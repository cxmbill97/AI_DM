import SwiftUI

struct ContentView: View {
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        Group {
            if auth.isLoading {
                ZStack {
                    Color(hex: "#0a0a0f").ignoresSafeArea()
                    VStack(spacing: 16) {
                        Image(systemName: "theatermasks.fill")
                            .font(.system(size: 40))
                            .foregroundStyle(LinearGradient(
                                colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                                startPoint: .top, endPoint: .bottom
                            ))
                        ProgressView()
                            .tint(Color(hex: "#c9a84c"))
                    }
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
