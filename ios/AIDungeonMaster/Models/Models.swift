import Foundation
import SwiftUI

// MARK: - REST Models

struct User: Codable, Equatable {
    let id: String
    let name: String
    let email: String
    let avatar_url: String
    let created_at: String
}

struct PuzzleSummary: Codable, Identifiable {
    let id: String
    let title: String
    let difficulty: String
    let tags: [String]
}

struct ScriptSummary: Codable, Identifiable {
    let id: String
    let title: String
    let difficulty: String
    let player_count: Int
}

struct FavoriteItem: Codable, Identifiable {
    let item_id: String
    let item_type: String
    let saved_at: String
    var id: String { "\(item_type):\(item_id)" }
}

struct HistoryItem: Codable, Identifiable {
    let id: String
    let room_id: String
    let game_type: String
    let title: String
    let player_count: Int
    let played_at: String
}

struct CreateRoomResponse: Codable {
    let room_id: String
    let game_type: String?
}

// MARK: - WebSocket Payload Models

struct CluePayload: Codable, Identifiable {
    let id: String
    let title: String
    let content: String
    let unlock_keywords: [String]
}

struct DmResponsePayload: Codable {
    let player_name: String
    let judgment: String
    let response: String
    let truth_progress: Double
    let clue_unlocked: CluePayload?
    let hint: String?
    let truth: String?
    let timestamp: Double
}

struct PlayerMessagePayload: Codable {
    let player_name: String
    let text: String
    let timestamp: Double
}

struct SystemPayload: Codable {
    let text: String
}

struct PlayerInfo: Codable, Identifiable {
    let id: String
    let name: String
    let character: String?
    let connected: Bool?
}

struct RoomSnapshotPayload: Codable {
    let room_id: String?
    let game_type: String?
    let phase: String?
    let current_phase: String?
    let phase_description: String?
    let players: [PlayerInfo]
    let clues: [CluePayload]
    let time_remaining: Int?
}

struct ErrorPayload: Codable {
    let message: String
}

// MARK: - GameMessage (discriminated union on "type" field)

enum GameMessage {
    case dmResponse(DmResponsePayload)
    case playerMessage(PlayerMessagePayload)
    case system(SystemPayload)
    case roomSnapshot(RoomSnapshotPayload)
    case error(ErrorPayload)
    case unknown(String)
}

extension GameMessage: Decodable {
    private struct TypeWrapper: Decodable { let type: String }

    init(from decoder: Decoder) throws {
        let wrapper = try TypeWrapper(from: decoder)
        let container = try decoder.singleValueContainer()
        switch wrapper.type {
        case "dm_response":
            self = .dmResponse(try container.decode(DmResponsePayload.self))
        case "player_message":
            self = .playerMessage(try container.decode(PlayerMessagePayload.self))
        case "system":
            self = .system(try container.decode(SystemPayload.self))
        case "room_snapshot":
            self = .roomSnapshot(try container.decode(RoomSnapshotPayload.self))
        case "error":
            self = .error(try container.decode(ErrorPayload.self))
        default:
            self = .unknown(wrapper.type)
        }
    }
}

// MARK: - Outbound WebSocket message

struct ClientMessage: Codable {
    let type: String
    let text: String
}

// MARK: - Color helper

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xFF) / 255
        let g = Double((int >> 8) & 0xFF) / 255
        let b = Double(int & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
}
