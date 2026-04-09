import Foundation

@MainActor
final class WaitingRoomViewModel: ObservableObject {
    @Published var players: [PlayerInfo] = []
    @Published var started = false
    @Published var maxPlayers: Int = 4
    @Published var isReady = false
    @Published var isPublic = false
    @Published var errorMessage: String?
    @Published var isConnected = false

    let roomId: String
    let gameType: String
    private var myPlayerId: String?
    private var hostPlayerId: String?
    private let ws = WebSocketService()

    var isHost: Bool {
        guard let myId = myPlayerId, let hostId = hostPlayerId else { return false }
        return myId == hostId
    }

    var canStart: Bool { isHost && players.count >= 1 }

    /// Player IDs that have clicked Ready
    @Published var readyPlayerIds: Set<String> = []

    init(roomId: String, gameType: String) {
        self.roomId = roomId
        self.gameType = gameType
        // Derive our player_id from the stored JWT — the backend sets player_id = JWT sub
        myPlayerId = Self.playerIdFromToken()
    }

    /// Decode the JWT sub claim (no signature check needed — just for UI logic).
    private static func playerIdFromToken() -> String? {
        guard let token = KeychainService.loadToken() else { return nil }
        let parts = token.split(separator: ".")
        guard parts.count == 3 else { return nil }
        var b64 = String(parts[1])
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        // Pad to multiple of 4
        let pad = (4 - b64.count % 4) % 4
        b64 += String(repeating: "=", count: pad)
        guard let data = Data(base64Encoded: b64),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sub = json["sub"] as? String else { return nil }
        return sub
    }

    func connect() async {
        let token = KeychainService.loadToken() ?? ""
        ws.connect(roomId: roomId, token: token)
        isConnected = true
        for await msg in ws.stream {
            handle(msg)
        }
    }

    func disconnect() {
        ws.disconnect()
        isConnected = false
    }

    func sendReady() async {
        isReady = true
        do {
            try await ws.send(ClientMessage(type: "ready", text: ""))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func startGame() async {
        do {
            try await APIService.shared.startRoom(roomId: roomId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func togglePublic() async {
        let newValue = !isPublic
        do {
            try await APIService.shared.patchRoom(roomId: roomId, isPublic: newValue)
            isPublic = newValue
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func handle(_ msg: GameMessage) {
        switch msg {
        case .roomSnapshot(let snap):
            players = snap.players
            maxPlayers = snap.max_players ?? 4
            hostPlayerId = snap.host_player_id
            // my_player_id from snapshot is authoritative; fall back to JWT decode
            if let id = snap.my_player_id { myPlayerId = id }
            if snap.started == true { started = true }
            readyPlayerIds = Set(snap.players.compactMap { $0.is_ready == true ? $0.id : nil })

        case .lobbyPlayerJoined(let p):
            // A new player joined — add them if not already present
            if !players.contains(where: { $0.id == p.player_id }) {
                let newPlayer = PlayerInfo(
                    id: p.player_id,
                    name: p.player_name,
                    character: nil,
                    connected: true,
                    is_host: p.is_host,
                    is_ready: false
                )
                players.append(newPlayer)
            }

        case .lobbyPlayerReady(let p):
            readyPlayerIds.insert(p.player_id)
            players = players.map { player in
                guard player.id == p.player_id else { return player }
                return PlayerInfo(id: player.id, name: player.name, character: player.character,
                                  connected: player.connected, is_host: player.is_host, is_ready: true)
            }

        case .gameStarted:
            started = true

        case .system(let s):
            // Ignore join/leave system messages in lobby
            _ = s

        case .error(let e):
            errorMessage = e.message

        default:
            break
        }
    }

}
