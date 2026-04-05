import SwiftUI

struct ActivityView: View {
    @StateObject private var vm = ActivityViewModel()
    @State private var navigateToRoom: String? = nil
    @State private var isCreating = false
    @State private var showGameModeSheet = false
    @State private var pendingGameId: String? = nil
    @State private var pendingGameType: String = "murder_mystery"

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0a0a0f").ignoresSafeArea()

                ScrollView(showsIndicators: false) {
                    VStack(spacing: 0) {
                        // Header
                        activityHeader
                            .padding(.top, 8)

                        if vm.isLoading && vm.scripts.isEmpty {
                            VStack(spacing: 16) {
                                ForEach(0..<4, id: \.self) { _ in
                                    RoundedRectangle(cornerRadius: 16)
                                        .fill(Color(hex: "#16151f"))
                                        .frame(height: 88)
                                        .padding(.horizontal, 16)
                                }
                            }
                            .padding(.top, 8)
                        } else {
                            // Trending section
                            sectionHeader("🔥 Trending Now")
                                .padding(.top, 16)

                            LazyVStack(spacing: 10) {
                                ForEach(Array(vm.scripts.prefix(5).enumerated()), id: \.element.id) { idx, script in
                                    TrendingRow(rank: idx + 1, script: script) {
                                        showModeSheet(gameId: script.script_id, gameType: "murder_mystery")
                                    }
                                    .padding(.horizontal, 16)
                                }
                            }
                            .padding(.top, 8)

                            // All community section
                            sectionHeader("📚 Community Scripts")
                                .padding(.top, 24)

                            LazyVStack(spacing: 10) {
                                ForEach(vm.scripts.dropFirst(5)) { script in
                                    CommunityRow(script: script) {
                                        showModeSheet(gameId: script.script_id, gameType: "murder_mystery")
                                    }
                                    .padding(.horizontal, 16)
                                }
                            }
                            .padding(.top, 8)
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
                if let gameId = pendingGameId {
                    GameModeSheet { isPublic in
                        showGameModeSheet = false
                        createAndNavigate(gameId: gameId, gameType: pendingGameType, isPublic: isPublic)
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

    private var activityHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Activity")
                    .font(.system(size: 22, weight: .black, design: .serif))
                    .foregroundStyle(LinearGradient(
                        colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                        startPoint: .leading, endPoint: .trailing
                    ))
                Text("What the community is playing")
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#44446a"))
            }
            Spacer()
            if vm.isLoading {
                ProgressView().tint(Color(hex: "#c9a84c")).scaleEffect(0.8)
            } else {
                Button { Task { await vm.load() } } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 14))
                        .foregroundColor(Color(hex: "#44446a"))
                }
            }
        }
        .padding(.horizontal, 16)
    }

    private func sectionHeader(_ title: String) -> some View {
        HStack {
            Text(title)
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(.white)
            Spacer()
        }
        .padding(.horizontal, 16)
    }

    private func showModeSheet(gameId: String, gameType: String) {
        pendingGameId = gameId
        pendingGameType = gameType
        showGameModeSheet = true
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

// MARK: - ActivityViewModel

@MainActor
final class ActivityViewModel: ObservableObject {
    @Published var scripts: [CommunityScript] = []
    @Published var isLoading = false
    @Published var error: String?

    var lang: String { UserDefaults.standard.string(forKey: "lang") ?? "zh" }

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            scripts = try await APIService.shared.getCommunityScripts(lang: lang, limit: 50)
            scripts.sort { ($0.likes) > ($1.likes) }
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - TrendingRow

private struct TrendingRow: View {
    let rank: Int
    let script: CommunityScript
    let onPlay: () -> Void

    var body: some View {
        HStack(spacing: 14) {
            // Rank
            Text("#\(rank)")
                .font(.system(size: 18, weight: .black, design: .serif))
                .foregroundStyle(rank <= 3
                    ? LinearGradient(colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")], startPoint: .top, endPoint: .bottom)
                    : LinearGradient(colors: [Color(hex: "#2a2840"), Color(hex: "#2a2840")], startPoint: .top, endPoint: .bottom)
                )
                .frame(width: 32)

            VStack(alignment: .leading, spacing: 4) {
                Text(script.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                HStack(spacing: 8) {
                    if !script.author.isEmpty {
                        Label(script.author, systemImage: "person.fill")
                            .font(.system(size: 11))
                            .foregroundColor(Color(hex: "#44446a"))
                    }
                    Label("\(script.likes)", systemImage: "heart.fill")
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#f87171").opacity(0.7))
                }
            }

            Spacer()

            Button(action: onPlay) {
                Image(systemName: "play.fill")
                    .font(.system(size: 13))
                    .foregroundColor(.black)
                    .frame(width: 36, height: 36)
                    .background(Color(hex: "#c9a84c"))
                    .clipShape(Circle())
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(Color(hex: "#16151f"))
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }
}

// MARK: - CommunityRow

private struct CommunityRow: View {
    let script: CommunityScript
    let onPlay: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(LinearGradient(
                    colors: [Color(hex: "#2a2840"), Color(hex: "#1a1830")],
                    startPoint: .topLeading, endPoint: .bottomTrailing
                ))
                .frame(width: 44, height: 44)
                .overlay(Text("🔍").font(.system(size: 20)))

            VStack(alignment: .leading, spacing: 4) {
                Text(script.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                HStack(spacing: 10) {
                    Text(localizedDifficulty(script.difficulty))
                        .font(.system(size: 11))
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(Color(hex: "#1e1c2e"))
                        .foregroundColor(Color(hex: "#5555a0"))
                        .clipShape(Capsule())
                    Label("\(script.player_count)p", systemImage: "person.2.fill")
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#44446a"))
                    Label("\(script.likes)", systemImage: "heart.fill")
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#f87171").opacity(0.6))
                }
            }

            Spacer()

            Button(action: onPlay) {
                Text("Play")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.black)
                    .padding(.horizontal, 14).padding(.vertical, 8)
                    .background(Color(hex: "#c9a84c"))
                    .clipShape(Capsule())
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(Color(hex: "#16151f"))
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }
}
