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

    var canStart: Bool {
        isHost && players.count >= 1
    }

    /// Player IDs that have clicked Ready
    @Published var readyPlayerIds: Set<String> = []

    init(roomId: String, gameType: String) {
        self.roomId = roomId
        self.gameType = gameType
    }

    func connect() async {
        guard let token = KeychainService.loadToken() else { return }
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
            isPublic = false  // default; patch endpoint controls this
            if snap.started == true {
                started = true
            }
            // Derive our own player_id from the first snapshot's player list
            // by matching the token's sub; fallback: we are the host if host_player_id is unset
            if myPlayerId == nil, let myId = snap.host_player_id, players.count == 1 {
                myPlayerId = myId
            }
            // Sync ready state
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

    /// Called from WaitingRoomView after WS connects and first snapshot arrives.
    /// We identify our own player slot by matching against the snapshot host logic:
    /// the room sets host_player_id = first joiner, so if we just created this room,
    /// we're the host. For joiners, we can't derive player_id from REST — it's set
    /// server-side from the JWT sub. We store it from the snapshot when possible.
    func identifyMe(playerId: String) {
        myPlayerId = playerId
    }
}
