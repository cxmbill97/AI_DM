import Foundation

struct WalletState: Codable {
    let playerId: String
    var coins: Int
    var inventory: [CosmeticItem]
    var pullCount: Int

    enum CodingKeys: String, CodingKey {
        case playerId = "player_id"
        case coins, inventory
        case pullCount = "pull_count"
    }
}

struct CosmeticItem: Codable, Identifiable {
    let id: String
    let name: String
    let rarity: String
    let type: String
    let obtainedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, name, rarity, type
        case obtainedAt = "obtained_at"
    }

    var rarityColor: String {
        switch rarity {
        case "SSR": return "gold"
        case "SR": return "purple"
        default: return "gray"
        }
    }
}

struct GachaResult: Codable {
    let success: Bool
    let results: [CosmeticItem]?
    let coins: Int
    let spent: Int?
    let error: String?
}

struct EarnResult: Codable {
    let coins: Int
    let earned: Int
    let reason: String
}
