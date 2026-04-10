// Mirrors ios/AIDungeonMaster/Services/KeychainService.swift
using UnityEngine;

public class TokenStore : MonoBehaviour
{
    public static TokenStore Instance { get; private set; }

    private const string TokenKey   = "aidm_token";
    private const string GuestIdKey = "ws_guest_stable_id";

    private void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(gameObject); return; }
        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    public void   SaveToken(string token) { PlayerPrefs.SetString(TokenKey, token); PlayerPrefs.Save(); }
    public string LoadToken()             => PlayerPrefs.HasKey(TokenKey) ? PlayerPrefs.GetString(TokenKey) : null;
    public string LoadTokenOrEmpty()      => PlayerPrefs.GetString(TokenKey, "");
    public void   DeleteToken()           { PlayerPrefs.DeleteKey(TokenKey); PlayerPrefs.Save(); }
    public bool   HasToken()              => PlayerPrefs.HasKey(TokenKey);

    /// Stable guest identity across reconnects — mirrors WebSocketService.stableGuestToken()
    public string StableGuestToken()
    {
        var stored = PlayerPrefs.GetString(GuestIdKey, "");
        if (stored.Length >= 12) return "guest:" + stored;
        var id = System.Guid.NewGuid().ToString("N").ToLower();
        PlayerPrefs.SetString(GuestIdKey, id);
        PlayerPrefs.Save();
        return "guest:" + id;
    }
}
