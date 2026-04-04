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

    init() {
        resetStream()
    }

    private func resetStream() {
        stream = AsyncStream { [weak self] continuation in
            self?.continuation = continuation
        }
    }

    func connect(roomId: String, token: String) {
        self.roomId = roomId
        self.token = token
        self.retryCount = 0
        openConnection()
    }

    private func openConnection() {
        let encodedToken = token.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? token
        let urlString = "\(AppConfig.wsBaseURL)/ws/\(roomId)?token=\(encodedToken)"
        guard let url = URL(string: urlString) else { return }
        task = URLSession.shared.webSocketTask(with: url)
        task?.resume()
        isConnected = true
        reconnecting = false
        listen()
    }

    private func listen() {
        task?.receive { [weak self] result in
            guard let self else { return }
            switch result {
            case .success(let msg):
                if case .string(let text) = msg,
                   let data = text.data(using: .utf8),
                   let gameMsg = try? JSONDecoder().decode(GameMessage.self, from: data) {
                    Task { @MainActor in
                        self.continuation?.yield(gameMsg)
                    }
                }
                self.listen()
            case .failure:
                Task { @MainActor in
                    self.handleDisconnect()
                }
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
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        isConnected = false
        reconnecting = false
        continuation?.finish()
        resetStream()
    }
}
