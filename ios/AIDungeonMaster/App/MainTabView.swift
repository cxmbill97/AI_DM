import SwiftUI

struct MainTabView: View {
    @State private var selectedTab = 0
    @StateObject private var tabBarState = TabBarVisibility()

    var body: some View {
        ZStack(alignment: .bottom) {
            // All tab views stay alive after first load (opacity trick preserves state)
            ZStack {
                HomeView()
                    .opacity(selectedTab == 0 ? 1 : 0)
                    .allowsHitTesting(selectedTab == 0)
                ExploreView()
                    .opacity(selectedTab == 1 ? 1 : 0)
                    .allowsHitTesting(selectedTab == 1)
                EconomyView()
                    .opacity(selectedTab == 2 ? 1 : 0)
                    .allowsHitTesting(selectedTab == 2)
                PetView()
                    .opacity(selectedTab == 3 ? 1 : 0)
                    .allowsHitTesting(selectedTab == 3)
                ProfileView()
                    .opacity(selectedTab == 4 ? 1 : 0)
                    .allowsHitTesting(selectedTab == 4)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            // Bottom padding so content doesn't sit behind tab bar
            .safeAreaInset(edge: .bottom) {
                Color.clear.frame(height: tabBarState.isHidden ? 0 : 66)
            }

            // Custom tab bar (hidden while inside a room)
            if !tabBarState.isHidden {
                CustomTabBar(selectedTab: $selectedTab)
            }
        }
        .ignoresSafeArea(.keyboard)
        .environmentObject(tabBarState)
    }
}
