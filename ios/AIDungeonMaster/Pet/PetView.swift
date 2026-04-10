import SwiftUI

struct PetView: View {
    @StateObject private var vm = PetViewModel()
    @EnvironmentObject private var auth: AuthViewModel
    @State private var showRename = false
    @State private var newName = ""

    private var playerId: String { auth.user?.id ?? "" }

    var body: some View {
        VStack(spacing: 20) {
            if let pet = vm.pet {
                // Pet avatar
                VStack {
                    Text(pet.moodEmoji)
                        .font(.system(size: 80))
                    Text(pet.name)
                        .font(.title2.bold())
                    Text("Level \(pet.level) \(pet.species.capitalized)")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }

                // XP Bar
                VStack(alignment: .leading, spacing: 4) {
                    Text("XP: \(pet.xp)")
                        .font(.caption)
                    ProgressView(value: Double(pet.xp % 100), total: 100)
                        .accentColor(.blue)
                    if pet.xpToNextLevel > 0 {
                        Text("\(pet.xpToNextLevel) XP to next level")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal)

                // Last comment bubble
                if !vm.lastComment.isEmpty {
                    HStack {
                        Image(systemName: "bubble.left.fill")
                            .foregroundColor(.blue)
                        Text(vm.lastComment)
                            .font(.body)
                            .italic()
                    }
                    .padding()
                    .background(Color.blue.opacity(0.1))
                    .cornerRadius(12)
                    .padding(.horizontal)
                }

                // Memory log
                if !pet.memory.isEmpty {
                    VStack(alignment: .leading) {
                        Text("Memory")
                            .font(.headline)
                        ForEach(pet.memory.suffix(5), id: \.self) { event in
                            Text("• \(event)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                }

                // Actions
                HStack(spacing: 16) {
                    Button("Rename") { showRename = true }
                        .buttonStyle(.bordered)
                    Button("Cheer!") {
                        Task { await vm.fetchComment(playerId: playerId, context: "correct") }
                    }
                    .buttonStyle(.borderedProminent)
                }
            } else {
                ProgressView("Loading pet...")
            }
        }
        .task { await vm.loadPet(playerId: playerId) }
        .alert("Rename Pet", isPresented: $showRename) {
            TextField("New name", text: $newName)
            Button("Save") {
                Task { await vm.renamePet(playerId: playerId, newName: newName) }
            }
            Button("Cancel", role: .cancel) {}
        }
        .navigationTitle("Your Pet")
    }
}
