import SwiftUI

struct EconomyView: View {
    @StateObject private var vm = EconomyViewModel()
    @State private var showGacha = false

    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                // Balance display
                HStack {
                    Image(systemName: "dollarsign.circle.fill")
                        .foregroundColor(.yellow)
                        .font(.title)
                    Text("\(vm.state.balance) coins")
                        .font(.title2.bold())
                    Spacer()
                    Button("Gacha Pull") { showGacha = true }
                        .buttonStyle(.borderedProminent)
                        .disabled(vm.state.balance < 100 || vm.state.isLoading)
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)
                .padding(.horizontal)

                // Last pull result
                if let lastPull = vm.state.lastPull {
                    VStack(alignment: .leading) {
                        Text("Last Pull")
                            .font(.headline)
                            .padding(.horizontal)
                        HStack(spacing: 12) {
                            VStack(spacing: 4) {
                                Text(lastPull.rarity)
                                    .font(.caption2.bold())
                                    .padding(4)
                                    .background(lastPull.rarity == "SSR" ? Color.yellow.opacity(0.3) :
                                                lastPull.rarity == "SR" ? Color.purple.opacity(0.3) :
                                                Color.gray.opacity(0.2))
                                    .cornerRadius(4)
                                Text(lastPull.item.name)
                                    .font(.caption)
                                    .multilineTextAlignment(.center)
                            }
                            .frame(width: 80)
                            .padding(8)
                            .background(Color(.systemGray6))
                            .cornerRadius(8)
                            Spacer()
                        }
                        .padding(.horizontal)
                    }
                }

                // Inventory
                if vm.state.inventory.isEmpty {
                    Text("No items yet. Try a gacha pull!")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    VStack(alignment: .leading) {
                        Text("Inventory (\(vm.state.inventory.count))")
                            .font(.headline)
                            .padding(.horizontal)
                        List(vm.state.inventory, id: \.self) { itemId in
                            Text(itemId)
                                .font(.subheadline)
                        }
                        .frame(height: 200)
                    }
                }

                if let err = vm.state.errorMessage {
                    Text(err).foregroundColor(.red).font(.caption).padding(.horizontal)
                }

                Spacer()
            }
            .navigationTitle("Economy")
            .overlay {
                if vm.state.isLoading {
                    ProgressView()
                }
            }
            .task { await vm.loadAll() }
            .sheet(isPresented: $showGacha) {
                GachaView(vm: vm)
            }
        }
    }
}
