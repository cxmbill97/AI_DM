import SwiftUI
import Combine

@MainActor
class PetViewModel: ObservableObject {
    @Published var pet: PetState?
    @Published var lastComment: String = ""
    @Published var isLoading = false

    private let baseURL = "http://localhost:8000"

    func loadPet(playerId: String) async {
        isLoading = true
        defer { isLoading = false }
        guard let url = URL(string: "\(baseURL)/pet/\(playerId)") else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            pet = try JSONDecoder().decode(PetState.self, from: data)
        } catch { print("Pet load error: \(error)") }
    }

    func renamePet(playerId: String, newName: String) async {
        guard let url = URL(string: "\(baseURL)/pet/\(playerId)/rename") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONEncoder().encode(["name": newName])
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            pet = try JSONDecoder().decode(PetState.self, from: data)
        } catch { print("Rename error: \(error)") }
    }

    func fetchComment(playerId: String, context: String) async {
        guard let url = URL(string: "\(baseURL)/pet/\(playerId)/comment") else { return }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try? JSONEncoder().encode(["context": context])
        do {
            let (data, _) = try await URLSession.shared.data(for: req)
            if let json = try? JSONDecoder().decode([String: String].self, from: data) {
                lastComment = json["comment"] ?? ""
            }
        } catch { print("Comment error: \(error)") }
    }
}
