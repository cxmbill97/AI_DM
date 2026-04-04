import SwiftUI

struct RoomView: View {
    let roomId: String
    @StateObject private var vm: RoomViewModel
    @Environment(\.dismiss) private var dismiss

    init(roomId: String) {
        self.roomId = roomId
        _vm = StateObject(wrappedValue: RoomViewModel(roomId: roomId))
    }

    var body: some View {
        ZStack {
            Color(hex: "#0d0d0f").ignoresSafeArea()

            VStack(spacing: 0) {
                headerBar
                Divider().background(Color(hex: "#1e1e2e"))

                if vm.phase != "" {
                    phaseBar
                }

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 0) {
                            ForEach(vm.messages) { msg in
                                MessageRow(message: msg)
                                    .id(msg.id)
                            }
                        }
                        .padding(.vertical, 8)
                    }
                    .onChange(of: vm.messages.count) { _ in
                        if let last = vm.messages.last {
                            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                }

                if vm.gameWon {
                    winBanner
                } else {
                    inputBar
                }
            }
        }
        .navigationBarHidden(true)
        .task { await vm.connect() }
        .onDisappear { vm.disconnect() }
        .sheet(isPresented: $vm.showClues) {
            ClueListSheet(clues: vm.clues)
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

    // MARK: - Header

    private var headerBar: some View {
        HStack(spacing: 12) {
            Button { dismiss() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(Color(hex: "#c9a84c"))
            }

            VStack(alignment: .leading, spacing: 2) {
                Text("Room \(roomId)")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(.white)
                HStack(spacing: 6) {
                    Circle()
                        .fill(vm.isConnected ? Color(hex: "#4ade80") : (vm.isReconnecting ? Color(hex: "#fbbf24") : Color(hex: "#f87171")))
                        .frame(width: 6, height: 6)
                    Text(vm.isConnected ? "\(vm.players.count) player\(vm.players.count == 1 ? "" : "s")" :
                         (vm.isReconnecting ? "Reconnecting…" : "Disconnected"))
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#666680"))
                }
            }

            Spacer()

            if !vm.clues.isEmpty {
                Button { vm.showClues.toggle() } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "key.fill")
                            .font(.system(size: 12))
                        Text("\(vm.clues.count)")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .background(Color(hex: "#1e1e10"))
                    .foregroundColor(Color(hex: "#c9a84c"))
                    .cornerRadius(8)
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color(hex: "#c9a84c").opacity(0.4), lineWidth: 1))
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    // MARK: - Phase bar

    private var phaseBar: some View {
        VStack(spacing: 4) {
            HStack {
                Text(vm.phase)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(Color(hex: "#c9a84c"))
                Spacer()
                if let t = vm.timeRemaining {
                    Label("\(t)s", systemImage: "timer")
                        .font(.system(size: 11))
                        .foregroundColor(Color(hex: "#666680"))
                }
            }
            if !vm.phaseDescription.isEmpty {
                Text(vm.phaseDescription)
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#666680"))
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if vm.truthProgress > 0 {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(Color(hex: "#1e1e2e")).frame(height: 4)
                        Capsule().fill(Color(hex: "#c9a84c"))
                            .frame(width: geo.size.width * vm.truthProgress, height: 4)
                    }
                }
                .frame(height: 4)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color(hex: "#0d0d10"))
    }

    // MARK: - Input

    private var inputBar: some View {
        HStack(spacing: 10) {
            TextField("Ask the DM…", text: $vm.inputText, axis: .vertical)
                .lineLimit(1...4)
                .textFieldStyle(.plain)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(Color(hex: "#141420"))
                .foregroundColor(.white)
                .font(.system(size: 14))
                .cornerRadius(10)
                .disabled(vm.isSending)

            Button {
                Task { await vm.send() }
            } label: {
                if vm.isSending {
                    ProgressView()
                        .tint(.black)
                        .frame(width: 36, height: 36)
                } else {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 32))
                        .foregroundColor(vm.inputText.trimmingCharacters(in: .whitespaces).isEmpty
                            ? Color(hex: "#333348")
                            : Color(hex: "#c9a84c"))
                }
            }
            .disabled(vm.inputText.trimmingCharacters(in: .whitespaces).isEmpty || vm.isSending)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Color(hex: "#0d0d0f"))
    }

    // MARK: - Win banner

    private var winBanner: some View {
        VStack(spacing: 12) {
            Text("🎉 Mystery Solved!")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(Color(hex: "#c9a84c"))
            if let truth = vm.truth {
                Text(truth)
                    .font(.system(size: 13))
                    .foregroundColor(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 24)
            }
            Button("Leave Room") { dismiss() }
                .padding(.horizontal, 24).padding(.vertical, 10)
                .background(Color(hex: "#c9a84c"))
                .foregroundColor(.black)
                .font(.system(size: 14, weight: .semibold))
                .cornerRadius(10)
        }
        .padding()
        .frame(maxWidth: .infinity)
        .background(Color(hex: "#141420"))
    }
}

// MARK: - MessageRow

private struct MessageRow: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            avatarView
            VStack(alignment: .leading, spacing: 3) {
                Text(message.sender)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(senderColor)
                Text(message.text)
                    .font(.system(size: 14))
                    .foregroundColor(messageColor)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 6)
    }

    private var avatarView: some View {
        ZStack {
            Circle()
                .fill(avatarBg)
                .frame(width: 28, height: 28)
            Text(String(message.sender.prefix(1)))
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(.white)
        }
    }

    private var avatarBg: Color {
        switch message.type {
        case .dm: return Color(hex: "#1a4f3a")
        case .player: return Color(hex: "#1a2f5a")
        case .system: return Color(hex: "#2e2a10")
        case .error: return Color(hex: "#5a1a1a")
        }
    }

    private var senderColor: Color {
        switch message.type {
        case .dm: return Color(hex: "#4ade80")
        case .player: return Color(hex: "#60a0f0")
        case .system: return Color(hex: "#c9a84c")
        case .error: return Color(hex: "#f87171")
        }
    }

    private var messageColor: Color {
        switch message.type {
        case .error: return Color(hex: "#f87171")
        default: return Color(hex: "#c8c8d8")
        }
    }
}

// MARK: - ClueListSheet

private struct ClueListSheet: View {
    let clues: [CluePayload]
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0d0d0f").ignoresSafeArea()
                if clues.isEmpty {
                    Text("No clues unlocked yet")
                        .foregroundColor(Color(hex: "#666680"))
                } else {
                    List(clues) { clue in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(clue.title)
                                .font(.system(size: 14, weight: .semibold))
                                .foregroundColor(Color(hex: "#c9a84c"))
                            Text(clue.content)
                                .font(.system(size: 13))
                                .foregroundColor(Color(hex: "#c8c8d8"))
                        }
                        .listRowBackground(Color(hex: "#141420"))
                        .padding(.vertical, 4)
                    }
                    .listStyle(.plain)
                    .background(Color(hex: "#0d0d0f"))
                }
            }
            .navigationTitle("Unlocked Clues")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(hex: "#0d0d0f"), for: .navigationBar)
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
