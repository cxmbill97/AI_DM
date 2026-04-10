import Foundation

struct ChatMessage: Identifiable {
    let id = UUID()
    let sender: String
    var text: String
    let type: MessageType
    var judgment: String? = nil
    var isStreaming: Bool = false
    var streamId: String? = nil
    enum MessageType { case player, dm, system, error, emote }
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

    // Phase 3: turn system
    @Published var turnMode: Bool = false
    @Published var currentTurnPlayerId: String? = nil
    @Published var myPlayerId: String? = nil

    @Published var ttsEnabled: Bool = UserDefaults.standard.object(forKey: "tts_enabled") as? Bool ?? true

    let roomId: String
    private let ws = WebSocketService()
    private let tts = TTSService()
    private var surfaceShown = false
    private var isListening = false   // guard: only one stream consumer at a time

    init(roomId: String) {
        self.roomId = roomId
    }

    var isConnected: Bool { ws.isConnected }
    var isReconnecting: Bool { ws.reconnecting }

    var isMyTurn: Bool {
        guard turnMode, let mine = myPlayerId, let current = currentTurnPlayerId else { return false }
        return mine == current
    }

    func connect() async {
        let token = KeychainService.loadToken() ?? ""
        ws.connect(roomId: roomId, token: token)
        // AsyncStream is single-consumer. If .task fires twice (SwiftUI
        // re-render), a second for-await splits messages with the first,
        // causing half of them to silently disappear.
        guard !isListening else { return }
        isListening = true
        defer { isListening = false }
        for await msg in ws.stream {
            print("[RoomVM] received message from stream: \(msg)")
            handle(msg)
        }
        print("[RoomVM] stream ended")
    }

    func disconnect() {
        ws.disconnect()
        tts.stop()
    }

    func toggleTTS() {
        ttsEnabled.toggle()
        tts.isEnabled = ttsEnabled
        if !ttsEnabled { tts.stop() }
    }

    func send() async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
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

    func sendEmote(_ emoji: String) async {
        do {
            try await ws.send(ClientMessage(type: "chat", text: emoji))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func handle(_ msg: GameMessage) {
        switch msg {
        case .playerMessage(let p):
            let isEmote = p.text.unicodeScalars.allSatisfy { $0.properties.isEmojiPresentation || $0.value == 0x200D }
            messages.append(ChatMessage(sender: p.player_name, text: p.text,
                                        type: isEmote ? .emote : .player))

        case .dmResponse(let r):
            messages.append(ChatMessage(sender: "DM", text: r.response, type: .dm,
                                        judgment: r.judgment))
            tts.speak(r.response)
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

        case .dmStreamStart(let r):
            let placeholder = ChatMessage(sender: "DM", text: "", type: .dm,
                                          isStreaming: true, streamId: r.stream_id)
            messages.append(placeholder)

        case .dmStreamChunk(let r):
            if let idx = messages.lastIndex(where: { $0.streamId == r.stream_id }) {
                messages[idx].text += r.text
            }

        case .dmStreamEnd(let r):
            let sid = r.stream_id
            let finalText = r.response ?? ""
            if let idx = messages.lastIndex(where: { $0.streamId == sid }) {
                messages[idx].text = finalText
                messages[idx].judgment = r.judgment
                messages[idx].isStreaming = false
            } else {
                // fallback if start/chunk were missed
                messages.append(ChatMessage(sender: "DM", text: finalText, type: .dm, judgment: r.judgment))
            }
            tts.speak(finalText)
            if let progress = r.truth_progress { truthProgress = progress }
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

        case .turnChange(let t):
            currentTurnPlayerId = t.player_id
            messages.append(ChatMessage(sender: "System", text: t.text, type: .system))

        case .roomSnapshot(let snap):
            players = snap.players
            clues = snap.clues ?? []
            phase = snap.phase ?? snap.current_phase ?? ""
            phaseDescription = snap.phase_description ?? ""
            timeRemaining = snap.time_remaining
            if let title = snap.title, !title.isEmpty { gameTitle = title }
            // Phase 3: capture turn state
            if let tm = snap.turn_mode { turnMode = tm }
            currentTurnPlayerId = snap.current_turn_player_id
            if let mine = snap.my_player_id { myPlayerId = mine }
            // Show puzzle surface as first message
            if !surfaceShown, let surface = snap.surface {
                surfaceShown = true
                let title = snap.title ?? "Mystery"
                messages.insert(ChatMessage(sender: title, text: surface, type: .dm), at: 0)
            }

        case .error(let e):
            messages.append(ChatMessage(sender: "System", text: "⚠️ \(e.message)", type: .error))
            errorMessage = e.message

        case .lobbyPlayerJoined, .lobbyPlayerReady:
            break

        case .gameStarted:
            break

        case .unknown:
            break
        }
    }
}
