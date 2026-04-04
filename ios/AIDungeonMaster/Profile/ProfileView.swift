import SwiftUI

struct ProfileView: View {
    @StateObject private var vm = ProfileViewModel()
    @EnvironmentObject var auth: AuthViewModel
    @State private var selectedTab = 0
    @State private var navigateToRoom: String? = nil
    @State private var isCreating = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0a0a0f").ignoresSafeArea()

                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        heroSection
                            .padding(.top, 20)
                            .padding(.bottom, 20)

                        statsSection
                            .padding(.horizontal, 20)
                            .padding(.bottom, 20)

                        // Tabs: Played / Liked
                        profileTabs
                            .padding(.bottom, 8)

                        // Content
                        if selectedTab == 0 {
                            playedGrid
                        } else {
                            likedGrid
                        }

                        signOutButton
                            .padding(.horizontal, 20)
                            .padding(.top, 24)
                            .padding(.bottom, 40)
                    }
                }

                if vm.isLoading {
                    ProgressView().tint(Color(hex: "#c9a84c"))
                }
            }
            .navigationBarHidden(true)
            .task { await vm.load() }
            .navigationDestination(isPresented: Binding(
                get: { navigateToRoom != nil },
                set: { if !$0 { navigateToRoom = nil } }
            )) {
                if let roomId = navigateToRoom { RoomView(roomId: roomId) }
            }
            .alert("Error", isPresented: Binding(
                get: { error != nil },
                set: { if !$0 { error = nil } }
            )) {
                Button("OK", role: .cancel) { error = nil }
            } message: {
                Text(error ?? "")
            }
        }
    }

    // MARK: - Hero

    private var heroSection: some View {
        VStack(spacing: 14) {
            ZStack {
                Circle()
                    .fill(RadialGradient(
                        colors: [Color(hex: "#c9a84c").opacity(0.2), Color.clear],
                        center: .center, startRadius: 0, endRadius: 55
                    ))
                    .frame(width: 110, height: 110)

                Circle()
                    .fill(LinearGradient(
                        colors: [Color(hex: "#2a2840"), Color(hex: "#1a1830")],
                        startPoint: .topLeading, endPoint: .bottomTrailing
                    ))
                    .frame(width: 86, height: 86)
                    .overlay(Circle().stroke(
                        LinearGradient(colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")], startPoint: .top, endPoint: .bottom),
                        lineWidth: 2
                    ))

                Text(vm.displayName.prefix(1).uppercased())
                    .font(.system(size: 36, weight: .black, design: .serif))
                    .foregroundStyle(LinearGradient(
                        colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                        startPoint: .top, endPoint: .bottom
                    ))
            }

            VStack(spacing: 4) {
                Text(vm.displayName.isEmpty ? "Player" : vm.displayName)
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(.white)
                if !vm.email.isEmpty {
                    Text(vm.email)
                        .font(.system(size: 13))
                        .foregroundColor(Color(hex: "#44446a"))
                }
            }
        }
    }

    // MARK: - Stats (Instagram-style: Posts · Followers · Following)

    private var statsSection: some View {
        HStack(spacing: 0) {
            StatPill(value: "\(vm.history.count)", label: "Games Played")
            Divider().frame(height: 30).background(Color(hex: "#2a2840"))
            StatPill(value: "\(vm.history.filter { $0.game_type == "turtle_soup" }.count)", label: "Soups")
            Divider().frame(height: 30).background(Color(hex: "#2a2840"))
            StatPill(value: "\(vm.history.filter { $0.game_type == "murder_mystery" }.count)", label: "Mysteries")
        }
        .padding(.vertical, 14)
        .background(Color(hex: "#16151f"))
        .cornerRadius(16)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }

    // MARK: - Profile tabs (Instagram-style icon switcher)

    private var profileTabs: some View {
        HStack(spacing: 0) {
            tabButton(icon: "clock.fill", index: 0, label: "Played")
            tabButton(icon: "heart.fill", index: 1, label: "Liked")
        }
        .padding(.horizontal, 20)
    }

    private func tabButton(icon: String, index: Int, label: String) -> some View {
        Button {
            withAnimation(.spring(response: 0.3)) { selectedTab = index }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                Text(label)
                    .font(.system(size: 13, weight: .semibold))
            }
            .foregroundColor(selectedTab == index ? Color(hex: "#c9a84c") : Color(hex: "#44446a"))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(Color.clear)
            .overlay(
                Rectangle()
                    .frame(height: 2)
                    .foregroundColor(selectedTab == index ? Color(hex: "#c9a84c") : Color.clear),
                alignment: .bottom
            )
        }
        .buttonStyle(.plain)
    }

    // MARK: - Played history

    @ViewBuilder
    private var playedGrid: some View {
        if vm.history.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "clock.badge.xmark")
                    .font(.system(size: 36))
                    .foregroundColor(Color(hex: "#2a2840"))
                Text("No games played yet")
                    .font(.system(size: 14))
                    .foregroundColor(Color(hex: "#44446a"))
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 40)
        } else {
            LazyVStack(spacing: 10) {
                ForEach(vm.history) { item in
                    HistoryRow(item: item)
                        .padding(.horizontal, 20)
                }
            }
            .padding(.top, 4)
        }
    }

    // MARK: - Liked

    @ViewBuilder
    private var likedGrid: some View {
        if vm.likedItems.isEmpty {
            VStack(spacing: 12) {
                Image(systemName: "heart.slash")
                    .font(.system(size: 36))
                    .foregroundColor(Color(hex: "#2a2840"))
                Text("No liked games yet")
                    .font(.system(size: 14))
                    .foregroundColor(Color(hex: "#44446a"))
                Text("Tap the ♥ on any game in your feed to like it.")
                    .font(.system(size: 12))
                    .foregroundColor(Color(hex: "#2a2840"))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 40)
        } else {
            LazyVStack(spacing: 10) {
                ForEach(vm.likedItems) { fav in
                    LikedRow(fav: fav) {
                        createAndNavigateFromFav(fav)
                    }
                    .padding(.horizontal, 20)
                }
            }
            .padding(.top, 4)
        }
    }

    private func createAndNavigateFromFav(_ fav: FavoriteItem) {
        guard !isCreating else { return }
        isCreating = true
        let gameId = fav.item_id
        let gameType = fav.item_type == "puzzle_like" ? "turtle_soup" : "murder_mystery"
        let lang = UserDefaults.standard.string(forKey: "lang") ?? "zh"
        Task {
            defer { isCreating = false }
            do {
                let resp = try await APIService.shared.createRoom(gameId: gameId, gameType: gameType, lang: lang, isPublic: false)
                navigateToRoom = resp.room_id
            } catch { self.error = error.localizedDescription }
        }
    }

    // MARK: - Sign out

    private var signOutButton: some View {
        Button { auth.signOut() } label: {
            HStack(spacing: 8) {
                Image(systemName: "rectangle.portrait.and.arrow.right")
                Text("Sign Out")
                    .font(.system(size: 14, weight: .semibold))
            }
            .foregroundColor(Color(hex: "#f87171"))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(Color(hex: "#f87171").opacity(0.08))
            .cornerRadius(14)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#f87171").opacity(0.25), lineWidth: 1))
        }
    }
}

// MARK: - StatPill

private struct StatPill: View {
    let value: String
    let label: String

    var body: some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.system(size: 20, weight: .black))
                .foregroundColor(.white)
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(Color(hex: "#44446a"))
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - HistoryRow

private struct HistoryRow: View {
    let item: HistoryItem

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
            RoundedRectangle(cornerRadius: 10)
                .fill(LinearGradient(colors: gradientColors, startPoint: .topLeading, endPoint: .bottomTrailing))
                .frame(width: 56, height: 56)
                .overlay(
                    Text(item.game_type == "turtle_soup" ? "🐢" : "🔍")
                        .font(.system(size: 24))
                )

            VStack(alignment: .leading, spacing: 4) {
                Text(item.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                HStack(spacing: 8) {
                    Text(item.game_type == "turtle_soup" ? "Turtle Soup" : "Murder Mystery")
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#5555a0"))
                    Text(shortDate(item.played_at))
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#2a2840"))
                }
            }

            Spacer()

            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 20))
                .foregroundColor(Color(hex: "#34d399").opacity(0.6))
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(Color(hex: "#16151f"))
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }

    private func shortDate(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: iso) {
            let rel = RelativeDateTimeFormatter()
            rel.unitsStyle = .abbreviated
            return rel.localizedString(for: date, relativeTo: Date())
        }
        return String(iso.prefix(10))
    }
}

// MARK: - LikedRow

private struct LikedRow: View {
    let fav: FavoriteItem
    let onPlay: () -> Void

    private var isSOup: Bool { fav.item_type == "puzzle_like" }

    private var gradientColors: [Color] {
        let hues: [(Double, Double)] = [
            (0.05, 0.15), (0.55, 0.65), (0.3, 0.4),
            (0.7, 0.8), (0.15, 0.25), (0.45, 0.55)
        ]
        let pair = hues[abs(fav.item_id.hashValue) % hues.count]
        return [Color(hue: pair.0, saturation: 0.5, brightness: 0.3), Color(hue: pair.1, saturation: 0.6, brightness: 0.2)]
    }

    var body: some View {
        HStack(spacing: 14) {
            RoundedRectangle(cornerRadius: 10)
                .fill(LinearGradient(colors: gradientColors, startPoint: .topLeading, endPoint: .bottomTrailing))
                .frame(width: 56, height: 56)
                .overlay(
                    Text(isSOup ? "🐢" : "🔍")
                        .font(.system(size: 24))
                )

            VStack(alignment: .leading, spacing: 4) {
                Text(isSOup ? "Turtle Soup" : "Murder Mystery")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Text(fav.item_id)
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#5555a0"))
                    .lineLimit(1)
            }

            Spacer()

            Button(action: onPlay) {
                HStack(spacing: 4) {
                    Image(systemName: "play.fill")
                        .font(.system(size: 11))
                    Text("Play")
                        .font(.system(size: 12, weight: .bold))
                }
                .foregroundColor(.black)
                .padding(.horizontal, 14).padding(.vertical, 8)
                .background(LinearGradient(
                    colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                    startPoint: .topLeading, endPoint: .bottomTrailing
                ))
                .clipShape(Capsule())
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(Color(hex: "#16151f"))
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }
}
