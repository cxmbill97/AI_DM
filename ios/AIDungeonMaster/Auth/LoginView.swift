import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        ZStack {
            Color(hex: "#0d0d0f").ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                Image(systemName: "clock.circle.fill")
                    .font(.system(size: 56))
                    .foregroundColor(Color(hex: "#c9a84c"))
                    .padding(.bottom, 20)

                Text("AI DM")
                    .font(.system(size: 32, weight: .black))
                    .foregroundColor(.white)

                Text("AI-powered mystery game master")
                    .font(.system(size: 14))
                    .foregroundColor(Color(hex: "#666680"))
                    .padding(.top, 8)
                    .padding(.bottom, 40)

                if let error = auth.error {
                    Text(error)
                        .font(.system(size: 13))
                        .foregroundColor(Color(hex: "#f87171"))
                        .padding(.horizontal, 24)
                        .multilineTextAlignment(.center)
                        .padding(.bottom, 16)
                }

                VStack(spacing: 12) {
                    Button {
                        auth.googleSignIn()
                    } label: {
                        HStack(spacing: 12) {
                            GoogleLogoView()
                                .frame(width: 20, height: 20)
                            Text("Sign in with Google")
                                .font(.system(size: 15, weight: .medium))
                                .foregroundColor(.white)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color(hex: "#1e1e28"))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color(hex: "#2e2e3d"), lineWidth: 1))
                        .cornerRadius(12)
                    }

                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { _ in
                        auth.appleSignIn()
                    }
                    .signInWithAppleButtonStyle(.white)
                    .frame(height: 50)
                    .cornerRadius(12)

                    #if DEBUG
                    DevLoginView()
                    #endif
                }
                .padding(.horizontal, 32)

                Spacer()

                Text("Sign in to save favorites and game history")
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#44445a"))
                    .padding(.bottom, 32)
            }
        }
    }
}

// MARK: - Dev login (DEBUG only)

private struct DevLoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var name = ""

    var body: some View {
        VStack(spacing: 8) {
            Divider().background(Color(hex: "#2e2e3d")).padding(.top, 8)
            Text("Dev login")
                .font(.system(size: 11))
                .foregroundColor(Color(hex: "#44445a"))
            HStack(spacing: 8) {
                TextField("Your name", text: $name)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(Color(hex: "#1e1e28"))
                    .cornerRadius(8)
                    .foregroundColor(.white)
                    .font(.system(size: 14))
                Button("Go") {
                    let trimmed = name.trimmingCharacters(in: .whitespaces)
                    guard !trimmed.isEmpty else { return }
                    Task {
                        let token = await DevLoginHelper.fetchToken(baseURL: AppConfig.baseURL, name: trimmed)
                        if let token {
                            KeychainService.save(token: token)
                            await auth.validateSession()
                        } else {
                            auth.error = "Dev login failed"
                        }
                    }
                }
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Color(hex: "#c9a84c"))
                .foregroundColor(.black)
                .font(.system(size: 14, weight: .semibold))
                .cornerRadius(8)
            }
        }
        .padding(.top, 4)
    }
}

// MARK: - DevLoginHelper

enum DevLoginHelper {
    static func fetchToken(baseURL: String, name: String) async -> String? {
        guard let encoded = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(baseURL)/auth/dev-login?name=\(encoded)") else { return nil }

        final class RedirectCatcher: NSObject, URLSessionTaskDelegate {
            var capturedToken: String?
            func urlSession(
                _ session: URLSession,
                task: URLSessionTask,
                willPerformHTTPRedirection response: HTTPURLResponse,
                newRequest request: URLRequest,
                completionHandler: @escaping (URLRequest?) -> Void
            ) {
                if let url = request.url, url.scheme == "aidm" {
                    let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
                    capturedToken = components?.queryItems?.first(where: { $0.name == "token" })?.value
                    completionHandler(nil)
                } else {
                    completionHandler(request)
                }
            }
        }

        let catcher = RedirectCatcher()
        let session = URLSession(configuration: .default, delegate: catcher, delegateQueue: nil)
        _ = try? await session.data(from: url)
        return catcher.capturedToken
    }
}

// MARK: - Google Logo

private struct GoogleLogoView: View {
    var body: some View {
        Canvas { ctx, size in
            let s = size.width / 24
            ctx.fill(Path { p in
                p.move(to: CGPoint(x: 22.56*s, y: 12.25*s))
                p.addLine(to: CGPoint(x: 12*s, y: 12.25*s))
                p.addLine(to: CGPoint(x: 12*s, y: 16.51*s))
                p.addLine(to: CGPoint(x: 17.92*s, y: 16.51*s))
                p.addLine(to: CGPoint(x: 22.56*s, y: 12.25*s))
            }, with: .color(Color(red: 66/255, green: 133/255, blue: 244/255)))
            ctx.fill(Path { p in
                p.move(to: CGPoint(x: 12*s, y: 23*s))
                p.addLine(to: CGPoint(x: 19.28*s, y: 20.34*s))
                p.addLine(to: CGPoint(x: 15.71*s, y: 17.57*s))
                p.addLine(to: CGPoint(x: 12*s, y: 18.63*s))
                p.addLine(to: CGPoint(x: 12*s, y: 23*s))
            }, with: .color(Color(red: 52/255, green: 168/255, blue: 83/255)))
            ctx.fill(Path { p in
                p.move(to: CGPoint(x: 5.84*s, y: 14.09*s))
                p.addLine(to: CGPoint(x: 2.18*s, y: 16.93*s))
                p.addLine(to: CGPoint(x: 2.18*s, y: 7.07*s))
                p.addLine(to: CGPoint(x: 5.84*s, y: 9.91*s))
                p.addLine(to: CGPoint(x: 5.84*s, y: 14.09*s))
            }, with: .color(Color(red: 251/255, green: 188/255, blue: 5/255)))
            ctx.fill(Path { p in
                p.move(to: CGPoint(x: 12*s, y: 5.38*s))
                p.addLine(to: CGPoint(x: 16.21*s, y: 7.02*s))
                p.addLine(to: CGPoint(x: 19.36*s, y: 3.87*s))
                p.addLine(to: CGPoint(x: 12*s, y: 1*s))
                p.addLine(to: CGPoint(x: 2.18*s, y: 7.07*s))
                p.addLine(to: CGPoint(x: 5.84*s, y: 9.91*s))
                p.addLine(to: CGPoint(x: 12*s, y: 5.38*s))
            }, with: .color(Color(red: 234/255, green: 67/255, blue: 53/255)))
        }
    }
}
