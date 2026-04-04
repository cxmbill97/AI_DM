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

    private func requestRaw(_ path: String, method: String, jsonData: Data? = nil) async throws {
        guard let url = URL(string: baseURL + path) else { throw APIError.networkError(URLError(.badURL)) }
        var req = URLRequest(url: url)
        req.httpMethod = method
        if let token = KeychainService.loadToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let data = jsonData {
            req.httpBody = data
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
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

    func createRoom(gameId: String, gameType: String, lang: String, isPublic: Bool = true) async throws -> CreateRoomResponse {
        struct Body: Encodable {
            let game_type: String
            let puzzle_id: String?
            let script_id: String?
            let language: String
            let is_public: Bool
        }
        let body = Body(
            game_type: gameType,
            puzzle_id: gameType == "turtle_soup" ? gameId : nil,
            script_id: gameType == "murder_mystery" ? gameId : nil,
            language: lang,
            is_public: isPublic
        )
        return try await request("/api/rooms", method: "POST", body: body)
    }

    func completeRoom(roomId: String, outcome: String) async throws {
        struct Body: Encodable { let outcome: String }
        let data = try JSONEncoder().encode(Body(outcome: outcome))
        try await requestRaw("/api/rooms/\(roomId)/complete", method: "POST", jsonData: data)
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

    // MARK: - Active Rooms

    func getActiveRooms() async throws -> [ActiveRoom] {
        try await request("/api/rooms")
    }

    // MARK: - Community

    func getCommunityScripts(lang: String, search: String = "", limit: Int = 50) async throws -> [CommunityScript] {
        var path = "/api/community/scripts?lang=\(lang)&limit=\(limit)"
        if !search.isEmpty { path += "&search=\(search.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? search)" }
        return try await request(path)
    }

    func likeScript(scriptId: String) async throws -> Int {
        struct LikeResp: Decodable { let likes: Int }
        let resp: LikeResp = try await request("/api/community/scripts/\(scriptId)/like", method: "POST")
        return resp.likes
    }
}
