import SwiftUI
import Combine

@MainActor
class EconomyViewModel: ObservableObject {
    @Published var wallet: WalletState?
    @Published var lastPullResults: [CosmeticItem] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let baseURL = "http://localhost:8000"

    func loadWallet(playerId: String) async {
        isLoading = true
        defer { isLoading = false }
        guard let url = URL(string: "\(baseURL)/economy/\(playerId)") else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            wallet = try JSONDecoder().decode(WalletState.self, from: data)
        } catch { errorMessage = "Failed to load wallet" }
    }

    func earnMatchReward(playerId: String, won: Bool = false) async {
        guard let url = URL(string: "\(baseURL)/economy/\(playerId)/earn_match?won=\(won)") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            if let result = try? JSONDecoder().decode(EarnResult.self, from: data) {
                wallet?.coins = result.coins
            }
        } catch { errorMessage = "Failed to earn reward" }
    }

    func gachaPull(playerId: String, count: Int = 1) async {
        guard let url = URL(string: "\(baseURL)/economy/\(playerId)/gacha?count=\(count)") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            let result = try JSONDecoder().decode(GachaResult.self, from: data)
            if result.success {
                lastPullResults = result.results ?? []
                wallet?.coins = result.coins
            } else {
                errorMessage = result.error ?? "Pull failed"
            }
        } catch { errorMessage = "Gacha pull failed" }
    }
}
