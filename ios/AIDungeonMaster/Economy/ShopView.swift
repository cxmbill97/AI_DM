import SwiftUI

struct ShopView: View {
    @StateObject private var vm = EconomyViewModel()
    @State private var showGacha = false
    @State private var purchaseError: String?

    private let columns = [GridItem(.adaptive(minimum: 150), spacing: 12)]

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Balance banner
                    HStack {
                        Image(systemName: "circle.fill")
                            .foregroundColor(.yellow)
                        Text("\(vm.state.balance) coins")
                            .font(.title2.bold())
                        Spacer()
                        Button("Gacha Pull (100)") { showGacha = true }
                            .buttonStyle(.borderedProminent)
                            .disabled(vm.state.balance < 100 || vm.state.isLoading)
                    }
                    .padding()
                    .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))

                    // Error banner
                    if let err = vm.state.errorMessage ?? purchaseError {
                        Text(err)
                            .foregroundColor(.red)
                            .font(.caption)
                    }

                    // Shop grid
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(vm.state.shopItems) { item in
                            ShopItemCard(
                                item: item,
                                owned: vm.state.inventory.contains(item.id),
                                canAfford: vm.state.balance >= item.cost
                            ) {
                                Task {
                                    purchaseError = nil
                                    await vm.purchase(itemId: item.id)
                                    if let err = vm.state.errorMessage { purchaseError = err }
                                }
                            }
                        }
                    }
                    .padding(.horizontal)
                }
                .padding(.vertical)
            }
            .navigationTitle("Shop")
            .task { await vm.loadAll() }
            .sheet(isPresented: $showGacha) {
                GachaView(vm: vm)
            }
        }
    }
}

private struct ShopItemCard: View {
    let item: ShopItem
    let owned: Bool
    let canAfford: Bool
    let onBuy: () -> Void

    private var rarityColor: Color {
        switch item.rarity {
        case "SSR": return .purple
        case "SR":  return .orange
        default:    return .blue
        }
    }

    var body: some View {
        VStack(spacing: 8) {
            RoundedRectangle(cornerRadius: 12)
                .fill(rarityColor.opacity(0.15))
                .frame(height: 70)
                .overlay(
                    VStack(spacing: 2) {
                        Image(systemName: iconName)
                            .font(.title2)
                            .foregroundColor(rarityColor)
                        Text(item.rarity)
                            .font(.caption2.bold())
                            .foregroundColor(rarityColor)
                    }
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(rarityColor, lineWidth: owned ? 2 : 0)
                )

            Text(item.name)
                .font(.caption.bold())
                .multilineTextAlignment(.center)
                .lineLimit(2)

            if owned {
                Label("Owned", systemImage: "checkmark.seal.fill")
                    .font(.caption2)
                    .foregroundColor(.green)
            } else {
                Button("\(item.cost) coins") { onBuy() }
                    .font(.caption.bold())
                    .buttonStyle(.bordered)
                    .disabled(!canAfford)
            }
        }
        .padding(10)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16))
    }

    private var iconName: String {
        switch item.type {
        case "frame":  return "photo.artframe"
        case "color":  return "paintbrush.fill"
        default:       return "shield.fill"
        }
    }
}

#Preview { ShopView() }
