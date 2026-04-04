import SwiftUI

struct LobbyView: View {
    @StateObject private var vm = LobbyViewModel()
    @State private var joinRoomCode = ""
    @State private var navigateToRoom: String?

    let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0d0d0f").ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 0) {
                        // Join strip
                        HStack(spacing: 8) {
                            TextField("Room code (e.g. ABC123)", text: $joinRoomCode)
                                .textFieldStyle(.plain)
                                .padding(.horizontal, 12).padding(.vertical, 10)
                                .background(Color(hex: "#141420"))
                                .cornerRadius(8)
                                .foregroundColor(.white)
                                .font(.system(size: 14))
                                .autocapitalization(.allCharacters)
                                .disableAutocorrection(true)
                            Button("Join") {
                                if !joinRoomCode.trimmingCharacters(in: .whitespaces).isEmpty {
                                    navigateToRoom = joinRoomCode.uppercased().trimmingCharacters(in: .whitespaces)
                                }
                            }
                            .padding(.horizontal, 16).padding(.vertical, 10)
                            .background(Color(hex: "#c9a84c"))
                            .foregroundColor(.black)
                            .font(.system(size: 14, weight: .semibold))
                            .cornerRadius(8)
                            .disabled(joinRoomCode.trimmingCharacters(in: .whitespaces).isEmpty)
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)

                        // Search
                        HStack {
                            Image(systemName: "magnifyingglass")
                                .foregroundColor(Color(hex: "#666680"))
                            TextField("Search", text: $vm.search)
                                .foregroundColor(.white)
                                .font(.system(size: 14))
                        }
                        .padding(.horizontal, 12).padding(.vertical, 10)
                        .background(Color(hex: "#141420"))
                        .cornerRadius(8)
                        .padding(.horizontal, 16)
                        .padding(.bottom, 12)

                        // Tabs
                        HStack(spacing: 0) {
                            tabButton("🐢 Turtle Soup", tab: .turtleSoup)
                            tabButton("🔍 Murder Mystery", tab: .murderMystery)
                        }
                        .padding(.horizontal, 16)
                        .padding(.bottom, 16)

                        // Grid
                        if vm.isLoading {
                            ProgressView()
                                .tint(Color(hex: "#c9a84c"))
                                .padding(.top, 60)
                        } else if vm.selectedTab == .turtleSoup {
                            if vm.filteredPuzzles.isEmpty {
                                Text("No puzzles found")
                                    .foregroundColor(Color(hex: "#666680"))
                                    .padding(.top, 60)
                            } else {
                                LazyVGrid(columns: columns, spacing: 12) {
                                    ForEach(vm.filteredPuzzles) { puzzle in
                                        GameCardView(
                                            title: puzzle.title,
                                            difficulty: puzzle.difficulty,
                                            tags: puzzle.tags,
                                            gameType: "turtle_soup",
                                            itemId: puzzle.id,
                                            isFavorite: vm.favorites.contains("puzzle:\(puzzle.id)"),
                                            onFavorite: { vm.toggleFavorite(type: "puzzle", id: puzzle.id) },
                                            onSolo: { createAndNavigate(gameId: puzzle.id, gameType: "turtle_soup") },
                                            onCreateRoom: { createAndNavigate(gameId: puzzle.id, gameType: "turtle_soup") }
                                        )
                                    }
                                }
                                .padding(.horizontal, 16)
                            }
                        } else {
                            if vm.filteredScripts.isEmpty {
                                Text("No scripts found")
                                    .foregroundColor(Color(hex: "#666680"))
                                    .padding(.top, 60)
                            } else {
                                LazyVGrid(columns: columns, spacing: 12) {
                                    ForEach(vm.filteredScripts) { script in
                                        GameCardView(
                                            title: script.title,
                                            difficulty: script.difficulty,
                                            tags: [],
                                            gameType: "murder_mystery",
                                            itemId: script.id,
                                            isFavorite: vm.favorites.contains("script:\(script.id)"),
                                            onFavorite: { vm.toggleFavorite(type: "script", id: script.id) },
                                            onSolo: { createAndNavigate(gameId: script.id, gameType: "murder_mystery") },
                                            onCreateRoom: { createAndNavigate(gameId: script.id, gameType: "murder_mystery") }
                                        )
                                    }
                                }
                                .padding(.horizontal, 16)
                            }
                        }
                        Spacer(minLength: 32)
                    }
                }
            }
            .navigationTitle("Browse Games")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(hex: "#0d0d0f"), for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .navigationDestination(isPresented: Binding(
                get: { navigateToRoom != nil },
                set: { if !$0 { navigateToRoom = nil } }
            )) {
                if let roomId = navigateToRoom {
                    RoomView(roomId: roomId)
                }
            }
            .task { await vm.load() }
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

    private func tabButton(_ label: String, tab: LobbyViewModel.GameTab) -> some View {
        Button(label) { vm.selectedTab = tab }
            .font(.system(size: 13, weight: .medium))
            .foregroundColor(vm.selectedTab == tab ? Color(hex: "#c9a84c") : Color(hex: "#666680"))
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity)
            .background(vm.selectedTab == tab ? Color(hex: "#1e1e10") : Color.clear)
            .cornerRadius(8)
    }

    private func createAndNavigate(gameId: String, gameType: String) {
        Task {
            if let roomId = await vm.createRoom(gameId: gameId, gameType: gameType) {
                navigateToRoom = roomId
            }
        }
    }
}
