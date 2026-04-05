import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        ZStack {
            // Rich background
            LinearGradient(
                colors: [Color(hex: "#0a0a0f"), Color(hex: "#12101a"), Color(hex: "#0d0810")],
                startPoint: .topLeading, endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            // Subtle grid pattern
            Canvas { ctx, size in
                let spacing: CGFloat = 40
                let cols = Int(size.width / spacing) + 2
                let rows = Int(size.height / spacing) + 2
                var path = Path()
                for i in 0...cols {
                    let x = CGFloat(i) * spacing
                    path.move(to: CGPoint(x: x, y: 0))
                    path.addLine(to: CGPoint(x: x, y: size.height))
                }
                for i in 0...rows {
                    let y = CGFloat(i) * spacing
                    path.move(to: CGPoint(x: 0, y: y))
                    path.addLine(to: CGPoint(x: size.width, y: y))
                }
                ctx.stroke(path, with: .color(Color.white.opacity(0.025)), lineWidth: 0.5)
            }
            .ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Logo area
                VStack(spacing: 16) {
                    ZStack {
                        Circle()
                            .fill(
                                RadialGradient(
                                    colors: [Color(hex: "#c9a84c").opacity(0.3), Color.clear],
                                    center: .center, startRadius: 0, endRadius: 50
                                )
                            )
                            .frame(width: 100, height: 100)

                        Image(systemName: "theatermasks.fill")
                            .font(.system(size: 44))
                            .foregroundStyle(
                                LinearGradient(
                                    colors: [Color(hex: "#e8c96a"), Color(hex: "#a07830")],
                                    startPoint: .top, endPoint: .bottom
                                )
                            )
                    }

                    VStack(spacing: 6) {
                        Text("AI DM")
                            .font(.system(size: 38, weight: .black, design: .serif))
                            .foregroundStyle(
                                LinearGradient(
                                    colors: [Color(hex: "#f0d878"), Color(hex: "#c9a84c")],
                                    startPoint: .top, endPoint: .bottom
                                )
                            )
                            .tracking(4)

                        Text("Mystery awaits")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(Color(hex: "#6060a0"))
                            .tracking(2)
                    }
                }
                .padding(.bottom, 52)

                // Error
                if let error = auth.error {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 12))
                        Text(error)
                            .font(.system(size: 13))
                    }
                    .foregroundColor(Color(hex: "#f87171"))
                    .padding(.horizontal, 20).padding(.vertical, 10)
                    .background(Color(hex: "#f87171").opacity(0.08))
                    .cornerRadius(10)
                    .padding(.horizontal, 32)
                    .padding(.bottom, 20)
                }

                // Auth buttons
                VStack(spacing: 12) {
                    Button { auth.googleSignIn() } label: {
                        HStack(spacing: 12) {
                            GoogleLogoView().frame(width: 18, height: 18)
                            Text("Continue with Google")
                                .font(.system(size: 15, weight: .semibold))
                                .foregroundColor(.white)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 15)
                        .background(
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color(hex: "#1c1c2e"))
                                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color(hex: "#2e2e4a"), lineWidth: 1))
                        )
                    }

                    SignInWithAppleButton(.continue) { req in
                        req.requestedScopes = [.fullName, .email]
                    } onCompletion: { _ in
                        auth.appleSignIn()
                    }
                    .signInWithAppleButtonStyle(.white)
                    .frame(height: 50)
                    .clipShape(RoundedRectangle(cornerRadius: 14))

                    #if DEBUG
                    DevLoginView()
                    #endif
                }
                .padding(.horizontal, 28)

                Spacer()

                Text("Your secrets are safe with us")
                    .font(.system(size: 11))
                    .foregroundColor(Color(hex: "#333360"))
                    .tracking(1)
                    .padding(.bottom, 36)
            }
        }
    }
}

// MARK: - Dev login

private struct DevLoginView: View {
    @EnvironmentObject var auth: AuthViewModel
    @State private var name = ""

    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Rectangle().fill(Color(hex: "#2e2e4a")).frame(height: 1)
                Text("DEV")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(Color(hex: "#444480"))
                    .tracking(2)
                Rectangle().fill(Color(hex: "#2e2e4a")).frame(height: 1)
            }
            .padding(.top, 4)

            HStack(spacing: 8) {
                TextField("Name", text: $name)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 11)
                    .background(Color(hex: "#1c1c2e"))
                    .foregroundColor(.white)
                    .font(.system(size: 14))
                    .cornerRadius(10)
                    .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color(hex: "#2e2e4a"), lineWidth: 1))

                Button("Go") {
                    let t = name.trimmingCharacters(in: .whitespaces)
                    guard !t.isEmpty else { return }
                    Task {
                        let token = await DevLoginHelper.fetchToken(baseURL: AppConfig.baseURL, name: t)
                        if let token {
                            KeychainService.save(token: token)
                            await auth.validateSession()
                        } else {
                            auth.error = "Dev login unavailable (Google creds active)"
                        }
                    }
                }
                .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                .padding(.horizontal, 18)
                .padding(.vertical, 11)
                .background(Color(hex: "#c9a84c"))
                .foregroundColor(.black)
                .font(.system(size: 14, weight: .bold))
                .cornerRadius(10)
            }
        }
        .padding(.top, 4)
    }
}

// MARK: - DevLoginHelper

enum DevLoginHelper {
    static func fetchToken(baseURL: String, name: String) async -> String? {
        guard let encoded = name.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let url = URL(string: "\(baseURL)/auth/dev-login/mobile?name=\(encoded)") else { return nil }

        final class RedirectCatcher: NSObject, URLSessionTaskDelegate {
            var capturedToken: String?
            func urlSession(_ session: URLSession, task: URLSessionTask,
                            willPerformHTTPRedirection response: HTTPURLResponse,
                            newRequest request: URLRequest,
                            completionHandler: @escaping (URLRequest?) -> Void) {
                if let url = request.url, url.scheme == "aidm" {
                    capturedToken = URLComponents(url: url, resolvingAgainstBaseURL: false)?
                        .queryItems?.first(where: { $0.name == "token" })?.value
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
