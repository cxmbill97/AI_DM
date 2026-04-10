import SwiftUI

// —————————————————————————
// Drop-in debug logger — shows last N entries as an overlay on any view.
//
// Usage:  someView.overlay(alignment: .top) { DebugOverlay() }
//
// To log:   DebugLog.log("tag", "message")
// To clear: DebugLog.clear()
// —————————————————————————

final class DebugLog: ObservableObject {
    static let shared = DebugLog()
    @Published var entries: [String] = []
    private let maxEntries = 40

    static func log(_ tag: String, _ msg: String) {
        let ts = ISO8601DateFormatter().string(from: Date())
            .suffix(12)            // HH:mm:ss.SSS
            .replacingOccurrences(of: "Z", with: "")
        let line = "[\(ts)] [\(tag)] \(msg)"
        print(line) // also goes to Xcode console / Console.app
        Task { @MainActor in
            shared.entries.append(line)
            if shared.entries.count > shared.maxEntries {
                shared.entries.removeFirst(shared.entries.count - shared.maxEntries)
            }
        }
    }

    static func clear() {
        Task { @MainActor in
            shared.entries.removeAll()
        }
    }
}

struct DebugOverlay: View {
    @ObservedObject private var log = DebugLog.shared
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Toggle button
            Button {
                withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
            } label: {
                HStack(spacing: 4) {
                    Circle()
                        .fill(Color.red)
                        .frame(width: 8, height: 8)
                    Text("DBG (\(log.entries.count))")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundColor(.white)
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 8))
                        .foregroundColor(.white)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.black.opacity(0.85))
                .cornerRadius(10)
            }
            .padding(.top, 50) // below notch
            .padding(.leading, 8)

            if expanded {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 1) {
                            ForEach(Array(log.entries.enumerated()), id: \.offset) { idx, entry in
                                Text(entry)
                                    .font(.system(size: 9, design: .monospaced))
                                    .foregroundColor(colorFor(entry))
                                    .id(idx)
                            }
                        }
                        .padding(6)
                    }
                    .frame(maxHeight: 280)
                    .background(Color.black.opacity(0.9))
                    .cornerRadius(8)
                    .padding(.horizontal, 8)
                    .onChange(of: log.entries.count) { _ in
                        if let last = log.entries.indices.last {
                            proxy.scrollTo(last, anchor: .bottom)
                        }
                    }
                }

                // Clear button
                Button("Clear") { DebugLog.clear() }
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(.red)
                    .padding(.leading, 16)
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .allowsHitTesting(true)
    }

    private func colorFor(_ entry: String) -> Color {
        if entry.contains("ERROR") || entry.contains("FAIL") || entry.contains("❌") { return .red }
        if entry.contains("WARN") || entry.contains("⚠️") { return .yellow }
        if entry.contains("[WS]") { return .cyan }
        if entry.contains("[VM]") { return .green }
        if entry.contains("[UI]") { return .orange }
        return Color.white.opacity(0.8)
    }
}
