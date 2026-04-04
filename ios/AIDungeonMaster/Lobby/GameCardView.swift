import SwiftUI

struct GameCardView: View {
    let title: String
    let difficulty: String
    let tags: [String]
    let gameType: String
    let itemId: String
    let isFavorite: Bool
    var onFavorite: () -> Void
    var onSolo: () -> Void
    var onCreateRoom: () -> Void

    var diffColor: Color {
        switch difficulty {
        case "简单", "beginner", "Easy": return Color(hex: "#4ade80")
        case "困难", "hard", "Hard": return Color(hex: "#f87171")
        default: return Color(hex: "#fbbf24")
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Thumbnail
            ZStack(alignment: .topLeading) {
                thumbGradient
                    .frame(height: 110)
                    .clipShape(RoundedRectangle(cornerRadius: 10))

                Text(gameType == "turtle_soup" ? "Turtle Soup" : "Murder Mystery")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(gameType == "turtle_soup" ? Color(hex: "#1a4f7a") : Color(hex: "#5a1a3a"))
                    .cornerRadius(6)
                    .padding(10)

                Button(action: onFavorite) {
                    Image(systemName: isFavorite ? "heart.fill" : "heart")
                        .font(.system(size: 13))
                        .foregroundColor(isFavorite ? Color(hex: "#e85d75") : Color(hex: "#666680"))
                        .padding(8)
                        .background(Color.black.opacity(0.4))
                        .clipShape(Circle())
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
                .padding(8)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(2)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 4) {
                        if !difficulty.isEmpty {
                            Text(difficulty)
                                .font(.system(size: 10))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(diffColor.opacity(0.15))
                                .foregroundColor(diffColor)
                                .cornerRadius(4)
                        }
                        ForEach(tags.prefix(2), id: \.self) { tag in
                            Text(tag)
                                .font(.system(size: 10))
                                .padding(.horizontal, 6).padding(.vertical, 2)
                                .background(Color(hex: "#1e1e28"))
                                .foregroundColor(Color(hex: "#9090b0"))
                                .cornerRadius(4)
                        }
                    }
                }

                HStack(spacing: 8) {
                    Button("Solo") { onSolo() }
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(Color(hex: "#c9a84c"))
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color(hex: "#c9a84c"), lineWidth: 1))

                    Button("Room") { onCreateRoom() }
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.black)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .background(Color(hex: "#c9a84c"))
                        .cornerRadius(6)
                }
                .padding(.top, 4)
            }
            .padding(12)
        }
        .background(Color(hex: "#141420"))
        .cornerRadius(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color(hex: "#1e1e2e"), lineWidth: 1))
    }

    private var thumbGradient: LinearGradient {
        let seed = itemId.unicodeScalars.reduce(0) { $0 + Int($1.value) }
        let hue = Double(seed % 360) / 360.0
        return LinearGradient(
            colors: [
                Color(hue: hue, saturation: 0.4, brightness: 0.25),
                Color(hue: (hue + 0.1).truncatingRemainder(dividingBy: 1.0), saturation: 0.5, brightness: 0.15)
            ],
            startPoint: .topLeading, endPoint: .bottomTrailing
        )
    }
}
