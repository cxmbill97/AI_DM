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
        DebugLog.log("VM", "init roomId=\(roomId)")
    }

    var isConnected: Bool { ws.isConnected }
    var isReconnecting: Bool { ws.reconnecting }

    var isMyTurn: Bool {
        guard turnMode, let mine = myPlayerId, let current = currentTurnPlayerId else { return false }
        return mine == current
    }

    func connect() async {
        let token = KeychainService.loadToken() ?? ""
        DebugLog.log("VM", "connect() roomId=\(roomId) hasToken=\(!token.isEmpty)")
        ws.connect(roomId: roomId, token: token)
        guard !isListening else {
            DebugLog.log("VM", "⚠️ ALREADY LISTENING — skipping for-await!")
            return
        }
        isListening = true
        DebugLog.log("VM", "entering for-await loop on ws.stream")
        defer {
            isListening = false
            DebugLog.log("VM", "for-await EXITED, isListening=false")
        }
        for await msg in ws.stream {
            DebugLog.log("VM", "◆ stream yielded: \(String(describing: msg).prefix(80))")
            handle(msg)
        }
        DebugLog.log("VM", "⚠️ stream FINISHED (for-await loop exited)")
    }

    func disconnect() {
        DebugLog.log("VM", "disconnect()")
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
        DebugLog.log("VM", "send() text='\(text.prefix(50))' inputText.count=\(inputText.count)")
        inputText = ""
        isSending = true
        defer { isSending = false }
        do {
            try await ws.send(ClientMessage(type: "chat", text: text))
            DebugLog.log("VM", "send() OK")
        } catch {
            DebugLog.log("VM", "❌ send() error: \(error)")
            errorMessage = error.localizedDescription
        }
    }

    func sendEmote(_ emoji: String) async {
        DebugLog.log("VM", "sendEmote(\(emoji))")
        do {
            try await ws.send(ClientMessage(type: "chat", text: emoji))
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func handle(_ msg: GameMessage) {
        let beforeCount = messages.count
        switch msg {
        case .playerMessage(let p):
            DebugLog.log("VM", "→ playerMessage from=\(p.player_name) text='\(p.text.prefix(40))'")
            let isEmote = p.text.unicodeScalars.allSatisfy { $0.properties.isEmojiPresentation || $0.value == 0x200D }
            messages.append(ChatMessage(sender: p.player_name, text: p.text,
                                        type: isEmote ? .emote : .player))

        case .dmResponse(let r):
            DebugLog.log("VM", "→ dmResponse judgment=\(r.judgment) resp='\(r.response.prefix(40))'")
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
            DebugLog.log("VM", "→ dmStreamStart sid=\(r.stream_id)")
            let placeholder = ChatMessage(sender: "DM", text: "", type: .dm,
                                          isStreaming: true, streamId: r.stream_id)
            messages.append(placeholder)

        case .dmStreamChunk(let r):
            if let idx = messages.lastIndex(where: { $0.streamId == r.stream_id }) {
                messages[idx].text += r.text
            } else {
                DebugLog.log("VM", "⚠️ dmStreamChunk: no message with sid=\(r.stream_id)")
            }

        case .dmStreamEnd(let r):
            DebugLog.log("VM", "→ dmStreamEnd sid=\(r.stream_id ?? "nil") judgment=\(r.judgment ?? "nil")")
            let sid = r.stream_id
            let finalText = r.response ?? ""
            if let idx = messages.lastIndex(where: { $0.streamId == sid }) {
                messages[idx].text = finalText
                messages[idx].judgment = r.judgment
                messages[idx].isStreaming = false
            } else {
                DebugLog.log("VM", "⚠️ dmStreamEnd fallback — no matching start")
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
            DebugLog.log("VM", "→ system: \(s.text.prefix(60))")
            messages.append(ChatMessage(sender: "System", text: s.text, type: .system))

        case .turnChange(let t):
            DebugLog.log("VM", "→ turnChange player=\(t.player_id)")
            currentTurnPlayerId = t.player_id
            messages.append(ChatMessage(sender: "System", text: t.text, type: .system))

        case .roomSnapshot(let snap):
            DebugLog.log("VM", "→ roomSnapshot players=\(snap.players.count) phase=\(snap.phase ?? snap.current_phase ?? "?") started=\(snap.started ?? false)")
            players = snap.players
            clues = snap.clues ?? []
            phase = snap.phase ?? snap.current_phase ?? ""
            phaseDescription = snap.phase_description ?? ""
            timeRemaining = snap.time_remaining
            if let title = snap.title, !title.isEmpty { gameTitle = title }
            if let tm = snap.turn_mode { turnMode = tm }
            currentTurnPlayerId = snap.current_turn_player_id
            if let mine = snap.my_player_id { myPlayerId = mine }
            if !surfaceShown, let surface = snap.surface {
                surfaceShown = true
                let title = snap.title ?? "Mystery"
                messages.insert(ChatMessage(sender: title, text: surface, type: .dm), at: 0)
                DebugLog.log("VM", "  surface shown: '\(surface.prefix(40))'")
            }

        case .error(let e):
            DebugLog.log("VM", "→ ERROR: \(e.message)")
            messages.append(ChatMessage(sender: "System", text: "⚠️ \(e.message)", type: .error))
            errorMessage = e.message

        case .lobbyPlayerJoined, .lobbyPlayerReady:
            break

        case .gameStarted:
            DebugLog.log("VM", "→ gameStarted")

        case .unknown(let type):
            DebugLog.log("VM", "→ unknown type: \(type)")
        }
        let afterCount = messages.count
        if afterCount != beforeCount {
            DebugLog.log("VM", "  messages \(beforeCount)→\(afterCount)")
        }
    }
}
