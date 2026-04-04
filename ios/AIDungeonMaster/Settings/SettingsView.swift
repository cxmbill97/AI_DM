import SwiftUI

struct SettingsView: View {
    @AppStorage("lang") private var lang: String = "zh"

    var body: some View {
        NavigationStack {
            ZStack {
                Color(hex: "#0a0a0f").ignoresSafeArea()

                List {
                    Section {
                        languagePicker
                    } header: {
                        sectionHeader("Game")
                    }
                    .listRowBackground(Color(hex: "#16151f"))

                    #if DEBUG
                    Section {
                        DevServerRow()
                    } header: {
                        sectionHeader("Developer")
                    }
                    .listRowBackground(Color(hex: "#16151f"))
                    #endif

                    Section {
                        aboutRow("Version", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")
                        aboutRow("Build", value: Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "1")
                    } header: {
                        sectionHeader("About")
                    }
                    .listRowBackground(Color(hex: "#16151f"))
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.large)
            .toolbarBackground(Color(hex: "#0a0a0f"), for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 10, weight: .bold))
            .foregroundColor(Color(hex: "#44446a"))
            .tracking(1.5)
    }

    private var languagePicker: some View {
        HStack {
            Image(systemName: "globe")
                .foregroundColor(Color(hex: "#c9a84c"))
                .frame(width: 28)
            Text("Language")
                .foregroundColor(.white)
            Spacer()
            Picker("", selection: $lang) {
                Text("中文").tag("zh")
                Text("English").tag("en")
            }
            .pickerStyle(.segmented)
            .frame(width: 140)
        }
        .padding(.vertical, 2)
    }

    private func aboutRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label).foregroundColor(.white)
            Spacer()
            Text(value).foregroundColor(Color(hex: "#44446a"))
        }
    }
}

#if DEBUG
private struct DevServerRow: View {
    @State private var url: String = UserDefaults.standard.string(forKey: "dev_base_url") ?? ""

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "server.rack")
                    .foregroundColor(Color(hex: "#c9a84c"))
                    .frame(width: 28)
                Text("Backend URL")
                    .foregroundColor(.white)
            }
            TextField(AppConfig.baseURL, text: $url)
                .textFieldStyle(.plain)
                .foregroundColor(Color(hex: "#c9a84c"))
                .font(.system(size: 13, design: .monospaced))
                .autocapitalization(.none)
                .disableAutocorrection(true)
                .keyboardType(.URL)
            Button("Save") {
                UserDefaults.standard.set(url.trimmingCharacters(in: .whitespaces), forKey: "dev_base_url")
            }
            .font(.system(size: 12, weight: .semibold))
            .foregroundColor(Color(hex: "#c9a84c"))
        }
        .padding(.vertical, 4)
    }
}
#endif
