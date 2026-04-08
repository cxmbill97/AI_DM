import SwiftUI

struct WaitingRoomView: View {
    let gameId: String
    let gameType: String
    @StateObject private var vm: WaitingRoomViewModel
    @EnvironmentObject private var tabBarState: TabBarVisibility
    @Environment(\.dismiss) private var dismiss

    // Navigation to actual game room once started
    @State private var navigateToGame = false

    init(gameId: String, gameType: String, roomId: String) {
        self.gameId = gameId
        self.gameType = gameType
        _vm = StateObject(wrappedValue: WaitingRoomViewModel(roomId: roomId, gameType: gameType))
    }

    var body: some View {
        ZStack {
            Color(hex: "#0a0a0f").ignoresSafeArea()

            VStack(spacing: 0) {
                navBar
                ScrollView(showsIndicators: false) {
                    VStack(spacing: 20) {
                        roomCodeCard
                        playerSlots
                        publicToggle
                        Spacer(minLength: 20)
                        actionButtons
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, 16)
                    .padding(.bottom, 32)
                }
            }
        }
        .navigationBarHidden(true)
        .navigationDestination(isPresented: $navigateToGame) {
            RoomView(roomId: vm.roomId)
        }
        .onAppear { tabBarState.isHidden = true }
        .onDisappear { tabBarState.isHidden = false }
        .task { await vm.connect() }
        .onChange(of: vm.started) { _ in
            if vm.started {
                vm.disconnect()   // release lobby WS before game room connects
                navigateToGame = true
            }
        }
        .alert("Error", isPresented: Binding(
            get: { vm.errorMessage != nil },
            set: { if !$0 { vm.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) { vm.errorMessage = nil }
        } message: {
            Text(vm.errorMessage ?? "")
        }
    }

    // MARK: - Nav bar

    private var navBar: some View {
        HStack {
            Button { dismiss() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color(hex: "#c9a84c"))
            }
            Spacer()
            Text("Waiting Room")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(.white)
            Spacer()
            ShareLink(item: URL(string: "aidm://room/\(vm.roomId)")!) {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color(hex: "#c9a84c"))
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 14)
        .background(Color(hex: "#0d0c17"))
        .overlay(Rectangle().frame(height: 0.5).foregroundColor(Color(hex: "#2a2840")), alignment: .bottom)
    }

    // MARK: - Room code card

    private var roomCodeCard: some View {
        VStack(spacing: 10) {
            Text("Room Code")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(Color(hex: "#44446a"))
                .textCase(.uppercase)
                .kerning(1.2)

            Text(vm.roomId)
                .font(.system(size: 32, weight: .black, design: .monospaced))
                .foregroundStyle(LinearGradient(
                    colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                    startPoint: .leading, endPoint: .trailing
                ))
                .kerning(6)

            Text("Share this code with friends to let them join")
                .font(.system(size: 12))
                .foregroundColor(Color(hex: "#44446a"))
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .padding(.horizontal, 20)
        .background(Color(hex: "#16151f"))
        .cornerRadius(16)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }

    // MARK: - Player slots

    private var playerSlots: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Players")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Color(hex: "#44446a"))
                    .textCase(.uppercase)
                    .kerning(1)
                Spacer()
                Text("\(vm.players.count)/\(vm.maxPlayers)")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(Color(hex: "#c9a84c"))
            }

            VStack(spacing: 8) {
                ForEach(0..<vm.maxPlayers, id: \.self) { idx in
                    if idx < vm.players.count {
                        PlayerSlotRow(player: vm.players[idx], isReady: vm.readyPlayerIds.contains(vm.players[idx].id))
                    } else {
                        EmptySlotRow()
                    }
                }
            }
        }
        .padding(16)
        .background(Color(hex: "#16151f"))
        .cornerRadius(16)
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color(hex: "#2a2840"), lineWidth: 1))
    }

    // MARK: - Public toggle

    private var publicToggle: some View {
        Button {
            Task { await vm.togglePublic() }
        } label: {
            HStack(spacing: 12) {
                Image(systemName: vm.isPublic ? "globe" : "lock.fill")
                    .font(.system(size: 18))
                    .foregroundColor(vm.isPublic ? Color(hex: "#60a5fa") : Color(hex: "#c9a84c"))
                    .frame(width: 28)
                VStack(alignment: .leading, spacing: 2) {
                    Text(vm.isPublic ? "Public Room" : "Private Room")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                    Text(vm.isPublic ? "Anyone can find and join" : "Only people with the code can join")
                        .font(.system(size: 12))
                        .foregroundColor(Color(hex: "#44446a"))
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 12))
                    .foregroundColor(Color(hex: "#44446a"))
            }
            .padding(16)
            .background(Color(hex: "#16151f"))
            .cornerRadius(16)
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color(hex: "2a2840"), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Action buttons

    @ViewBuilder
    private var actionButtons: some View {
        VStack(spacing: 12) {
            if vm.isHost {
                Button {
                    Task { await vm.startGame() }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "play.fill")
                            .font(.system(size: 14))
                        Text("Start Game")
                            .font(.system(size: 16, weight: .bold))
                    }
                    .foregroundColor(.black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(
                        vm.canStart
                            ? AnyShapeStyle(LinearGradient(colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                                                           startPoint: .leading, endPoint: .trailing))
                            : AnyShapeStyle(Color(hex: "#2a2840"))
                    )
                    .cornerRadius(14)
                }
                .disabled(!vm.canStart)
            } else {
                Button {
                    Task { await vm.sendReady() }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: vm.isReady ? "checkmark.circle.fill" : "hand.raised.fill")
                            .font(.system(size: 14))
                        Text(vm.isReady ? "Ready!" : "I'm Ready")
                            .font(.system(size: 16, weight: .bold))
                    }
                    .foregroundColor(vm.isReady ? Color(hex: "#34d399") : .black)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(
                        vm.isReady
                            ? AnyShapeStyle(Color(hex: "#16151f"))
                            : AnyShapeStyle(LinearGradient(colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                                                           startPoint: .leading, endPoint: .trailing))
                    )
                    .cornerRadius(14)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14)
                            .stroke(vm.isReady ? Color(hex: "#34d399") : Color.clear, lineWidth: 1.5)
                    )
                }
                .disabled(vm.isReady)
            }
        }
    }
}

// MARK: - Player slot row

private struct PlayerSlotRow: View {
    let player: PlayerInfo
    let isReady: Bool

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(Color(hex: "#2a2840"))
                .frame(width: 36, height: 36)
                .overlay(
                    Text(String(player.name.prefix(1)).uppercased())
                        .font(.system(size: 15, weight: .bold))
                        .foregroundColor(Color(hex: "#c9a84c"))
                )
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(player.name)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                    if player.is_host == true {
                        Text("Host")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.black)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color(hex: "#c9a84c"))
                            .cornerRadius(4)
                    }
                }
                if let character = player.character {
                    Text(character)
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#44446a"))
                }
            }
            Spacer()
            if isReady {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 18))
                    .foregroundColor(Color(hex: "#34d399"))
            } else {
                Image(systemName: "clock")
                    .font(.system(size: 16))
                    .foregroundColor(Color(hex: "#44446a"))
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Color(hex: "#0d0c17"))
        .cornerRadius(12)
    }
}

private struct EmptySlotRow: View {
    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .stroke(Color(hex: "#2a2840"), lineWidth: 1.5)
                .frame(width: 36, height: 36)
                .overlay(
                    Image(systemName: "plus")
                        .font(.system(size: 14))
                        .foregroundColor(Color(hex: "#2a2840"))
                )
            Text("Waiting for player…")
                .font(.system(size: 14))
                .foregroundColor(Color(hex: "#2a2840"))
            Spacer()
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Color(hex: "#0d0c17").opacity(0.5))
        .cornerRadius(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color(hex: "#1a1a2e"), style: StrokeStyle(lineWidth: 1, dash: [4, 4])))
    }
}
