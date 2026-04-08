import SwiftUI

struct GachaView: View {
    @ObservedObject var vm: EconomyViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var result: GachaPullResult?
    @State private var animating = false
    @State private var revealed = false

    var body: some View {
        VStack(spacing: 32) {
            Text("Gacha Pull")
                .font(.largeTitle.bold())
                .padding(.top, 40)

            // Pity counter
            HStack(spacing: 4) {
                Image(systemName: "arrow.counterclockwise")
                Text("Pity: \(vm.state.pityCount)/10")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
            }

            Spacer()

            // Reveal area
            if let result, revealed {
                RarityRevealCard(result: result)
                    .transition(.scale.combined(with: .opacity))
            } else {
                RoundedRectangle(cornerRadius: 24)
                    .fill(Color.purple.opacity(0.15))
                    .frame(width: 200, height: 200)
                    .overlay(
                        Image(systemName: "sparkles")
                            .font(.system(size: 60))
                            .foregroundColor(.purple)
                            .rotationEffect(.degrees(animating ? 360 : 0))
                            .animation(animating ? .linear(duration: 1).repeatForever(autoreverses: false) : .default, value: animating)
                    )
            }

            Spacer()

            if result == nil || !revealed {
                Button {
                    Task { await doPull() }
                } label: {
                    Label("Pull (100 coins)", systemImage: "die.face.5")
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.purple)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                }
                .disabled(vm.state.balance < 100 || vm.state.isLoading)
            } else {
                Button("Pull Again (100 coins)") {
                    result = nil
                    revealed = false
                    Task { await doPull() }
                }
                .buttonStyle(.borderedProminent)
                .tint(.purple)
                .disabled(vm.state.balance < 100 || vm.state.isLoading)
            }

            Button("Close") { dismiss() }
                .foregroundColor(.secondary)
                .padding(.bottom, 20)

            if let err = vm.state.errorMessage {
                Text(err).foregroundColor(.red).font(.caption)
            }
        }
        .padding(.horizontal, 32)
    }

    private func doPull() async {
        animating = true
        revealed = false
        let r = await vm.pull()
        try? await Task.sleep(nanoseconds: 800_000_000)
        animating = false
        result = r
        withAnimation(.spring(response: 0.5, dampingFraction: 0.7)) {
            revealed = true
        }
    }
}

private struct RarityRevealCard: View {
    let result: GachaPullResult

    private var rarityColor: Color {
        switch result.rarity {
        case "SSR": return .purple
        case "SR":  return .orange
        default:    return .blue
        }
    }

    private var rarityLabel: String {
        switch result.rarity {
        case "SSR": return "✨ SSR — Ultra Rare!"
        case "SR":  return "⭐ SR — Rare"
        default:    return "R — Common"
        }
    }

    var body: some View {
        VStack(spacing: 16) {
            Text(rarityLabel)
                .font(.title2.bold())
                .foregroundColor(rarityColor)

            RoundedRectangle(cornerRadius: 20)
                .fill(rarityColor.opacity(0.15))
                .frame(width: 140, height: 140)
                .overlay(
                    VStack(spacing: 6) {
                        Image(systemName: "sparkle")
                            .font(.system(size: 48))
                            .foregroundColor(rarityColor)
                        Text(result.item.rarity)
                            .font(.caption.bold())
                            .foregroundColor(rarityColor)
                    }
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(rarityColor, lineWidth: 2)
                )

            Text(result.item.name)
                .font(.headline)
        }
    }
}

#Preview {
    GachaView(vm: EconomyViewModel())
}
