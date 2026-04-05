import SwiftUI

struct SavedView: View {
    @StateObject private var vm = SavedViewModel()
    @State private var navigateToRoom: String? = nil
    @State private var isCreating = false
    @State private var showGameModeSheet = false
    @State private var pendingItem: SavedViewModel.SavedFeedItem? = nil

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0a0a0f").ignoresSafeArea()

                VStack(spacing: 0) {
                    // Header
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Saved")
                                .font(.system(size: 22, weight: .black, design: .serif))
                                .foregroundStyle(LinearGradient(
                                    colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                                    startPoint: .leading, endPoint: .trailing
                                ))
                            Text("Your bookmarked games")
                                .font(.system(size: 11))
                                .foregroundColor(Color(hex: "#44446a"))
                        }
                        Spacer()
                        if vm.isLoading {
                            ProgressView().tint(Color(hex: "#c9a84c")).scaleEffect(0.8)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 16)

                    if vm.savedItems.isEmpty && !vm.isLoading {
                        emptyState
                    } else {
                        ScrollView(showsIndicators: false) {
                            LazyVStack(spacing: 10) {
                                ForEach(vm.savedItems) { item in
                                    SavedRow(item: item, onPlay: {
                                        pendingItem = item
                                        showGameModeSheet = true
                                    }, onRemove: {
                                        vm.remove(item: item)
                                    })
                                    .padding(.horizontal, 16)
                                }
                            }
                            .padding(.bottom, 24)
                        }
                    }
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(isPresented: Binding(
                get: { navigateToRoom != nil },
                set: { if !$0 { navigateToRoom = nil } }
            )) {
                if let roomId = navigateToRoom { RoomView(roomId: roomId) }
            }
            .task { await vm.load() }
            .sheet(isPresented: $showGameModeSheet) {
                if let item = pendingItem {
                    GameModeSheet { isPublic in
                        showGameModeSheet = false
                        createAndNavigate(gameId: item.gameId, gameType: item.gameType, isPublic: isPublic)
                    }
                }
            }
            .alert("Error", isPresented: Binding(
                get: { vm.error != nil },
                set: { if !$0 { vm.error = nil } }
            )) {
                Button("OK", role: .cancel) { vm.error = nil }
            } message: {
                Text(vm.error ?? "")
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "bookmark.slash")
                .font(.system(size: 44))
                .foregroundColor(Color(hex: "#2a2840"))
            Text("No saved games yet")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(Color(hex: "#44446a"))
            Text("Tap the bookmark icon on any game to save it here.")
                .font(.system(size: 13))
                .foregroundColor(Color(hex: "#2a2840"))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.top, 80)
    }

    private func createAndNavigate(gameId: String, gameType: String, isPublic: Bool = true) {
        guard !isCreating else { return }
        isCreating = true
        let lang = UserDefaults.standard.string(forKey: "lang") ?? "zh"
        Task {
            defer { isCreating = false }
            do {
                let resp = try await APIService.shared.createRoom(gameId: gameId, gameType: gameType, lang: lang, isPublic: isPublic)
                navigateToRoom = resp.room_id
            } catch {
                vm.error = error.localizedDescription
            }
        }
    }
}

// MARK: - SavedViewModel

@MainActor
final class SavedViewModel: ObservableObject {
    struct SavedFeedItem: Identifiable {
        let id: String
        let gameId: String
        let title: String
        let gameType: String
        let difficulty: String
        let playerCount: Int
    }

    @Published var savedItems: [SavedFeedItem] = []
    @Published var isLoading = false
    @Published var error: String?

    var lang: String { UserDefaults.standard.string(forKey: "lang") ?? "zh" }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            async let favs = APIService.shared.getFavorites()
            async let puzzles = APIService.shared.listPuzzles(lang: lang)
            async let scripts = APIService.shared.listScripts(lang: lang)
            let (favorites, allPuzzles, allScripts) = try await (favs, puzzles, scripts)

            let puzzleMap = Dictionary(uniqueKeysWithValues: allPuzzles.map { ($0.id, $0) })
            let scriptMap = Dictionary(uniqueKeysWithValues: allScripts.map { ($0.id, $0) })

            savedItems = favorites.compactMap { fav in
                if fav.item_type == "puzzle", let p = puzzleMap[fav.item_id] {
                    return SavedFeedItem(id: fav.id, gameId: p.id, title: p.title, gameType: "turtle_soup", difficulty: p.difficulty, playerCount: 1)
                } else if fav.item_type == "script", let s = scriptMap[fav.item_id] {
                    return SavedFeedItem(id: fav.id, gameId: s.id, title: s.title, gameType: "murder_mystery", difficulty: s.difficulty, playerCount: s.player_count)
                }
                return nil
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    func remove(item: SavedFeedItem) {
        savedItems.removeAll { $0.id == item.id }
        let type = item.gameType == "turtle_soup" ? "puzzle" : "script"
        Task {
            try? await APIService.shared.removeFavorite(itemType: type, itemId: item.gameId)
        }
    }
}

// MARK: - SavedRow

private struct SavedRow: View {
    let item: SavedViewModel.SavedFeedItem
    let onPlay: () -> Void
    let onRemove: () -> Void

    private var gradientColors: [Color] {
        let hues: [(Double, Double)] = [
            (0.05, 0.15), (0.55, 0.65), (0.3, 0.4),
            (0.7, 0.8), (0.15, 0.25), (0.45, 0.55)
        ]
        let pair = hues[abs(item.title.hashValue) % hues.count]
        return [Color(hue: pair.0, saturation: 0.5, brightness: 0.3), Color(hue: pair.1, saturation: 0.6, brightness: 0.2)]
    }

    var body: some View {
        HStack(spacing: 14) {
            // Thumbnail
            RoundedRectangle(cornerRadius: 10)
                .fill(LinearGradient(colors: gradientColors, startPoint: .topLeading, endPoint: .bottomTrailing))
                .frame(width: 64, height: 64)
                .overlay(
                    Text(item.gameType == "turtle_soup" ? "🐢" : "🔍")
                        .font(.system(size: 28))
                )

            VStack(alignment: .leading, spacing: 6) {
                Text(item.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(2)
                HStack(spacing: 8) {
                    Text(localizedDifficulty(item.difficulty))
                        .font(.system(size: 11))
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(Color(hex: "#1e1c2e"))
                        .foregroundColor(Color(hex: "#5555a0"))
                        .clipShape(Capsule())
                    if item.playerCount > 1 {
                        Label("\(item.playerCount)p", systemImage: "person.2.fill")
                            .font(.system(size: 11))
                            .foregroundColor(Color(hex: "#44446a"))
                    }
                }
            }

            Spacer()

            VStack(spacing: 8) {
                Button(action: onPlay) {
                    Image(systemName: "play.fill")
                        .font(.system(size: 13))
                        .foregroundColor(.black)
                        .frame(width: 36, height: 36)
                        .background(Color(hex: "#c9a84c"))
                        .clipShape(Circle())
                }
                Button(action: onRemove) {
                    Image(systemName: "bookmark.slash.fill")
                        .font(.system(size: 13))
                        .foregroundColor(Color(hex: "#44446a"))
                        .frame(width: 36, height: 36)
                        .background(Color(hex: "#16151f"))
                        .clipShape(Circle())
                        .overlay(Circle().stroke(Color(hex: "#2a2840"), lineWidth: 1))
                }
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(Color(hex: "#16151f"))
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }
}
