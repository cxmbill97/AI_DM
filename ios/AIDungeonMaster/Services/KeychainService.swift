import Foundation
import Security

enum KeychainService {
    private static let key = "ai_dm_token"
    private static let service = "com.aidm.AIDungeonMaster"

    // In the simulator without code signing, Keychain can fail silently.
    // Use UserDefaults as a fallback in DEBUG builds only.
    private static let userDefaultsKey = "AIDM_token_debug"

    static func save(token: String) {
        #if DEBUG
        UserDefaults.standard.set(token, forKey: userDefaultsKey)
        #endif

        let data = Data(token.utf8)
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: key,
        ]
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData] = data
        SecItemAdd(item as CFDictionary, nil)
    }

    static func loadToken() -> String? {
        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: key,
            kSecReturnData: true,
            kSecMatchLimit: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecSuccess, let data = result as? Data, let tok = String(data: data, encoding: .utf8) {
            return tok
        }

        #if DEBUG
        // Keychain fails without code signing in simulator; fall back to UserDefaults
        return UserDefaults.standard.string(forKey: userDefaultsKey)
        #else
        return nil
        #endif
    }

    static func deleteToken() {
        #if DEBUG
        UserDefaults.standard.removeObject(forKey: userDefaultsKey)
        #endif

        let query: [CFString: Any] = [
            kSecClass: kSecClassGenericPassword,
            kSecAttrService: service,
            kSecAttrAccount: key,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
