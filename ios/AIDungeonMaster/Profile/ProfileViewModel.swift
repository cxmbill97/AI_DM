import Foundation

@MainActor
final class ProfileViewModel: ObservableObject {
    @Published var displayName: String = ""
    @Published var email: String = ""
    @Published var avatarUrl: String = ""
    @Published var history: [HistoryItem] = []
    @Published var likedItems: [FavoriteItem] = []
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
            let (user, histItems, allFavs) = try await (me, hist, favs)
            displayName = user.name
            email = user.email
            avatarUrl = user.avatar_url
            history = histItems.filter { $0.outcome != nil }
            likedItems = allFavs.filter { $0.item_type.hasSuffix("_like") }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
