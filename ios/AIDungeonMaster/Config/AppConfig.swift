import Foundation

enum AppConfig {
    static var baseURL: String {
        #if DEBUG
        UserDefaults.standard.string(forKey: "backend_url") ?? "http://10.0.0.91:8000"
        #else
        "https://your-production-domain.com"
        #endif
    }

    static var wsBaseURL: String {
        baseURL
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "http://", with: "ws://")
    }
}
