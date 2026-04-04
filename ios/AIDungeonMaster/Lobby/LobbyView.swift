import SwiftUI

struct LobbyView: View {
    @EnvironmentObject private var auth: AuthViewModel
    @StateObject private var vm = LobbyViewModel()
    @State private var joinCode = ""
    @State private var navigateToRoom: String? = nil
    @State private var isCreating = false

    let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0a0a0f").ignoresSafeArea()

                VStack(spacing: 0) {
                    // Header
                    headerView

                    // Join strip
                    joinStrip
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)

                    // Tabs
                    tabBar
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)

                    // Search
                    searchBar
                        .padding(.horizontal, 16)
                        .padding(.bottom, 12)

                    // Content
                    ScrollView {
                        gameGrid
                            .padding(.horizontal, 16)
                            .padding(.bottom, 24)
                    }
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(isPresented: Binding(
                get: { navigateToRoom != nil },
                set: { if !$0 { navigateToRoom = nil } }
            )) {
                if let roomId = navigateToRoom {
                    RoomView(roomId: roomId)
                }
            }
            .task {
                await vm.load()
                #if DEBUG
                if let roomId = auth.debugRoomId {
                    auth.debugRoomId = nil
                    navigateToRoom = roomId
                }
                #endif
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

    // MARK: - Header

    private var headerView: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("AI DM")
                    .font(.system(size: 22, weight: .black, design: .serif))
                    .foregroundStyle(LinearGradient(
                        colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                        startPoint: .leading, endPoint: .trailing
                    ))
                Text("Choose your adventure")
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#44446a"))
            }
            Spacer()
            if vm.isLoading {
                ProgressView()
                    .tint(Color(hex: "#c9a84c"))
                    .scaleEffect(0.8)
            } else {
                Button { Task { await vm.load() } } label: {
                    Image(systemName: "arrow.clockwise")
                        .font(.system(size: 14))
                        .foregroundColor(Color(hex: "#44446a"))
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 8)
        .padding(.bottom, 10)
    }

    // MARK: - Join strip

    private var joinStrip: some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "key.fill")
                    .font(.system(size: 12))
                    .foregroundColor(Color(hex: "#c9a84c").opacity(0.6))
                TextField("Room code (e.g. ABC123)", text: $joinCode)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.white)
                    .autocapitalization(.allCharacters)
                    .disableAutocorrection(true)
            }
            .padding(.horizontal, 12).padding(.vertical, 11)
            .background(Color(hex: "#16151f"))
            .cornerRadius(11)
            .overlay(RoundedRectangle(cornerRadius: 11).stroke(Color(hex: "#2a2840"), lineWidth: 1))

            Button("Join") {
                let code = joinCode.trimmingCharacters(in: .whitespaces).uppercased()
                guard !code.isEmpty else { return }
                navigateToRoom = code
            }
            .font(.system(size: 14, weight: .bold))
            .foregroundColor(.black)
            .padding(.horizontal, 20).padding(.vertical, 11)
            .background(Color(hex: "#c9a84c"))
            .cornerRadius(11)
        }
    }

    // MARK: - Tab bar

    private var tabBar: some View {
        HStack(spacing: 8) {
            ForEach(LobbyViewModel.GameTab.allCases, id: \.self) { tab in
                Button {
                    withAnimation(.spring(response: 0.3)) { vm.selectedTab = tab }
                } label: {
                    HStack(spacing: 6) {
                        Text(tab.icon)
                            .font(.system(size: 14))
                        Text(tab.label)
                            .font(.system(size: 13, weight: .semibold))
                    }
                    .foregroundColor(vm.selectedTab == tab ? .black : Color(hex: "#5555a0"))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 9)
                    .background(vm.selectedTab == tab
                        ? AnyShapeStyle(LinearGradient(colors: [Color(hex: "#e8c96a"), Color(hex: "#c9a84c")], startPoint: .topLeading, endPoint: .bottomTrailing))
                        : AnyShapeStyle(Color(hex: "#16151f"))
                    )
                    .cornerRadius(10)
                    .overlay(RoundedRectangle(cornerRadius: 10)
                        .stroke(vm.selectedTab == tab ? Color.clear : Color(hex: "#2a2840"), lineWidth: 1))
                }
            }
        }
    }

    // MARK: - Search

    private var searchBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 13))
                .foregroundColor(Color(hex: "#44446a"))
            TextField("Search…", text: $vm.search)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundColor(.white)
            if !vm.search.isEmpty {
                Button { vm.search = "" } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 14))
                        .foregroundColor(Color(hex: "#44446a"))
                }
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Color(hex: "#16151f"))
        .cornerRadius(11)
        .overlay(RoundedRectangle(cornerRadius: 11).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }

    // MARK: - Grid

    @ViewBuilder
    private var gameGrid: some View {
        let items = vm.selectedTab == .turtleSoup ? vm.filteredPuzzles.map(AnyGame.puzzle) : vm.filteredScripts.map(AnyGame.script)

        if items.isEmpty && !vm.isLoading {
            VStack(spacing: 12) {
                Image(systemName: "eyes.inverse")
                    .font(.system(size: 36))
                    .foregroundColor(Color(hex: "#2a2840"))
                Text("Nothing found")
                    .font(.system(size: 14))
                    .foregroundColor(Color(hex: "#44446a"))
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 60)
        } else {
            LazyVGrid(columns: columns, spacing: 14) {
                ForEach(items) { item in
                    GameCardView(
                        title: item.title,
                        difficulty: item.difficulty,
                        tags: item.tags,
                        gameType: item.gameType,
                        itemId: item.id,
                        isFavorite: vm.favorites.contains(item.favoriteKey),
                        onFavorite: { vm.toggleFavorite(type: item.favType, id: item.id) },
                        onSolo: { createAndNavigate(gameId: item.id, gameType: item.gameType) },
                        onCreateRoom: { createAndNavigate(gameId: item.id, gameType: item.gameType) }
                    )
                }
            }
        }
    }

    private func createAndNavigate(gameId: String, gameType: String) {
        guard !isCreating else { return }
        isCreating = true
        let lang = UserDefaults.standard.string(forKey: "lang") ?? "zh"
        Task {
            defer { isCreating = false }
            do {
                let resp = try await APIService.shared.createRoom(gameId: gameId, gameType: gameType, lang: lang)
                navigateToRoom = resp.room_id
            } catch {
                vm.error = error.localizedDescription
            }
        }
    }
}

// MARK: - AnyGame helper (unifies PuzzleSummary + ScriptSummary)

private enum AnyGame: Identifiable {
    case puzzle(PuzzleSummary)
    case script(ScriptSummary)

    var id: String {
        switch self { case .puzzle(let p): return p.id; case .script(let s): return s.id }
    }
    var title: String {
        switch self { case .puzzle(let p): return p.title; case .script(let s): return s.title }
    }
    var difficulty: String {
        switch self { case .puzzle(let p): return p.difficulty; case .script(let s): return s.difficulty }
    }
    var tags: [String] {
        switch self { case .puzzle(let p): return p.tags; case .script: return [] }
    }
    var gameType: String {
        switch self { case .puzzle: return "turtle_soup"; case .script: return "murder_mystery" }
    }
    var favoriteKey: String {
        switch self { case .puzzle(let p): return "puzzle:\(p.id)"; case .script(let s): return "script:\(s.id)" }
    }
    var favType: String {
        switch self { case .puzzle: return "puzzle"; case .script: return "script" }
    }
}
