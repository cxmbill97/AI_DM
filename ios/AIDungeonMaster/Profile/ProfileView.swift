import SwiftUI

struct ProfileView: View {
    @StateObject private var vm = ProfileViewModel()
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0d0d0f").ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        // Avatar
                        ZStack {
                            Circle()
                                .fill(Color(hex: "#1e1e28"))
                                .frame(width: 80, height: 80)
                            Text(vm.displayName.prefix(1).uppercased())
                                .font(.system(size: 32, weight: .bold))
                                .foregroundColor(Color(hex: "#c9a84c"))
                        }
                        .padding(.top, 24)

                        VStack(spacing: 4) {
                            Text(vm.displayName.isEmpty ? "—" : vm.displayName)
                                .font(.system(size: 20, weight: .semibold))
                                .foregroundColor(.white)
                            if !vm.email.isEmpty {
                                Text(vm.email)
                                    .font(.system(size: 13))
                                    .foregroundColor(Color(hex: "#666680"))
                            }
                        }

                        // History section placeholder
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Recent Games")
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(Color(hex: "#666680"))
                                .padding(.horizontal, 16)
                            Text("Game history coming soon")
                                .font(.system(size: 14))
                                .foregroundColor(Color(hex: "#44445a"))
                                .frame(maxWidth: .infinity, alignment: .center)
                                .padding(.vertical, 32)
                        }

                        Spacer(minLength: 40)

                        Button("Sign Out") {
                            auth.signOut()
                        }
                        .font(.system(size: 14, weight: .medium))
                        .foregroundColor(Color(hex: "#f87171"))
                        .padding(.horizontal, 24).padding(.vertical, 12)
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color(hex: "#f87171").opacity(0.4), lineWidth: 1))
                        .padding(.bottom, 32)
                    }
                }

                if vm.isLoading {
                    ProgressView()
                        .tint(Color(hex: "#c9a84c"))
                }
            }
            .navigationTitle("Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(hex: "#0d0d0f"), for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .task { await vm.load() }
        }
    }
}
