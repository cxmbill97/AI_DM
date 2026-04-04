import SwiftUI

struct GameModeSheet: View {
    let onSelect: (Bool) -> Void   // isPublic

    var body: some View {
        VStack(spacing: 0) {
            // Handle
            Capsule()
                .fill(Color(hex: "#2a2840"))
                .frame(width: 36, height: 4)
                .padding(.top, 12)
                .padding(.bottom, 20)

            Text("Choose Room Type")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(.white)
                .padding(.bottom, 24)

            VStack(spacing: 12) {
                ModeRow(
                    icon: "person.fill",
                    title: "Solo",
                    subtitle: "Play alone — room won't be listed publicly",
                    isPublic: false,
                    onSelect: onSelect
                )
                ModeRow(
                    icon: "globe",
                    title: "Public",
                    subtitle: "Open room — anyone can find and join",
                    isPublic: true,
                    onSelect: onSelect
                )
            }
            .padding(.horizontal, 20)

            Spacer(minLength: 32)
        }
        .frame(maxWidth: .infinity)
        .background(Color(hex: "#0d0c17").ignoresSafeArea())
        .presentationDetents([.height(280)])
        .presentationDragIndicator(.hidden)
    }
}

private struct ModeRow: View {
    let icon: String
    let title: String
    let subtitle: String
    let isPublic: Bool
    let onSelect: (Bool) -> Void

    var body: some View {
        Button { onSelect(isPublic) } label: {
            HStack(spacing: 16) {
                ZStack {
                    Circle()
                        .fill(Color(hex: "#1e1c2e"))
                        .frame(width: 48, height: 48)
                    Image(systemName: icon)
                        .font(.system(size: 20))
                        .foregroundStyle(LinearGradient(
                            colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                            startPoint: .top, endPoint: .bottom
                        ))
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                    Text(subtitle)
                        .font(.system(size: 12))
                        .foregroundColor(Color(hex: "#44446a"))
                        .lineLimit(2)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.system(size: 13))
                    .foregroundColor(Color(hex: "#2a2840"))
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            .background(Color(hex: "#16151f"))
            .cornerRadius(14)
            .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2a2840"), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}
