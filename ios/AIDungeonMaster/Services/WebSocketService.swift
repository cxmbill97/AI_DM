import Foundation

@MainActor
final class WebSocketService: ObservableObject {
    @Published var isConnected = false
    @Published var reconnecting = false

    private var task: URLSessionWebSocketTask?
    private var continuation: AsyncStream<GameMessage>.Continuation?
    private(set) var stream: AsyncStream<GameMessage>!
    private var roomId: String = ""
    private var token: String = ""
    private var retryCount = 0
    private let maxRetries = 3
    private var pingTask: Task<Void, Never>?
    private var currentConnectionId = UUID()

    init() {
        resetStream()
    }

    private func resetStream() {
        stream = AsyncStream { [weak self] continuation in
            self?.continuation = continuation
            DebugLog.log("WS", "AsyncStream build closure: continuation stored = \(self?.continuation != nil)")
        }
    }

    func connect(roomId: String, token: String) {
        if (isConnected || reconnecting) && self.roomId == roomId {
            DebugLog.log("WS", "connect() SKIPPED (already connected/reconnecting to \(roomId))")
            return
        }
        self.roomId = roomId
        self.token = token.isEmpty ? Self.stableGuestToken() : token
        self.retryCount = 0
        DebugLog.log("WS", "connect() roomId=\(roomId) token=\(self.token.prefix(20))...")
        openConnection()
    }

    private static func stableGuestToken() -> String {
        let key = "ws_guest_stable_id"
        let stored = UserDefaults.standard.string(forKey: key) ?? ""
        let guestId: String
        if stored.count >= 12 {
            guestId = stored
        } else {
            guestId = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
            UserDefaults.standard.set(guestId, forKey: key)
        }
        return "guest:\(guestId)"
    }

    private func openConnection() {
        let connId = UUID()
        currentConnectionId = connId

        pingTask?.cancel()
        pingTask = nil
        task?.cancel(with: .goingAway, reason: nil)

        let encodedToken = token.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? token
        let urlString = "\(AppConfig.wsBaseURL)/ws/\(roomId)?token=\(encodedToken)"
        guard let url = URL(string: urlString) else {
            DebugLog.log("WS", "ERROR: invalid URL: \(urlString)")
            return
        }
        DebugLog.log("WS", "openConnection → \(urlString)")
        task = URLSession.shared.webSocketTask(with: url)
        task?.resume()
        isConnected = true
        reconnecting = false
        listen(connectionId: connId)
        startPingLoop()
    }

    private func startPingLoop() {
        pingTask = Task {
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 20_000_000_000)
                guard !Task.isCancelled, let t = task else { break }
                t.sendPing { _ in }
            }
        }
    }

    private var listenTask: Task<Void, Never>?

    private func listen(connectionId: UUID) {
        listenTask?.cancel()
        listenTask = Task { [weak self] in
            guard let self else {
                DebugLog.log("WS", "listen: self deallocated")
                return
            }
            guard let ws = self.task else {
                DebugLog.log("WS", "listen: task is nil, exiting")
                return
            }
            DebugLog.log("WS", "listen loop STARTED connId=\(connectionId.uuidString.prefix(8))")
            do {
                while !Task.isCancelled, connectionId == self.currentConnectionId {
                    let msg = try await ws.receive()
                    guard connectionId == self.currentConnectionId else {
                        DebugLog.log("WS", "connectionId rotated, exiting listen loop")
                        break
                    }
                    if case .string(let text) = msg {
                        DebugLog.log("WS", "RAW ← \(String(text.prefix(150)))")
                        guard let data = text.data(using: .utf8) else {
                            DebugLog.log("WS", "ERROR: utf8 conversion failed")
                            continue
                        }
                        do {
                            let gameMsg = try JSONDecoder().decode(GameMessage.self, from: data)
                            if self.continuation == nil {
                                DebugLog.log("WS", "⚠️ continuation is NIL — message will be LOST")
                            }
                            self.continuation?.yield(gameMsg)
                        } catch {
                            DebugLog.log("WS", "❌ DECODE FAIL: \(error)")
                            DebugLog.log("WS", "❌ raw text: \(String(text.prefix(300)))")
                        }
                    } else {
                        DebugLog.log("WS", "recv non-string message (binary?)")
                    }
                }
                DebugLog.log("WS", "listen loop EXITED normally (cancelled=\(Task.isCancelled))")
            } catch {
                guard connectionId == self.currentConnectionId else { return }
                DebugLog.log("WS", "❌ receive error: \(error)")
                self.handleDisconnect()
            }
        }
    }

    private func handleDisconnect() {
        isConnected = false
        DebugLog.log("WS", "handleDisconnect retry=\(retryCount)/\(maxRetries)")
        guard retryCount < maxRetries else {
            DebugLog.log("WS", "max retries reached, finishing stream")
            continuation?.finish()
            return
        }
        retryCount += 1
        reconnecting = true
        let delay = Double(retryCount) * 1.5
        Task {
            try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
            await self.openConnection()
        }
    }

    func send(_ message: ClientMessage) async throws {
        let data = try JSONEncoder().encode(message)
        let text = String(data: data, encoding: .utf8) ?? ""
        DebugLog.log("WS", "SEND → \(String(text.prefix(120)))")
        try await task?.send(.string(text))
    }

    func disconnect() {
        DebugLog.log("WS", "disconnect() called")
        listenTask?.cancel()
        listenTask = nil
        pingTask?.cancel()
        pingTask = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        isConnected = false
        reconnecting = false
        continuation?.finish()
        resetStream()
    }
}
