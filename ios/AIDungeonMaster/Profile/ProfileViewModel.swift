import Foundation

@MainActor
final class ProfileViewModel: ObservableObject {
    struct LikedGame: Identifiable {
        let id: String      // "puzzle_like:xxx" | "script_like:xxx"
        let gameId: String
        let title: String
        let gameType: String
        let savedAt: String
    }

    @Published var displayName: String = ""
    @Published var email: String = ""
    @Published var avatarUrl: String = ""
    @Published var history: [HistoryItem] = []
    @Published var likedItems: [LikedGame] = []
    @Published var isLoading = false
    @Published var error: String?

    var lang: String { UserDefaults.standard.string(forKey: "lang") ?? "zh" }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let me = APIService.shared.getMe()
            async let hist = APIService.shared.getHistory()
            async let favs = APIService.shared.getFavorites()
            async let puzzles = APIService.shared.listPuzzles(lang: lang)
            async let scripts = APIService.shared.listScripts(lang: lang)
            let (user, histItems, allFavs, allPuzzles, allScripts) = try await (me, hist, favs, puzzles, scripts)
            displayName = user.name
            email = user.email
            avatarUrl = user.avatar_url
            history = histItems.filter { $0.outcome != nil }

            let puzzleMap = Dictionary(uniqueKeysWithValues: allPuzzles.map { ($0.id, $0.title) })
            let scriptMap = Dictionary(uniqueKeysWithValues: allScripts.map { ($0.id, $0.title) })

            likedItems = allFavs.compactMap { fav in
                guard fav.item_type.hasSuffix("_like") else { return nil }
                if fav.item_type == "puzzle_like" {
                    let title = puzzleMap[fav.item_id] ?? "Turtle Soup"
                    return LikedGame(id: fav.id, gameId: fav.item_id, title: title, gameType: "turtle_soup", savedAt: fav.saved_at)
                } else {
                    let title = scriptMap[fav.item_id] ?? "Murder Mystery"
                    return LikedGame(id: fav.id, gameId: fav.item_id, title: title, gameType: "murder_mystery", savedAt: fav.saved_at)
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
