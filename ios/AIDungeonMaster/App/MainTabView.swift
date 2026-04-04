import SwiftUI

struct MainTabView: View {
    var body: some View {
        TabView {
            LobbyView()
                .tabItem {
                    Label("Games", systemImage: "gamecontroller.fill")
                }

            ProfileView()
                .tabItem {
                    Label("Profile", systemImage: "person.fill")
                }

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
        }
        .tint(Color(hex: "#c9a84c"))
        .onAppear {
            let tabBarAppearance = UITabBarAppearance()
            tabBarAppearance.configureWithOpaqueBackground()
            tabBarAppearance.backgroundColor = UIColor(red: 0.05, green: 0.05, blue: 0.06, alpha: 1)
            UITabBar.appearance().standardAppearance = tabBarAppearance
            UITabBar.appearance().scrollEdgeAppearance = tabBarAppearance
        }
    }
}
