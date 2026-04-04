import Foundation

@MainActor
final class LobbyViewModel: ObservableObject {
    @Published var puzzles: [PuzzleSummary] = []
    @Published var scripts: [ScriptSummary] = []
    @Published var favorites: Set<String> = []
    @Published var search = ""
    @Published var selectedTab: GameTab = .turtleSoup
    @Published var isLoading = false
    @Published var error: String?

    enum GameTab { case turtleSoup, murderMystery }

    var lang: String {
        UserDefaults.standard.string(forKey: "lang") ?? "zh"
    }

    var filteredPuzzles: [PuzzleSummary] {
        guard !search.isEmpty else { return puzzles }
        return puzzles.filter { $0.title.localizedCaseInsensitiveContains(search) }
    }

    var filteredScripts: [ScriptSummary] {
        guard !search.isEmpty else { return scripts }
        return scripts.filter { $0.title.localizedCaseInsensitiveContains(search) }
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let p = APIService.shared.listPuzzles(lang: lang)
            async let s = APIService.shared.listScripts(lang: lang)
            async let f = APIService.shared.getFavorites()
            let (fetchedPuzzles, fetchedScripts, fetchedFavs) = try await (p, s, f)
            puzzles = fetchedPuzzles
            scripts = fetchedScripts
            favorites = Set(fetchedFavs.map { "\($0.item_type):\($0.item_id)" })
        } catch {
            self.error = error.localizedDescription
        }
    }

    func toggleFavorite(type: String, id: String) {
        let key = "\(type):\(id)"
        let wasFavorited = favorites.contains(key)
        if wasFavorited { favorites.remove(key) } else { favorites.insert(key) }
        Task {
            do {
                if wasFavorited {
                    try await APIService.shared.removeFavorite(itemType: type, itemId: id)
                } else {
                    try await APIService.shared.addFavorite(itemType: type, itemId: id)
                }
            } catch {
                if wasFavorited { favorites.insert(key) } else { favorites.remove(key) }
            }
        }
    }

    func createRoom(gameId: String, gameType: String) async -> String? {
        do {
            let resp = try await APIService.shared.createRoom(gameId: gameId, gameType: gameType, lang: lang)
            return resp.room_id
        } catch {
            self.error = error.localizedDescription
            return nil
        }
    }
}
