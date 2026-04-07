import SwiftUI

struct ExploreView: View {
    @StateObject private var vm = ExploreViewModel()
    @State private var navigateToRoom: String? = nil
    @State private var joinCode = ""
    @State private var showBrowse = false

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0a0a0f").ignoresSafeArea()

                VStack(spacing: 0) {
                    exploreHeader

                    // Join-by-code strip
                    joinStrip
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)

                    // Room list
                    List {
                        if vm.rooms.isEmpty && !vm.isLoading {
                            emptyState
                                .listRowBackground(Color.clear)
                                .listRowSeparator(.hidden)
                        } else {
                            ForEach(vm.rooms) { room in
                                RoomRow(room: room) {
                                    navigateToRoom = room.room_id
                                }
                                .listRowBackground(Color.clear)
                                .listRowSeparator(.hidden)
                                .listRowInsets(EdgeInsets(top: 5, leading: 16, bottom: 5, trailing: 16))
                            }
                        }
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                    .refreshable { await vm.load() }
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(isPresented: Binding(
                get: { navigateToRoom != nil },
                set: { if !$0 { navigateToRoom = nil } }
            )) {
                if let roomId = navigateToRoom { RoomView(roomId: roomId) }
            }
            .sheet(isPresented: $showBrowse) {
                LobbyView()
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

    // MARK: - Header

    private var exploreHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Explore")
                    .font(.system(size: 22, weight: .black, design: .serif))
                    .foregroundStyle(LinearGradient(
                        colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                        startPoint: .leading, endPoint: .trailing
                    ))
                Text("Live rooms · pull down to refresh")
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#44446a"))
            }
            Spacer()
            // Browse games button
            Button {
                showBrowse = true
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "square.grid.2x2")
                        .font(.system(size: 12))
                    Text("Browse")
                        .font(.system(size: 13, weight: .semibold))
                }
                .foregroundColor(Color(hex: "#c9a84c"))
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(Color(hex: "#c9a84c").opacity(0.12))
                .clipShape(Capsule())
                .overlay(Capsule().stroke(Color(hex: "#c9a84c").opacity(0.3), lineWidth: 1))
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 12)
        .padding(.bottom, 4)
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
                joinCode = ""
                navigateToRoom = code
            }
            .font(.system(size: 14, weight: .bold))
            .foregroundColor(.black)
            .padding(.horizontal, 20).padding(.vertical, 11)
            .background(Color(hex: "#c9a84c"))
            .cornerRadius(11)
        }
    }

    // MARK: - Empty state

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "door.left.hand.open")
                .font(.system(size: 44))
                .foregroundColor(Color(hex: "#2a2840"))
            Text("No active rooms")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(Color(hex: "#44446a"))
            Text("Be the first to play — tap Browse to start a game.")
                .font(.system(size: 13))
                .foregroundColor(Color(hex: "#2a2840"))
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
            Button {
                showBrowse = true
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "square.grid.2x2")
                    Text("Browse Games")
                        .font(.system(size: 14, weight: .semibold))
                }
                .foregroundColor(.black)
                .padding(.horizontal, 24).padding(.vertical, 12)
                .background(Color(hex: "#c9a84c"))
                .clipShape(Capsule())
            }
            .padding(.top, 4)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 60)
    }
}

// MARK: - ExploreViewModel

@MainActor
final class ExploreViewModel: ObservableObject {
    @Published var rooms: [ActiveRoom] = []
    @Published var isLoading = false
    @Published var error: String?

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            rooms = try await APIService.shared.getActiveRooms()
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - RoomRow

private struct RoomRow: View {
    let room: ActiveRoom
    let onJoin: () -> Void

    private var gradientColors: [Color] {
        let hues: [(Double, Double)] = [
            (0.05, 0.15), (0.55, 0.65), (0.3, 0.4),
            (0.7, 0.8), (0.15, 0.25), (0.45, 0.55)
        ]
        let pair = hues[abs(room.title.hashValue) % hues.count]
        return [Color(hue: pair.0, saturation: 0.5, brightness: 0.3), Color(hue: pair.1, saturation: 0.6, brightness: 0.2)]
    }

    var body: some View {
        HStack(spacing: 14) {
            // Game type thumbnail
            RoundedRectangle(cornerRadius: 10)
                .fill(LinearGradient(colors: gradientColors, startPoint: .topLeading, endPoint: .bottomTrailing))
                .frame(width: 58, height: 58)
                .overlay(
                    Text(room.game_type == "turtle_soup" ? "🐢" : "🔍")
                        .font(.system(size: 26))
                )

            VStack(alignment: .leading, spacing: 6) {
                Text(room.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(1)

                HStack(spacing: 10) {
                    // Game type badge
                    Text(room.game_type == "turtle_soup" ? "Turtle Soup" : "Murder Mystery")
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#5555a0"))

                    // Player dots
                    playerDots
                }

                // Room code
                HStack(spacing: 4) {
                    Image(systemName: "key.fill")
                        .font(.system(size: 10))
                    Text(room.room_id)
                        .font(.system(size: 11, design: .monospaced))
                }
                .foregroundColor(Color(hex: "#2a2840"))
            }

            Spacer()

            Button(action: onJoin) {
                Text("Join")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(.black)
                    .padding(.horizontal, 16).padding(.vertical, 9)
                    .background(Color(hex: "#c9a84c"))
                    .clipShape(Capsule())
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(Color(hex: "#16151f"))
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }

    private var playerDots: some View {
        let capacity = max(room.player_count, 1)
        return HStack(spacing: 4) {
            ForEach(0..<capacity, id: \.self) { i in
                Circle()
                    .fill(i < room.connected_count
                        ? Color(hex: "#34d399")
                        : Color(hex: "#44446a")
                    )
                    .frame(width: 8, height: 8)
            }
            Text("\(room.connected_count)/\(capacity)")
                .font(.system(size: 11))
                .foregroundColor(Color(hex: "#44446a"))
        }
    }
}
