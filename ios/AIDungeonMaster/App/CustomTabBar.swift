import SwiftUI

private struct TabBarItem {
    let tag: Int
    let icon: String
    let selectedIcon: String
    let label: String
}

struct CustomTabBar: View {
    @Binding var selectedTab: Int

    private let items: [TabBarItem] = [
        TabBarItem(tag: 0, icon: "house",              selectedIcon: "house.fill",              label: "Home"),
        TabBarItem(tag: 1, icon: "magnifyingglass",    selectedIcon: "magnifyingglass",          label: "Explore"),
        TabBarItem(tag: 2, icon: "flame",              selectedIcon: "flame.fill",               label: "Activity"),
        TabBarItem(tag: 3, icon: "bookmark",           selectedIcon: "bookmark.fill",            label: "Saved"),
        TabBarItem(tag: 4, icon: "person.crop.circle", selectedIcon: "person.crop.circle.fill",  label: "Profile"),
    ]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(items, id: \.tag) { item in
                let isSelected = selectedTab == item.tag
                Button {
                    withAnimation(.spring(response: 0.25, dampingFraction: 0.7)) {
                        selectedTab = item.tag
                    }
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: isSelected ? item.selectedIcon : item.icon)
                            .font(.system(size: 22))
                            .foregroundStyle(
                                isSelected
                                    ? AnyShapeStyle(LinearGradient(
                                        colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                                        startPoint: .top, endPoint: .bottom
                                      ))
                                    : AnyShapeStyle(Color(hex: "#44446a"))
                            )
                            .scaleEffect(isSelected ? 1.08 : 1.0)
                            .animation(.spring(response: 0.25), value: isSelected)

                        Text(item.label)
                            .font(.system(size: 10, weight: .medium))
                            .foregroundColor(isSelected ? Color(hex: "#c9a84c") : Color(hex: "#44446a"))
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 4)
        .background(
            Color(hex: "#0d0c17")
                .shadow(color: .black.opacity(0.5), radius: 12, x: 0, y: -4)
                .ignoresSafeArea(edges: .bottom)
        )
        .overlay(
            Rectangle()
                .frame(height: 0.5)
                .foregroundColor(Color(hex: "#2a2840")),
            alignment: .top
        )
    }
}
