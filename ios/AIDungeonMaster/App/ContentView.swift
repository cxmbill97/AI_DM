import SwiftUI

struct ContentView: View {
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        Group {
            if auth.isLoading {
                ZStack {
                    Color(hex: "#0d0d0f").ignoresSafeArea()
                    ProgressView()
                        .tint(Color(hex: "#c9a84c"))
                }
            } else if auth.user != nil {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .preferredColorScheme(.dark)
    }
}
