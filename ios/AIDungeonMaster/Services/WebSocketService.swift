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
        }
    }

    func connect(roomId: String, token: String) {
        // Prevent double-connecting to the same room (e.g. SwiftUI .task firing twice,
        // or an external connect() call racing with the internal reconnect retry task).
        if (isConnected || reconnecting) && self.roomId == roomId { return }
        self.roomId = roomId
        // If no JWT, use a stable guest token so reconnects keep the same identity
        self.token = token.isEmpty ? Self.stableGuestToken() : token
        self.retryCount = 0
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
        // Rotate connection ID first — any pending receive closure from the old
        // task will see a stale ID and exit without calling handleDisconnect.
        let connId = UUID()
        currentConnectionId = connId

        pingTask?.cancel()
        pingTask = nil
        task?.cancel(with: .goingAway, reason: nil)

        let encodedToken = token.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? token
        let urlString = "\(AppConfig.wsBaseURL)/ws/\(roomId)?token=\(encodedToken)"
        guard let url = URL(string: urlString) else { return }
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
                try? await Task.sleep(nanoseconds: 20_000_000_000) // ping every 20s
                guard !Task.isCancelled, let t = task else { break }
                t.sendPing { _ in } // keep-alive; ignore pong result
            }
        }
    }

    private var listenTask: Task<Void, Never>?

    private func listen(connectionId: UUID) {
        listenTask?.cancel()
        listenTask = Task { [weak self] in
            guard let self else { return }
            guard let ws = self.task else { return }
            do {
                while !Task.isCancelled, connectionId == self.currentConnectionId {
                    let msg = try await ws.receive()
                    guard connectionId == self.currentConnectionId else {
                        print("[WS] connectionId rotated, exiting listen loop")
                        break
                    }
                    if case .string(let text) = msg {
                        guard let data = text.data(using: .utf8) else {
                            print("[WS] failed to convert text to data")
                            continue
                        }
                        do {
                            let gameMsg = try JSONDecoder().decode(GameMessage.self, from: data)
                            print("[WS] decoded message: \(gameMsg)")
                            self.continuation?.yield(gameMsg)
                        } catch {
                            print("[WS] decode FAILED: \(error)")
                            print("[WS] raw text: \(text.prefix(300))")
                        }
                    }
                }
            } catch {
                guard connectionId == self.currentConnectionId else { return }
                print("[WS] receive error: \(error)")
                self.handleDisconnect()
            }
        }
    }

    private func handleDisconnect() {
        isConnected = false
        guard retryCount < maxRetries else {
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
        try await task?.send(.string(text))
    }

    func disconnect() {
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
