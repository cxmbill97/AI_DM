import SwiftUI

struct SettingsView: View {
    @AppStorage("lang") private var lang: String = "zh"
    @State private var customBaseURL: String = ""
    @EnvironmentObject var auth: AuthViewModel

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0d0d0f").ignoresSafeArea()

                List {
                    // Language
                    Section {
                        HStack {
                            Text("Language")
                                .foregroundColor(.white)
                            Spacer()
                            Picker("Language", selection: $lang) {
                                Text("中文").tag("zh")
                                Text("English").tag("en")
                            }
                            .pickerStyle(.segmented)
                            .frame(width: 150)
                        }
                    } header: {
                        Text("Game")
                            .foregroundColor(Color(hex: "#666680"))
                    }
                    .listRowBackground(Color(hex: "#141420"))

                    #if DEBUG
                    // Server URL
                    Section {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Backend URL")
                                .foregroundColor(Color(hex: "#666680"))
                                .font(.system(size: 11))
                            TextField(AppConfig.baseURL, text: $customBaseURL)
                                .textFieldStyle(.plain)
                                .foregroundColor(.white)
                                .font(.system(size: 14))
                                .autocapitalization(.none)
                                .disableAutocorrection(true)
                                .keyboardType(.URL)
                            Button("Save URL") {
                                let trimmed = customBaseURL.trimmingCharacters(in: .whitespaces)
                                if !trimmed.isEmpty {
                                    UserDefaults.standard.set(trimmed, forKey: "dev_base_url")
                                }
                            }
                            .foregroundColor(Color(hex: "#c9a84c"))
                            .font(.system(size: 13))
                        }
                        .padding(.vertical, 4)
                    } header: {
                        Text("Developer")
                            .foregroundColor(Color(hex: "#666680"))
                    }
                    .listRowBackground(Color(hex: "#141420"))
                    #endif

                    // About
                    Section {
                        HStack {
                            Text("Version")
                                .foregroundColor(.white)
                            Spacer()
                            Text(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "—")
                                .foregroundColor(Color(hex: "#666680"))
                        }
                    } header: {
                        Text("About")
                            .foregroundColor(Color(hex: "#666680"))
                    }
                    .listRowBackground(Color(hex: "#141420"))
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(Color(hex: "#0d0d0f"), for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .onAppear {
                customBaseURL = UserDefaults.standard.string(forKey: "dev_base_url") ?? ""
            }
        }
    }
}
