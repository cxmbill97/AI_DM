import SwiftUI

@main
struct AIDungeonMasterApp: App {
    @StateObject private var auth = AuthViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(auth)
                .onOpenURL { url in
                    auth.handleDeepLink(url)
                }
        }
    }
}
