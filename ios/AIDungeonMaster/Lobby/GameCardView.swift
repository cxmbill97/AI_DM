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

    private var isTurtleSoup: Bool { gameType == "turtle_soup" }

    private var diffColor: Color {
        switch normalizedDifficulty(difficulty) {
        case "easy": return Color(hex: "#34d399")
        case "hard": return Color(hex: "#f87171")
        default:     return Color(hex: "#fbbf24")
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Thumbnail area
            ZStack(alignment: .bottom) {
                thumbGradient
                    .frame(height: 120)

                // Bottom gradient overlay
                LinearGradient(
                    colors: [Color.clear, Color.black.opacity(0.6)],
                    startPoint: .top, endPoint: .bottom
                )
                .frame(height: 60)

                // Title on top of gradient
                Text(title)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(.white)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 10)
                    .padding(.bottom, 8)
            }
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(alignment: .topLeading) {
                Text(isTurtleSoup ? "🐢 Turtle Soup" : "🔍 Murder Mystery")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(isTurtleSoup ? Color(hex: "#7dd3fc") : Color(hex: "#d8b4fe"))
                    .padding(.horizontal, 7).padding(.vertical, 3)
                    .background(.ultraThinMaterial)
                    .clipShape(Capsule())
                    .padding(8)
            }
            .overlay(alignment: .topTrailing) {
                Button(action: onFavorite) {
                    Image(systemName: isFavorite ? "heart.fill" : "heart")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(isFavorite ? Color(hex: "#fb7185") : .white)
                        .padding(7)
                        .background(.ultraThinMaterial)
                        .clipShape(Circle())
                }
                .padding(8)
            }

            // Card body
            VStack(alignment: .leading, spacing: 8) {
                // Tags row
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 5) {
                        if !difficulty.isEmpty {
                            Text(localizedDifficulty(difficulty))
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundColor(diffColor)
                                .padding(.horizontal, 7).padding(.vertical, 3)
                                .background(diffColor.opacity(0.12))
                                .clipShape(Capsule())
                        }
                        ForEach(tags.prefix(3), id: \.self) { tag in
                            Text(tag)
                                .font(.system(size: 10))
                                .foregroundColor(Color(hex: "#7878a8"))
                                .padding(.horizontal, 7).padding(.vertical, 3)
                                .background(Color(hex: "#7878a8").opacity(0.1))
                                .clipShape(Capsule())
                        }
                    }
                }

                // Action buttons
                HStack(spacing: 8) {
                    Button(action: onSolo) {
                        Label("Solo", systemImage: "person.fill")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(Color(hex: "#c9a84c"))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 7)
                            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color(hex: "#c9a84c").opacity(0.6), lineWidth: 1))
                    }

                    Button(action: onCreateRoom) {
                        Label("Room", systemImage: "person.3.fill")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.black)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 7)
                            .background(Color(hex: "#c9a84c"))
                            .cornerRadius(8)
                    }
                }
            }
            .padding(12)
        }
        .background(Color(hex: "#16151f"))
        .cornerRadius(14)
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2a2840").opacity(0.8), lineWidth: 1))
        .shadow(color: .black.opacity(0.3), radius: 8, y: 4)
    }

    private var thumbGradient: LinearGradient {
        let seed = itemId.unicodeScalars.reduce(0) { $0 + Int($1.value) }
        let hues: [(Double, Double)] = [
            (0.55, 0.65), (0.75, 0.85), (0.15, 0.25),
            (0.05, 0.10), (0.35, 0.45), (0.85, 0.95)
        ]
        let pair = hues[seed % hues.count]
        return LinearGradient(
            colors: [
                Color(hue: pair.0, saturation: 0.6, brightness: 0.35),
                Color(hue: pair.1, saturation: 0.7, brightness: 0.2),
            ],
            startPoint: .topLeading, endPoint: .bottomTrailing
        )
    }
}
