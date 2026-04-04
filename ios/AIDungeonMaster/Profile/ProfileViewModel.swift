import Foundation

@MainActor
final class ProfileViewModel: ObservableObject {
    @Published var displayName: String = ""
    @Published var email: String = ""
    @Published var avatarUrl: String = ""
    @Published var isLoading = false
    @Published var error: String?

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let user = try await APIService.shared.getMe()
            displayName = user.name
            email = user.email
            avatarUrl = user.avatar_url
        } catch {
            self.error = error.localizedDescription
        }
    }
}
