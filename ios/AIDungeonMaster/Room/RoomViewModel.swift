import Foundation

struct ChatMessage: Identifiable {
    let id = UUID()
    let sender: String
    let text: String
    let type: MessageType
    enum MessageType { case player, dm, system, error }
}

@MainActor
final class RoomViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var players: [PlayerInfo] = []
    @Published var clues: [CluePayload] = []
    @Published var phase: String = ""
    @Published var phaseDescription: String = ""
    @Published var timeRemaining: Int? = nil
    @Published var truthProgress: Double = 0
    @Published var gameWon = false
    @Published var truth: String? = nil
    @Published var inputText = ""
    @Published var isSending = false
    @Published var showClues = false
    @Published var errorMessage: String?
    @Published var gameTitle: String = ""

    let roomId: String
    private let ws = WebSocketService()
    private var surfaceShown = false

    init(roomId: String) {
        self.roomId = roomId
    }

    var isConnected: Bool { ws.isConnected }
    var isReconnecting: Bool { ws.reconnecting }

    func connect() async {
        guard let token = KeychainService.loadToken() else { return }
        ws.connect(roomId: roomId, token: token)
        for await msg in ws.stream {
            handle(msg)
        }
    }

    func disconnect() {
        ws.disconnect()
    }

    func send() async {
        let text = inputText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        inputText = ""
        isSending = true
        defer { isSending = false }
        do {
            try await ws.send(ClientMessage(type: "chat", text: text))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func handle(_ msg: GameMessage) {
        switch msg {
        case .playerMessage(let p):
            messages.append(ChatMessage(sender: p.player_name, text: p.text, type: .player))

        case .dmResponse(let r):
            messages.append(ChatMessage(sender: "DM", text: r.response, type: .dm))
            truthProgress = r.truth_progress
            if let clue = r.clue_unlocked, !clues.contains(where: { $0.id == clue.id }) {
                clues.append(clue)
                messages.append(ChatMessage(sender: "System", text: "🔑 Clue unlocked: \(clue.title)", type: .system))
            }
            if let t = r.truth {
                truth = t
                gameWon = true
                messages.append(ChatMessage(sender: "System", text: "🎉 \(t)", type: .system))
                Task { try? await APIService.shared.completeRoom(roomId: roomId, outcome: "success") }
            }

        case .system(let s):
            messages.append(ChatMessage(sender: "System", text: s.text, type: .system))

        case .roomSnapshot(let snap):
            players = snap.players
            clues = snap.clues ?? []
            phase = snap.phase ?? snap.current_phase ?? ""
            phaseDescription = snap.phase_description ?? ""
            timeRemaining = snap.time_remaining
            if let title = snap.title, !title.isEmpty { gameTitle = title }
            // Show puzzle surface as first message (insert at 0, above any "joined" system notice)
            if !surfaceShown, let surface = snap.surface {
                surfaceShown = true
                let title = snap.title ?? "Mystery"
                messages.insert(ChatMessage(sender: title, text: surface, type: .dm), at: 0)
            }

        case .error(let e):
            messages.append(ChatMessage(sender: "System", text: "⚠️ \(e.message)", type: .error))
            errorMessage = e.message

        case .unknown:
            break
        }
    }
}
