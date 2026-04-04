import SwiftUI
import AuthenticationServices

@MainActor
final class AuthViewModel: NSObject, ObservableObject {
    @Published var user: User?
    @Published var isLoading = true
    @Published var error: String?
    @Published var debugRoomId: String? = nil

    override init() {
        super.init()
        #if DEBUG
        let args = ProcessInfo.processInfo.arguments
        if let idx = args.firstIndex(of: "--debug-token"), idx + 1 < args.count {
            KeychainService.save(token: args[idx + 1])
        }
        debugRoomId = args.firstIndex(of: "--debug-room").map { args[$0 + 1] }
        #endif
        Task { await validateSession() }
    }

    // MARK: - Session

    func validateSession() async {
        guard KeychainService.loadToken() != nil else {
            isLoading = false
            return
        }
        do {
            user = try await APIService.shared.getMe()
        } catch APIError.unauthorized {
            KeychainService.deleteToken()
        } catch {}
        isLoading = false
    }

    func signOut() {
        KeychainService.deleteToken()
        user = nil
    }

    func handleDeepLink(_ url: URL) {
        guard url.scheme == "aidm", url.host == "auth" else { return }
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        if let token = components?.queryItems?.first(where: { $0.name == "token" })?.value {
            KeychainService.save(token: token)
            Task { await validateSession() }
        } else {
            error = "Google Sign-In failed"
        }
    }

    // MARK: - Google Sign-In

    func googleSignIn() {
        guard let url = URL(string: "\(AppConfig.baseURL)/auth/google/mobile") else { return }
        let session = ASWebAuthenticationSession(
            url: url,
            callbackURLScheme: "aidm"
        ) { [weak self] callbackURL, sessionError in
            guard let self else { return }
            if let sessionError {
                let nsError = sessionError as NSError
                if nsError.code != ASWebAuthenticationSessionError.canceledLogin.rawValue {
                    Task { @MainActor in self.error = sessionError.localizedDescription }
                }
                return
            }
            guard let url = callbackURL else { return }
            Task { @MainActor in self.handleDeepLink(url) }
        }
        session.presentationContextProvider = self
        session.prefersEphemeralWebBrowserSession = false
        session.start()
    }

    // MARK: - Apple Sign-In

    func appleSignIn() {
        let request = ASAuthorizationAppleIDProvider().createRequest()
        request.requestedScopes = [.fullName, .email]
        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.performRequests()
    }
}

// MARK: - ASWebAuthenticationPresentationContextProviding

extension AuthViewModel: ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
            .first { $0.isKeyWindow } ?? ASPresentationAnchor()
    }
}

// MARK: - ASAuthorizationControllerDelegate

extension AuthViewModel: ASAuthorizationControllerDelegate {
    func authorizationController(
        controller: ASAuthorizationController,
        didCompleteWithAuthorization authorization: ASAuthorization
    ) {
        guard let cred = authorization.credential as? ASAuthorizationAppleIDCredential,
              let tokenData = cred.identityToken,
              let tokenString = String(data: tokenData, encoding: .utf8) else {
            error = "Apple Sign-In: missing token"
            return
        }
        let fullName = [cred.fullName?.givenName, cred.fullName?.familyName]
            .compactMap { $0 }.joined(separator: " ")

        Task {
            do {
                struct AppleBody: Encodable { let identity_token: String; let full_name: String }
                let resp: [String: String] = try await APIService.shared.request(
                    "/auth/apple",
                    method: "POST",
                    body: AppleBody(identity_token: tokenString, full_name: fullName)
                )
                guard let token = resp["token"] else { throw APIError.httpError(500, "No token") }
                KeychainService.save(token: token)
                await validateSession()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        let nsError = error as NSError
        if nsError.code != ASAuthorizationError.canceled.rawValue {
            self.error = error.localizedDescription
        }
    }
}
