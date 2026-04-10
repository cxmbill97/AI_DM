import SwiftUI

struct EconomyView: View {
    @StateObject private var vm = EconomyViewModel()
    @EnvironmentObject private var auth: AuthViewModel
    @State private var showPullSheet = false

    private var playerId: String { auth.user?.id ?? "" }

    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                // Coins display
                HStack {
                    Image(systemName: "dollarsign.circle.fill")
                        .foregroundColor(.yellow)
                        .font(.title)
                    Text("\(vm.wallet?.coins ?? 0) coins")
                        .font(.title2.bold())
                    Spacer()
                    Button("Gacha Pull") { showPullSheet = true }
                        .buttonStyle(.borderedProminent)
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)
                .padding(.horizontal)

                // Last pull results
                if !vm.lastPullResults.isEmpty {
                    VStack(alignment: .leading) {
                        Text("Last Pull")
                            .font(.headline)
                            .padding(.horizontal)
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 12) {
                                ForEach(vm.lastPullResults) { item in
                                    VStack(spacing: 4) {
                                        Text(item.rarity)
                                            .font(.caption2.bold())
                                            .padding(4)
                                            .background(item.rarity == "SSR" ? Color.yellow.opacity(0.3) :
                                                        item.rarity == "SR" ? Color.purple.opacity(0.3) :
                                                        Color.gray.opacity(0.2))
                                            .cornerRadius(4)
                                        Text(item.name)
                                            .font(.caption)
                                            .multilineTextAlignment(.center)
                                    }
                                    .frame(width: 80)
                                    .padding(8)
                                    .background(Color(.systemGray6))
                                    .cornerRadius(8)
                                }
                            }
                            .padding(.horizontal)
                        }
                    }
                }

                // Inventory
                if let inventory = vm.wallet?.inventory, !inventory.isEmpty {
                    VStack(alignment: .leading) {
                        Text("Inventory (\(inventory.count))")
                            .font(.headline)
                            .padding(.horizontal)
                        List(inventory) { item in
                            HStack {
                                Text(item.rarity)
                                    .font(.caption.bold())
                                    .foregroundColor(item.rarity == "SSR" ? .yellow :
                                                    item.rarity == "SR" ? .purple : .secondary)
                                    .frame(width: 36)
                                Text(item.name)
                                Spacer()
                                Text(item.type)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        .frame(height: 200)
                    }
                } else {
                    Text("No items yet. Try a gacha pull!")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }

                Spacer()
            }
            .navigationTitle("Economy")
            .task { await vm.loadWallet(playerId: playerId) }
            .sheet(isPresented: $showPullSheet) {
                PullSheet(vm: vm, playerId: playerId)
            }
        }
    }
}

struct PullSheet: View {
    @ObservedObject var vm: EconomyViewModel
    let playerId: String
    @Environment(\.dismiss) var dismiss

    var body: some View {
        VStack(spacing: 20) {
            Text("Gacha Pull")
                .font(.title2.bold())
            Text("Cost: 100 coins per pull")
                .foregroundColor(.secondary)
            Text("Current: \(vm.wallet?.coins ?? 0) coins")
                .font(.headline)
            HStack(spacing: 16) {
                Button("1 Pull") {
                    Task {
                        await vm.gachaPull(playerId: playerId, count: 1)
                        dismiss()
                    }
                }
                .buttonStyle(.bordered)
                Button("10 Pulls") {
                    Task {
                        await vm.gachaPull(playerId: playerId, count: 10)
                        dismiss()
                    }
                }
                .buttonStyle(.borderedProminent)
            }
            Button("Cancel", role: .cancel) { dismiss() }
        }
        .padding()
    }
}
