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
        // Reset the stream so the caller always gets a fresh for-await sequence.
        // This is safe here because we're not yet connected — no active consumer exists.
        resetStream()
        DebugLog.log("WS", "connect() roomId=\(roomId) token=\(self.token.prefix(20))...")
        openConnection()
    }

    private static func stableGuestToken() -> String {
        // Store in Keychain so it persists across reinstalls and is not iCloud-backed.
        // Using a dedicated Keychain entry separate from the JWT token.
        let service = "com.aidm.AIDungeonMaster"
        let account = "ws_guest_stable_id"
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
            kSecReturnData: true,
            kSecMatchLimit: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        if SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
           let data = result as? Data,
           let stored = String(data: data, encoding: .utf8),
           stored.count >= 12 {
            return "guest:\(stored)"
        }
        // Generate and save a new guest ID.
        let guestId = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
        let saveQuery: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: account,
            kSecValueData: Data(guestId.utf8),
        ]
        SecItemDelete(saveQuery as CFDictionary)
        SecItemAdd(saveQuery as CFDictionary, nil)

        #if DEBUG
        // Simulator Keychain may fail without code signing — fall back to UserDefaults in DEBUG
        if SecItemCopyMatching(query as CFDictionary, &result) != errSecSuccess {
            let key = "ws_guest_stable_id"
            UserDefaults.standard.set(guestId, forKey: key)
        }
        #endif

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
        // isConnected is set to true on first successful receive in listen(),
        // not here — the handshake is asynchronous and the server may reject the connection.
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
            var firstMessage = true
            do {
                while !Task.isCancelled, connectionId == self.currentConnectionId {
                    let msg = try await ws.receive()
                    guard connectionId == self.currentConnectionId else {
                        DebugLog.log("WS", "connectionId rotated, exiting listen loop")
                        break
                    }
                    if firstMessage {
                        // Handshake confirmed — server accepted the connection.
                        firstMessage = false
                        await MainActor.run { self.isConnected = true }
                        DebugLog.log("WS", "first message received → isConnected = true")
                    }
                    if case .string(let text) = msg {
                        DebugLog.log("WS", "RAW ← \(String(text.prefix(150)))")
                        guard let data = text.data(using: .utf8) else {
                            DebugLog.log("WS", "ERROR: utf8 conversion failed")
                            continue
                        }
                        do {
                            let gameMsg = try JSONDecoder().decode(GameMessage.self, from: data)
                            DebugLog.log("WS", "✓ decoded: \(String(describing: gameMsg).prefix(60))")
                            if self.continuation == nil {
                                DebugLog.log("WS", "⚠️ continuation is NIL — message LOST")
                            }
                            self.continuation?.yield(gameMsg)
                            DebugLog.log("WS", "✓ yield called")
                        } catch {
                            DebugLog.log("WS", "❌ DECODE FAIL: \(error)")
                            DebugLog.log("WS", "❌ raw: \(String(text.prefix(300)))")
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
        // Rotate connectionId FIRST so the stale listenTask's catch block sees a
        // mismatched ID and skips handleDisconnect — preventing a ghost reconnect.
        currentConnectionId = UUID()
        listenTask?.cancel()
        listenTask = nil
        pingTask?.cancel()
        pingTask = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        isConnected = false
        reconnecting = false
        // Finish the current stream so any active for-await consumer exits cleanly.
        // Do NOT call resetStream() here — that would orphan the new stream with no consumer.
        // connect() calls resetStream() at the start of the next connection.
        continuation?.finish()
        continuation = nil
    }
}
