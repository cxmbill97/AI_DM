import Foundation
import SwiftUI

@MainActor
final class HomeViewModel: ObservableObject {
    @Published var feedItems: [FeedItem] = []
    @Published var selectedFilter: FeedFilter = .all
    @Published var favorites: Set<String> = []
    @Published var liked: Set<String> = []
    @Published var isLoading = false
    @Published var error: String?
    @Published var isCreating = false

    enum FeedFilter: String, CaseIterable, Identifiable {
        case all = "For You"
        case turtleSoup = "Turtle Soup"
        case murderMystery = "Murder Mystery"
        case trending = "Trending"

        var id: String { rawValue }
        var icon: String {
            switch self {
            case .all: return "sparkles"
            case .turtleSoup: return "🐢"
            case .murderMystery: return "🔍"
            case .trending: return "flame"
            }
        }
    }

    var lang: String { UserDefaults.standard.string(forKey: "lang") ?? "zh" }

    var filteredItems: [FeedItem] {
        switch selectedFilter {
        case .all: return feedItems
        case .turtleSoup: return feedItems.filter { $0.gameType == "turtle_soup" }
        case .murderMystery: return feedItems.filter { $0.gameType == "murder_mystery" }
        case .trending: return feedItems.sorted { $0.likeCount > $1.likeCount }
        }
    }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let p = APIService.shared.listPuzzles(lang: lang)
            async let s = APIService.shared.listScripts(lang: lang)
            async let f = APIService.shared.getFavorites()
            async let c = APIService.shared.getCommunityScripts(lang: lang)
            let (puzzles, scripts, favs, community) = try await (p, s, f, c)

            favorites = Set(favs.filter { !$0.item_type.hasSuffix("_like") }.map { "\($0.item_type):\($0.item_id)" })
            liked     = Set(favs.filter {  $0.item_type.hasSuffix("_like") }.map { "\($0.item_type):\($0.item_id)" })

            // Build community lookup for like counts
            let communityByTitle: [String: CommunityScript] = Dictionary(
                community.map { ($0.title, $0) }, uniquingKeysWith: { a, _ in a }
            )

            var items: [FeedItem] = []
            for puzzle in puzzles {
                let comm = communityByTitle[puzzle.title]
                items.append(FeedItem(
                    id: "puzzle:\(puzzle.id)",
                    gameId: puzzle.id,
                    title: puzzle.title,
                    difficulty: puzzle.difficulty,
                    tags: puzzle.tags,
                    gameType: "turtle_soup",
                    playerCount: 1,
                    author: "AI DM",
                    likeCount: comm?.likes ?? Int.random(in: 0..<50),
                    isSaved: favorites.contains("puzzle:\(puzzle.id)"),
                    isLiked: liked.contains("puzzle_like:\(puzzle.id)")
                ))
            }
            for script in scripts {
                let comm = communityByTitle[script.title]
                items.append(FeedItem(
                    id: "script:\(script.id)",
                    gameId: script.id,
                    title: script.title,
                    difficulty: script.difficulty,
                    tags: [],
                    gameType: "murder_mystery",
                    playerCount: script.player_count,
                    author: comm?.author ?? "AI DM",
                    likeCount: comm?.likes ?? Int.random(in: 0..<80),
                    isSaved: favorites.contains("script:\(script.id)"),
                    isLiked: liked.contains("script_like:\(script.id)")
                ))
            }
            feedItems = items.shuffled()
        } catch is CancellationError {
            // Refresh gesture cancelled before completing — not an error
        } catch let urlErr as URLError where urlErr.code == .cancelled {
            // URLSession task cancelled mid-flight — ignore
        } catch {
            self.error = error.localizedDescription
        }
    }

    func toggleSave(item: FeedItem) {
        let type = item.gameType == "turtle_soup" ? "puzzle" : "script"
        let key = "\(type):\(item.gameId)"
        let idx = feedItems.firstIndex(where: { $0.id == item.id })
        let wasSaved = favorites.contains(key)
        if wasSaved { favorites.remove(key) } else { favorites.insert(key) }
        if let idx { feedItems[idx].isSaved = !wasSaved }
        Task {
            do {
                if wasSaved {
                    try await APIService.shared.removeFavorite(itemType: type, itemId: item.gameId)
                } else {
                    try await APIService.shared.addFavorite(itemType: type, itemId: item.gameId)
                }
            } catch {
                if wasSaved { favorites.insert(key) } else { favorites.remove(key) }
                if let idx { feedItems[idx].isSaved = wasSaved }
            }
        }
    }

    func toggleLike(item: FeedItem) {
        let likeType = item.gameType == "turtle_soup" ? "puzzle_like" : "script_like"
        let key = "\(likeType):\(item.gameId)"
        let idx = feedItems.firstIndex(where: { $0.id == item.id })
        let wasLiked = liked.contains(key)
        if wasLiked { liked.remove(key) } else { liked.insert(key) }
        if let idx { feedItems[idx].isLiked = !wasLiked }
        Task {
            do {
                if wasLiked {
                    try await APIService.shared.removeFavorite(itemType: likeType, itemId: item.gameId)
                } else {
                    try await APIService.shared.addFavorite(itemType: likeType, itemId: item.gameId)
                }
            } catch {
                if wasLiked { liked.insert(key) } else { liked.remove(key) }
                if let idx { feedItems[idx].isLiked = wasLiked }
            }
        }
    }
}
