import SwiftUI

struct RoomView: View {
    let roomId: String
    @StateObject private var vm: RoomViewModel
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var tabBarState: TabBarVisibility
    @State private var showEmotes = false

    init(roomId: String) {
        self.roomId = roomId
        _vm = StateObject(wrappedValue: RoomViewModel(roomId: roomId))
    }

    var body: some View {
        ZStack {
            Color(hex: "#0a0a0f").ignoresSafeArea()

            VStack(spacing: 0) {
                navBar
                if vm.turnMode, let currentName = currentTurnPlayerName {
                    turnBanner(name: currentName, isMe: vm.isMyTurn)
                }
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
        .onDisappear {
            tabBarState.isHidden = false
            vm.disconnect()
        }
        .task { await vm.connect() }
        .sheet(isPresented: $vm.showClues) { ClueSheet(clues: vm.clues) }
        .alert("Error", isPresented: Binding(
            get: { vm.errorMessage != nil },
            set: { if !$0 { vm.errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) { vm.errorMessage = nil }
        } message: { Text(vm.errorMessage ?? "") }
    }

    // MARK: - Helpers

    private var currentTurnPlayerName: String? {
        guard let pid = vm.currentTurnPlayerId else { return nil }
        return vm.players.first(where: { $0.id == pid })?.name
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

            // Player avatars — highlight active turn player
            if !vm.players.isEmpty {
                HStack(spacing: -6) {
                    ForEach(vm.players.prefix(4)) { p in
                        let isActive = vm.turnMode && p.id == vm.currentTurnPlayerId
                        PlayerAvatar(name: p.name, size: 26, isActive: isActive)
                            .overlay(
                                isActive
                                    ? Circle().stroke(Color(hex: "#c9a84c"), lineWidth: 2)
                                    : nil
                            )
                            .overlay(Circle().stroke(Color(hex: "#0a0a0f"), lineWidth: 1.5))
                            .scaleEffect(isActive ? 1.15 : 1.0)
                            .animation(.spring(response: 0.3, dampingFraction: 0.7), value: isActive)
                            .zIndex(isActive ? 1 : 0)
                    }
                }
            }

            // TTS toggle
            Button { vm.toggleTTS() } label: {
                Image(systemName: vm.ttsEnabled ? "speaker.wave.2.fill" : "speaker.slash.fill")
                    .font(.system(size: 13))
                    .foregroundColor(vm.ttsEnabled ? Color(hex: "#c9a84c") : Color(hex: "#5555a0"))
                    .frame(width: 32, height: 32)
                    .background(Color(hex: "#1e1c2e"))
                    .clipShape(Circle())
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

    // MARK: - Turn banner

    private func turnBanner(name: String, isMe: Bool) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "person.fill")
                .font(.system(size: 11))
            Text(isMe ? "Your turn!" : "\(name)'s turn")
                .font(.system(size: 12, weight: .semibold))
            Spacer()
            if isMe {
                Text("Ask the DM a question")
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#c9a84c").opacity(0.8))
            }
        }
        .foregroundColor(isMe ? Color(hex: "#c9a84c") : Color(hex: "#818cf8"))
        .padding(.horizontal, 16).padding(.vertical, 7)
        .background(
            isMe
                ? Color(hex: "#c9a84c").opacity(0.12)
                : Color(hex: "#818cf8").opacity(0.08)
        )
        .overlay(
            Rectangle().frame(height: 1).foregroundColor(
                isMe ? Color(hex: "#c9a84c").opacity(0.3) : Color(hex: "#2a2840")
            ),
            alignment: .bottom
        )
        .transition(.opacity.combined(with: .move(edge: .top)))
        .animation(.easeInOut(duration: 0.3), value: name)
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
                    Text("·").foregroundColor(Color(hex: "#333360"))
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
                            .animation(.easeOut(duration: 0.5), value: vm.truthProgress)
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
                            .transition(.opacity)
                    }
                    if vm.messages.isEmpty {
                        VStack(spacing: 12) {
                            ProgressView().tint(Color(hex: "#c9a84c"))
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
            // Emote picker tray
            if showEmotes {
                emoteTray
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }

            Divider().background(Color(hex: "#1e1c2e"))
            HStack(spacing: 10) {
                // Emote toggle button
                Button {
                    withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) {
                        showEmotes.toggle()
                        if showEmotes { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
                    }
                } label: {
                    Text("😄")
                        .font(.system(size: 20))
                        .frame(width: 36, height: 36)
                        .background(showEmotes ? Color(hex: "#c9a84c").opacity(0.2) : Color(hex: "#16151f"))
                        .cornerRadius(10)
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(
                            showEmotes ? Color(hex: "#c9a84c").opacity(0.4) : Color(hex: "#2a2840"), lineWidth: 1))
                }

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
                    .submitLabel(.send)
                    .onSubmit { if vm.canSend { Task { await vm.send() } } }
                    .onChange(of: vm.inputText) { _ in
                        if showEmotes { showEmotes = false }
                    }

                Button {
                    Task { await vm.send() }
                } label: {
                    ZStack {
                        if vm.isSending {
                            ProgressView().tint(.black).scaleEffect(0.8)
                        } else {
                            Image(systemName: "paperplane.fill")
                                .font(.system(size: 14))
                                .foregroundColor(.black)
                        }
                    }
                    .frame(width: 40, height: 40)
                    .background(vm.canSend
                        ? AnyShapeStyle(LinearGradient(colors: [Color(hex: "#e8c96a"), Color(hex: "#c9a84c")],
                                                       startPoint: .top, endPoint: .bottom))
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

    private var emoteTray: some View {
        let emotes = ["👏", "🤔", "😮", "🎉", "💡", "❓"]
        return HStack(spacing: 12) {
            ForEach(emotes, id: \.self) { emoji in
                Button {
                    Task { await vm.sendEmote(emoji) }
                    withAnimation { showEmotes = false }
                } label: {
                    Text(emoji)
                        .font(.system(size: 24))
                        .frame(width: 44, height: 44)
                        .background(Color(hex: "#16151f"))
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color(hex: "#2a2840"), lineWidth: 1))
                }
            }
            Spacer()
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
        .background(Color(hex: "#0d0c16"))
    }

    // MARK: - Win banner

    private var winBanner: some View {
        VStack(spacing: 16) {
            Text("🎉 Mystery Solved!")
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
        .background(LinearGradient(colors: [Color(hex: "#1a150a"), Color(hex: "#16151f")], startPoint: .top, endPoint: .bottom))
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

// MARK: - PlayerAvatar (Phase 3 reusable component)

struct PlayerAvatar: View {
    let name: String
    let size: CGFloat
    var isActive: Bool = false

    var body: some View {
        ZStack {
            Circle()
                .fill(bgColor)
                .frame(width: size, height: size)
            if isActive {
                Circle()
                    .fill(bgColor.opacity(0.5))
                    .frame(width: size * 1.4, height: size * 1.4)
                    .blur(radius: 4)
            }
            Text(name.prefix(1).uppercased())
                .font(.system(size: size * 0.42, weight: .bold))
                .foregroundColor(.white)
        }
        .frame(width: size, height: size)
    }

    private var bgColor: Color {
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
        Group {
            if message.type == .emote {
                emoteBubble
            } else {
                regularBubble
            }
        }
    }

    private var emoteBubble: some View {
        HStack {
            Text(message.sender)
                .font(.system(size: 11))
                .foregroundColor(Color(hex: "#5555a0"))
            Text(message.text)
                .font(.system(size: 26))
            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 4)
    }

    private var regularBubble: some View {
        HStack(alignment: .top, spacing: 10) {
            PlayerAvatar(name: message.sender, size: 32)

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(message.sender)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(senderColor)
                    if let j = message.judgment {
                        judgmentBadge(j)
                    }
                }

                HStack(alignment: .bottom, spacing: 2) {
                    Text(message.text)
                        .font(.system(size: 14))
                        .foregroundColor(textColor)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                    if message.isStreaming {
                        BlinkingCursor()
                    }
                }
            }
            Spacer(minLength: 32)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(message.type == .dm ? Color(hex: "#16151f").opacity(0.5) : Color.clear)
        .overlay(
            // Left edge accent for DM correct answers
            message.type == .dm && isPositiveJudgment
                ? Rectangle()
                    .fill(judgmentAccentColor)
                    .frame(width: 3)
                    .cornerRadius(1.5)
                : nil,
            alignment: .leading
        )
    }

    private func judgmentBadge(_ j: String) -> some View {
        let (label, color) = judgmentDisplay(j)
        return Text(label)
            .font(.system(size: 9, weight: .bold))
            .foregroundColor(color)
            .padding(.horizontal, 5).padding(.vertical, 2)
            .background(color.opacity(0.15))
            .cornerRadius(4)
    }

    private func judgmentDisplay(_ j: String) -> (String, Color) {
        switch j {
        case "是", "Yes":                     return ("✓ YES", Color(hex: "#34d399"))
        case "部分正确", "Partially correct": return ("~ PARTIAL", Color(hex: "#fbbf24"))
        case "不是", "No":                    return ("✗ NO", Color(hex: "#f87171"))
        default:                              return ("— N/A", Color(hex: "#5555a0"))
        }
    }

    private var isPositiveJudgment: Bool {
        guard let j = message.judgment else { return false }
        return j == "是" || j == "Yes"
    }

    private var judgmentAccentColor: Color {
        guard let j = message.judgment else { return .clear }
        return judgmentDisplay(j).1
    }

    private var senderColor: Color {
        switch message.type {
        case .dm:     return Color(hex: "#34d399")
        case .player: return Color(hex: "#818cf8")
        case .system: return Color(hex: "#c9a84c")
        case .error:  return Color(hex: "#f87171")
        case .emote:  return Color(hex: "#5555a0")
        }
    }

    private var textColor: Color {
        switch message.type {
        case .error:  return Color(hex: "#f87171")
        case .system: return Color(hex: "#d4c080")
        default:      return Color(hex: "#e2e2f0")
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
                    Text("No clues yet").foregroundColor(Color(hex: "#333360"))
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

// MARK: - BlinkingCursor

private struct BlinkingCursor: View {
    @State private var visible = true
    var body: some View {
        Rectangle()
            .fill(Color(hex: "#34d399"))
            .frame(width: 2, height: 14)
            .opacity(visible ? 1 : 0)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.5).repeatForever()) {
                    visible = false
                }
            }
    }
}

// MARK: - RoomViewModel extension for derived state

extension RoomViewModel {
    var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }
}
