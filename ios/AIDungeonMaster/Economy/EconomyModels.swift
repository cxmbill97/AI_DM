import Foundation

struct ShopItem: Codable, Identifiable {
    let id: String
    let name: String
    let cost: Int
    let rarity: String
    let type: String
}

struct GachaPullResult: Codable {
    let item: ShopItem
    let rarity: String
    let pity_count: Int
}

struct BalanceResponse: Codable {
    let balance: Int
}

struct PurchaseResponse: Codable {
    let ok: Bool
    let balance: Int
}

struct EconomyState {
    var balance: Int = 0
    var inventory: [String] = []
    var shopItems: [ShopItem] = []
    var lastPull: GachaPullResult? = nil
    var pityCount: Int = 0
    var isLoading: Bool = false
    var errorMessage: String? = nil
}
