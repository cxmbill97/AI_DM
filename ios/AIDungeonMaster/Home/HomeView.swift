import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var auth: AuthViewModel
    @StateObject private var vm = HomeViewModel()
    @State private var navigateToRoom: String? = nil
    @State private var isCreating = false
    @State private var showGameModeSheet = false
    @State private var pendingItem: FeedItem?

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0a0a0f").ignoresSafeArea()

                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        // Stories-style filter row
                        storiesRow
                            .padding(.top, 4)

                        // Feed
                        if vm.isLoading && vm.feedItems.isEmpty {
                            loadingPlaceholder
                        } else if vm.filteredItems.isEmpty {
                            emptyState
                        } else {
                            LazyVStack(spacing: 0) {
                                ForEach(vm.filteredItems) { item in
                                    FeedCardView(
                                        item: item,
                                        onSave: { vm.toggleSave(item: item) },
                                        onLike: { vm.toggleLike(item: item) },
                                        onPlay: { pendingItem = item; showGameModeSheet = true }
                                    )
                                    .padding(.bottom, 12)
                                }
                            }
                            .padding(.top, 4)
                        }
                    }
                }
                .refreshable { await vm.load() }
                .safeAreaInset(edge: .top, spacing: 0) {
                    navBar
                        .background(
                            Color(hex: "#0a0a0f").opacity(0.95)
                                .ignoresSafeArea(edges: .top)
                        )
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(isPresented: Binding(
                get: { navigateToRoom != nil },
                set: { if !$0 { navigateToRoom = nil } }
            )) {
                if let roomId = navigateToRoom { RoomView(roomId: roomId) }
            }
            .task {
                await vm.load()
                #if DEBUG
                if let roomId = auth.debugRoomId {
                    auth.debugRoomId = nil  // consume once — prevents re-navigation on tab switch
                    navigateToRoom = roomId
                }
                #endif
            }
            .sheet(isPresented: $showGameModeSheet) {
                if let item = pendingItem {
                    GameModeSheet { isPublic in
                        showGameModeSheet = false
                        createAndNavigate(item: item, isPublic: isPublic)
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

    // MARK: - Nav bar

    private var navBar: some View {
        HStack {
            Text("AI DM")
                .font(.system(size: 24, weight: .black, design: .serif))
                .foregroundStyle(LinearGradient(
                    colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                    startPoint: .leading, endPoint: .trailing
                ))
            Spacer()
            if vm.isLoading {
                ProgressView().tint(Color(hex: "#c9a84c")).scaleEffect(0.8)
            } else {
                Button { Task { await vm.load() } } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 15))
                        .foregroundColor(Color(hex: "#44446a"))
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    // MARK: - Stories row

    private var storiesRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 16) {
                ForEach(HomeViewModel.FeedFilter.allCases) { filter in
                    StoryBubble(
                        filter: filter,
                        isSelected: vm.selectedFilter == filter
                    ) {
                        withAnimation(.spring(response: 0.3)) { vm.selectedFilter = filter }
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
        }
    }

    // MARK: - Loading / empty

    private var loadingPlaceholder: some View {
        VStack(spacing: 16) {
            ForEach(0..<3, id: \.self) { _ in
                RoundedRectangle(cornerRadius: 16)
                    .fill(Color(hex: "#16151f"))
                    .frame(height: 320)
                    .padding(.horizontal, 16)
                    .redacted(reason: .placeholder)
                    .shimmering()
            }
        }
        .padding(.top, 8)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "eyes.inverse")
                .font(.system(size: 40))
                .foregroundColor(Color(hex: "#2a2840"))
            Text("Nothing here yet")
                .font(.system(size: 15))
                .foregroundColor(Color(hex: "#44446a"))
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 80)
    }

    // MARK: - Create room

    private func createAndNavigate(item: FeedItem, isPublic: Bool = true) {
        guard !isCreating else { return }
        isCreating = true
        let lang = UserDefaults.standard.string(forKey: "lang") ?? "zh"
        Task {
            defer { isCreating = false }
            do {
                let resp = try await APIService.shared.createRoom(
                    gameId: item.gameId,
                    gameType: item.gameType,
                    lang: lang,
                    isPublic: isPublic
                )
                navigateToRoom = resp.room_id
            } catch {
                vm.error = error.localizedDescription
            }
        }
    }
}

// MARK: - Story bubble

private struct StoryBubble: View {
    let filter: HomeViewModel.FeedFilter
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                ZStack {
                    Circle()
                        .stroke(
                            isSelected
                                ? LinearGradient(colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")], startPoint: .topLeading, endPoint: .bottomTrailing)
                                : LinearGradient(colors: [Color(hex: "#2a2840"), Color(hex: "#2a2840")], startPoint: .top, endPoint: .bottom),
                            lineWidth: 2.5
                        )
                        .frame(width: 60, height: 60)

                    Circle()
                        .fill(isSelected ? Color(hex: "#1e1c2e") : Color(hex: "#16151f"))
                        .frame(width: 54, height: 54)

                    if filter.icon.count == 1 || filter.icon.count == 2 {
                        Text(filter.icon)
                            .font(.system(size: 24))
                    } else {
                        Image(systemName: filter.icon)
                            .font(.system(size: 20))
                            .foregroundStyle(
                                isSelected
                                    ? LinearGradient(colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")], startPoint: .top, endPoint: .bottom)
                                    : LinearGradient(colors: [Color(hex: "#44446a"), Color(hex: "#44446a")], startPoint: .top, endPoint: .bottom)
                            )
                    }
                }

                Text(filter.rawValue)
                    .font(.system(size: 11, weight: isSelected ? .semibold : .regular))
                    .foregroundColor(isSelected ? Color(hex: "#c9a84c") : Color(hex: "#44446a"))
                    .lineLimit(1)
            }
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Feed card

struct FeedCardView: View {
    let item: FeedItem
    let onSave: () -> Void
    let onLike: () -> Void
    let onPlay: () -> Void

    private var gradientColors: [Color] {
        let hues: [(Double, Double)] = [
            (0.05, 0.15), (0.55, 0.65), (0.3, 0.4),
            (0.7, 0.8), (0.15, 0.25), (0.45, 0.55)
        ]
        let pair = hues[abs(item.title.hashValue) % hues.count]
        return [
            Color(hue: pair.0, saturation: 0.5, brightness: 0.25),
            Color(hue: pair.1, saturation: 0.6, brightness: 0.18),
        ]
    }

    var body: some View {
        VStack(spacing: 0) {
            // Post header
            postHeader

            // Artwork
            artworkPanel

            // Actions
            actionRow

            // Description
            descriptionRow
        }
        .background(Color(hex: "#0d0c17"))
    }

    private var postHeader: some View {
        HStack(spacing: 10) {
            // Avatar
            Circle()
                .fill(LinearGradient(
                    colors: [Color(hex: "#2a2840"), Color(hex: "#1a1830")],
                    startPoint: .topLeading, endPoint: .bottomTrailing
                ))
                .frame(width: 36, height: 36)
                .overlay(
                    Text(item.gameType == "turtle_soup" ? "🐢" : "🔍")
                        .font(.system(size: 18))
                )
                .overlay(Circle().stroke(Color(hex: "#c9a84c").opacity(0.3), lineWidth: 1))

            VStack(alignment: .leading, spacing: 2) {
                Text(item.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                Text(item.gameType == "turtle_soup" ? "Turtle Soup" : "Murder Mystery")
                    .font(.system(size: 12))
                    .foregroundColor(Color(hex: "#44446a"))
            }

            Spacer()

            // Difficulty badge
            Text(localizedDifficulty(item.difficulty))
                .font(.system(size: 11, weight: .semibold))
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(difficultyColor.opacity(0.15))
                .foregroundColor(difficultyColor)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(difficultyColor.opacity(0.3), lineWidth: 1))
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    private var artworkPanel: some View {
        ZStack(alignment: .bottomLeading) {
            Rectangle()
                .fill(LinearGradient(
                    colors: gradientColors,
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ))
                .frame(maxWidth: .infinity)
                .frame(height: 240)
                .overlay(
                    // Subtle geometric pattern
                    Canvas { ctx, size in
                        for i in stride(from: 0, to: Int(size.width) + 80, by: 80) {
                            for j in stride(from: 0, to: Int(size.height) + 80, by: 80) {
                                let rect = CGRect(x: Double(i) - 40, y: Double(j) - 40, width: 80, height: 80)
                                ctx.stroke(Path(ellipseIn: rect), with: .color(.white.opacity(0.04)), lineWidth: 1)
                            }
                        }
                    }
                )

            // Bottom gradient overlay
            LinearGradient(
                colors: [Color.clear, Color.black.opacity(0.7)],
                startPoint: .center,
                endPoint: .bottom
            )
            .frame(maxWidth: .infinity)
            .frame(height: 240)

            // Title overlay
            VStack(alignment: .leading, spacing: 4) {
                Text(item.title)
                    .font(.system(size: 22, weight: .black, design: .serif))
                    .foregroundColor(.white)
                    .shadow(color: .black.opacity(0.6), radius: 4, x: 0, y: 2)
                if item.playerCount > 1 {
                    HStack(spacing: 4) {
                        Image(systemName: "person.2.fill")
                            .font(.system(size: 11))
                        Text("\(item.playerCount) players")
                            .font(.system(size: 12))
                    }
                    .foregroundColor(.white.opacity(0.7))
                }
            }
            .padding(16)
        }
        .clipped()
    }

    private var actionRow: some View {
        HStack(spacing: 0) {
            // Heart (like button)
            Button(action: onLike) {
                HStack(spacing: 6) {
                    Image(systemName: item.isLiked ? "heart.fill" : "heart")
                        .font(.system(size: 20))
                        .foregroundColor(item.isLiked ? Color(hex: "#f87171") : Color(hex: "#44446a"))
                        .scaleEffect(item.isLiked ? 1.1 : 1.0)
                        .animation(.spring(response: 0.2), value: item.isLiked)
                    Text("\(item.likeCount + (item.isLiked ? 1 : 0))")
                        .font(.system(size: 13))
                        .foregroundColor(Color(hex: "#44446a"))
                }
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)

            // Bookmark (save)
            Button(action: onSave) {
                Image(systemName: item.isSaved ? "bookmark.fill" : "bookmark")
                    .font(.system(size: 20))
                    .foregroundColor(item.isSaved ? Color(hex: "#c9a84c") : Color(hex: "#44446a"))
                    .frame(width: 44, height: 44)
            }

            Spacer()

            // Play button
            Button(action: onPlay) {
                HStack(spacing: 6) {
                    Image(systemName: "play.fill")
                        .font(.system(size: 13))
                    Text("Play")
                        .font(.system(size: 14, weight: .bold))
                }
                .foregroundColor(.black)
                .padding(.horizontal, 20).padding(.vertical, 10)
                .background(
                    LinearGradient(
                        colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .clipShape(Capsule())
            }
            .padding(.trailing, 16)
        }
        .padding(.vertical, 8)
    }

    private var descriptionRow: some View {
        HStack(spacing: 8) {
            if !item.tags.isEmpty {
                ForEach(item.tags.prefix(3), id: \.self) { tag in
                    Text("#\(tag)")
                        .font(.system(size: 12))
                        .foregroundColor(Color(hex: "#5555a0"))
                }
            }
            Spacer()
            Text("by \(item.author)")
                .font(.system(size: 11))
                .foregroundColor(Color(hex: "#2a2840"))
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 12)
    }

    private var difficultyColor: Color {
        switch normalizedDifficulty(item.difficulty) {
        case "easy": return Color(hex: "#34d399")
        case "hard": return Color(hex: "#f87171")
        default:     return Color(hex: "#c9a84c")
        }
    }
}

// MARK: - Shimmer modifier (loading skeleton)

private extension View {
    func shimmering() -> some View {
        self.overlay(
            LinearGradient(
                colors: [Color.clear, Color.white.opacity(0.06), Color.clear],
                startPoint: .leading,
                endPoint: .trailing
            )
            .rotationEffect(.degrees(30))
        )
    }
}
