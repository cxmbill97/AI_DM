import SwiftUI

struct RoomView: View {
    let roomId: String
    @StateObject private var vm: RoomViewModel
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var tabBarState: TabBarVisibility

    init(roomId: String) {
        self.roomId = roomId
        _vm = StateObject(wrappedValue: RoomViewModel(roomId: roomId))
    }

    var body: some View {
        ZStack {
            Color(hex: "#0a0a0f").ignoresSafeArea()

            VStack(spacing: 0) {
                navBar
                if !vm.phase.isEmpty || vm.truthProgress > 0 {
                    statusStrip
                }
                messageList
                if vm.gameWon {
                    winBanner
                } else {
                    inputBar
                }
            }
        }
        .navigationBarHidden(true)
        .onAppear { tabBarState.isHidden = true }
        .onDisappear { tabBarState.isHidden = false }
        .task { await vm.connect() }
        .onDisappear { vm.disconnect() }
        .sheet(isPresented: $vm.showClues) { ClueSheet(clues: vm.clues) }
        .alert("Error", isPresented: Binding(
            get: { vm.errorMessage != nil },
            set: { if !$0 { vm.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) { vm.errorMessage = nil }
        } message: { Text(vm.errorMessage ?? "") }
    }

    // MARK: - Nav bar

    private var navBar: some View {
        HStack(spacing: 12) {
            Button { dismiss() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Color(hex: "#c9a84c"))
                    .padding(8)
                    .background(Color(hex: "#1e1c2e"))
                    .clipShape(Circle())
            }

            VStack(alignment: .leading, spacing: 1) {
                Text(vm.gameTitle.isEmpty ? "Room \(roomId)" : vm.gameTitle)
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(.white)
                    .lineLimit(1)
                HStack(spacing: 5) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 5, height: 5)
                    Text(statusText)
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#5555a0"))
                }
            }

            Spacer()

            // Players count
            if !vm.players.isEmpty {
                HStack(spacing: -6) {
                    ForEach(vm.players.prefix(3)) { p in
                        Text(p.name.prefix(1).uppercased())
                            .font(.system(size: 10, weight: .bold))
                            .foregroundColor(.white)
                            .frame(width: 24, height: 24)
                            .background(avatarColor(p.name))
                            .clipShape(Circle())
                            .overlay(Circle().stroke(Color(hex: "#0a0a0f"), lineWidth: 1.5))
                    }
                }
            }

            // Clues button
            if !vm.clues.isEmpty {
                Button { vm.showClues = true } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "sparkles")
                            .font(.system(size: 11))
                        Text("\(vm.clues.count)")
                            .font(.system(size: 12, weight: .bold))
                    }
                    .foregroundColor(Color(hex: "#c9a84c"))
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .background(Color(hex: "#c9a84c").opacity(0.12))
                    .cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color(hex: "#c9a84c").opacity(0.3), lineWidth: 1))
                }
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(Color(hex: "#0d0c16"))
    }

    private var statusColor: Color {
        vm.isConnected ? Color(hex: "#34d399") : (vm.isReconnecting ? Color(hex: "#fbbf24") : Color(hex: "#f87171"))
    }

    private var statusText: String {
        if vm.isConnected { return "\(vm.players.count) online" }
        if vm.isReconnecting { return "Reconnecting…" }
        return "Disconnected"
    }

    // MARK: - Status strip

    private var statusStrip: some View {
        VStack(spacing: 6) {
            HStack {
                if !vm.phase.isEmpty {
                    Label(vm.phase.replacingOccurrences(of: "_", with: " ").capitalized,
                          systemImage: "circle.fill")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(Color(hex: "#c9a84c"))
                        .labelStyle(.titleAndIcon)
                }
                if !vm.phaseDescription.isEmpty {
                    Text("·")
                        .foregroundColor(Color(hex: "#333360"))
                    Text(vm.phaseDescription)
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#5555a0"))
                        .lineLimit(1)
                }
                Spacer()
                if let t = vm.timeRemaining {
                    Label("\(t)s", systemImage: "timer")
                        .font(.system(size: 11))
                        .foregroundColor(t < 30 ? Color(hex: "#f87171") : Color(hex: "#5555a0"))
                }
            }
            if vm.truthProgress > 0 {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 2).fill(Color(hex: "#1e1c2e")).frame(height: 3)
                        RoundedRectangle(cornerRadius: 2)
                            .fill(LinearGradient(
                                colors: [Color(hex: "#c9a84c"), Color(hex: "#e8c96a")],
                                startPoint: .leading, endPoint: .trailing
                            ))
                            .frame(width: geo.size.width * vm.truthProgress, height: 3)
                    }
                }
                .frame(height: 3)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 8)
        .background(Color(hex: "#0d0c16").opacity(0.9))
        .overlay(Divider().background(Color(hex: "#1e1c2e")), alignment: .bottom)
    }

    // MARK: - Messages

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 0) {
                    ForEach(vm.messages) { msg in
                        MessageBubble(message: msg)
                            .id(msg.id)
                    }
                    if vm.messages.isEmpty {
                        VStack(spacing: 12) {
                            ProgressView()
                                .tint(Color(hex: "#c9a84c"))
                            Text("Connecting to the dungeon…")
                                .font(.system(size: 13))
                                .foregroundColor(Color(hex: "#333360"))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.top, 80)
                    }
                }
                .padding(.vertical, 12)
            }
            .onChange(of: vm.messages.count) { _ in
                if let last = vm.messages.last {
                    withAnimation(.easeOut(duration: 0.2)) {
                        proxy.scrollTo(last.id, anchor: .bottom)
                    }
                }
            }
        }
    }

    // MARK: - Input

    private var inputBar: some View {
        VStack(spacing: 0) {
            Divider().background(Color(hex: "#1e1c2e"))
            HStack(spacing: 10) {
                TextField("Ask the DM a question…", text: $vm.inputText, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .foregroundColor(.white)
                    .padding(.horizontal, 14).padding(.vertical, 11)
                    .background(Color(hex: "#16151f"))
                    .cornerRadius(12)
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color(hex: "#2a2840"), lineWidth: 1))
                    .disabled(vm.isSending)

                Button {
                    Task { await vm.send() }
                } label: {
                    ZStack {
                        if vm.isSending {
                            ProgressView()
                                .tint(.black)
                                .scaleEffect(0.8)
                        } else {
                            Image(systemName: "paperplane.fill")
                                .font(.system(size: 14))
                                .foregroundColor(.black)
                        }
                    }
                    .frame(width: 40, height: 40)
                    .background(vm.canSend
                        ? AnyShapeStyle(LinearGradient(colors: [Color(hex: "#e8c96a"), Color(hex: "#c9a84c")], startPoint: .top, endPoint: .bottom))
                        : AnyShapeStyle(Color(hex: "#2a2840"))
                    )
                    .clipShape(Circle())
                }
                .disabled(!vm.canSend)
            }
            .padding(.horizontal, 14).padding(.vertical, 10)
            .background(Color(hex: "#0d0c16"))
        }
    }

    // MARK: - Win banner

    private var winBanner: some View {
        VStack(spacing: 16) {
            Text("Mystery Solved!")
                .font(.system(size: 20, weight: .black, design: .serif))
                .foregroundStyle(LinearGradient(
                    colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                    startPoint: .leading, endPoint: .trailing
                ))
            if let truth = vm.truth {
                Text(truth)
                    .font(.system(size: 13))
                    .foregroundColor(Color(hex: "#c8c8d8"))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 20)
            }
            Button("Leave Room") { dismiss() }
                .font(.system(size: 14, weight: .bold))
                .foregroundColor(.black)
                .padding(.horizontal, 28).padding(.vertical, 12)
                .background(Color(hex: "#c9a84c"))
                .cornerRadius(12)
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(
            LinearGradient(colors: [Color(hex: "#1a150a"), Color(hex: "#16151f")], startPoint: .top, endPoint: .bottom)
        )
        .overlay(Divider().background(Color(hex: "#c9a84c").opacity(0.3)), alignment: .top)
    }

    private func avatarColor(_ name: String) -> Color {
        let colors: [Color] = [
            Color(hex: "#6366f1"), Color(hex: "#8b5cf6"), Color(hex: "#06b6d4"),
            Color(hex: "#10b981"), Color(hex: "#f59e0b"), Color(hex: "#ef4444"),
        ]
        let idx = name.unicodeScalars.reduce(0) { $0 + Int($1.value) } % colors.count
        return colors[idx]
    }
}

// MARK: - MessageBubble

private struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            // Avatar
            ZStack {
                Circle()
                    .fill(avatarBg)
                    .frame(width: 32, height: 32)
                Text(message.sender.prefix(1).uppercased())
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(.white)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(message.sender)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(senderColor)

                Text(message.text)
                    .font(.system(size: 14))
                    .foregroundColor(textColor)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
            Spacer(minLength: 32)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(message.type == .dm ? Color(hex: "#16151f").opacity(0.5) : Color.clear)
    }

    private var avatarBg: Color {
        switch message.type {
        case .dm: return Color(hex: "#1a3a2a")
        case .player: return Color(hex: "#1a1a3a")
        case .system: return Color(hex: "#2a2010")
        case .error: return Color(hex: "#3a1a1a")
        }
    }

    private var senderColor: Color {
        switch message.type {
        case .dm: return Color(hex: "#34d399")
        case .player: return Color(hex: "#818cf8")
        case .system: return Color(hex: "#c9a84c")
        case .error: return Color(hex: "#f87171")
        }
    }

    private var textColor: Color {
        switch message.type {
        case .error: return Color(hex: "#f87171")
        case .system: return Color(hex: "#d4c080")
        default: return Color(hex: "#e2e2f0")
        }
    }
}

// MARK: - Clue sheet

private struct ClueSheet: View {
    let clues: [CluePayload]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0a0a0f").ignoresSafeArea()
                if clues.isEmpty {
                    Text("No clues yet")
                        .foregroundColor(Color(hex: "#333360"))
                } else {
                    List(clues) { clue in
                        VStack(alignment: .leading, spacing: 6) {
                            Label(clue.title, systemImage: "sparkles")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(Color(hex: "#c9a84c"))
                            Text(clue.content)
                                .font(.system(size: 13))
                                .foregroundColor(Color(hex: "#c8c8d8"))
                        }
                        .listRowBackground(Color(hex: "#16151f"))
                        .padding(.vertical, 4)
                    }
                    .listStyle(.plain)
                    .scrollContentBackground(.hidden)
                }
            }
            .navigationTitle("Clues (\(clues.count))")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(hex: "#0d0c16"), for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") { dismiss() }
                        .foregroundColor(Color(hex: "#c9a84c"))
                }
            }
        }
    }
}

// MARK: - RoomViewModel extension for derived state

extension RoomViewModel {
    var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespaces).isEmpty && !isSending
    }
}
