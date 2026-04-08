import Foundation

struct PetState: Codable, Identifiable {
    let id: String  // owner_id
    var name: String
    var species: String
    var level: Int
    var xp: Int
    var mood: String
    var personalityTraits: [String]
    var memory: [String]

    enum CodingKeys: String, CodingKey {
        case id = "owner_id"
        case name, species, level, xp, mood
        case personalityTraits = "personality_traits"
        case memory
    }

    var moodEmoji: String {
        switch mood {
        case "happy": return "😊"
        case "excited": return "🎉"
        case "sleepy": return "😴"
        default: return "😐"
        }
    }

    var xpToNextLevel: Int {
        let thresholds = [0, 100, 300, 600, 1000]
        if level < thresholds.count {
            return thresholds[level] - xp
        }
        return 0
    }
}
