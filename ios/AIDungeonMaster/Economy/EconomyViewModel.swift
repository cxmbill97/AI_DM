import Foundation

@MainActor
final class EconomyViewModel: ObservableObject {
    @Published var state = EconomyState()

    private let api = APIService.shared

    func loadAll() async {
        state.isLoading = true
        defer { state.isLoading = false }
        async let balanceTask: BalanceResponse = api.request("/economy/balance")
        async let shopTask: [ShopItem] = api.request("/economy/shop")
        async let inventoryTask: [String] = api.request("/economy/inventory")
        do {
            let (balance, shop, inventory) = try await (balanceTask, shopTask, inventoryTask)
            state.balance = balance.balance
            state.shopItems = shop
            state.inventory = inventory
            state.errorMessage = nil
        } catch {
            state.errorMessage = error.localizedDescription
        }
    }

    func purchase(itemId: String) async {
        state.isLoading = true
        defer { state.isLoading = false }
        struct Body: Encodable { let item_id: String }
        do {
            let resp: PurchaseResponse = try await api.request("/economy/purchase", method: "POST", body: Body(item_id: itemId))
            state.balance = resp.balance
            if !state.inventory.contains(itemId) {
                state.inventory.append(itemId)
            }
            state.errorMessage = nil
        } catch {
            state.errorMessage = error.localizedDescription
        }
    }

    func pull() async -> GachaPullResult? {
        state.isLoading = true
        defer { state.isLoading = false }
        do {
            let result: GachaPullResult = try await api.request("/economy/pull", method: "POST")
            state.balance -= 100  // optimistic update; real balance refreshed on next load
            state.lastPull = result
            state.pityCount = result.pity_count
            if !state.inventory.contains(result.item.id) {
                state.inventory.append(result.item.id)
            }
            state.errorMessage = nil
            return result
        } catch {
            state.errorMessage = error.localizedDescription
            return nil
        }
    }
}
