import Foundation

enum APIError: LocalizedError {
    case unauthorized
    case httpError(Int, String)
    case decodingError(Error)
    case networkError(Error)

    var errorDescription: String? {
        switch self {
        case .unauthorized: return "Session expired. Please sign in again."
        case .httpError(let code, let msg): return "Error \(code): \(msg)"
        case .decodingError(let e): return "Data error: \(e.localizedDescription)"
        case .networkError(let e): return e.localizedDescription
        }
    }
}

final class APIService {
    static let shared = APIService()
    private init() {}

    private var baseURL: String { AppConfig.baseURL }

    func request<T: Decodable>(
        _ path: String,
        method: String = "GET",
        body: (some Encodable)? = nil as String?
    ) async throws -> T {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.networkError(URLError(.badURL))
        }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = KeychainService.loadToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            req.httpBody = try JSONEncoder().encode(body)
        }
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError.networkError(URLError(.badServerResponse))
        }
        if http.statusCode == 401 { throw APIError.unauthorized }
        guard (200..<300).contains(http.statusCode) else {
            let msg = (try? JSONDecoder().decode([String: String].self, from: data))?["detail"] ?? "Unknown error"
            throw APIError.httpError(http.statusCode, msg)
        }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    private func requestRaw(_ path: String, method: String) async throws {
        guard let url = URL(string: baseURL + path) else { throw APIError.networkError(URLError(.badURL)) }
        var req = URLRequest(url: url)
        req.httpMethod = method
        if let token = KeychainService.loadToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (_, response) = try await URLSession.shared.data(for: req)
        if let http = response as? HTTPURLResponse, http.statusCode == 401 { throw APIError.unauthorized }
    }

    // MARK: - Auth

    func getMe() async throws -> User {
        try await request("/api/me")
    }

    // MARK: - Games

    func listPuzzles(lang: String) async throws -> [PuzzleSummary] {
        try await request("/api/puzzles?lang=\(lang)")
    }

    func listScripts(lang: String) async throws -> [ScriptSummary] {
        try await request("/api/scripts?lang=\(lang)")
    }

    func createRoom(gameId: String, gameType: String, lang: String) async throws -> CreateRoomResponse {
        struct Body: Encodable {
            let game_type: String
            let puzzle_id: String?
            let script_id: String?
            let language: String
        }
        let body = Body(
            game_type: gameType,
            puzzle_id: gameType == "turtle_soup" ? gameId : nil,
            script_id: gameType == "murder_mystery" ? gameId : nil,
            language: lang
        )
        return try await request("/api/rooms", method: "POST", body: body)
    }

    // MARK: - Favorites

    func getFavorites() async throws -> [FavoriteItem] {
        try await request("/api/favorites")
    }

    func addFavorite(itemType: String, itemId: String) async throws {
        try await requestRaw("/api/favorites/\(itemType)/\(itemId)", method: "POST")
    }

    func removeFavorite(itemType: String, itemId: String) async throws {
        try await requestRaw("/api/favorites/\(itemType)/\(itemId)", method: "DELETE")
    }

    // MARK: - History

    func getHistory() async throws -> [HistoryItem] {
        try await request("/api/history")
    }
}
