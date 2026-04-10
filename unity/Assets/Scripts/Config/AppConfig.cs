// Mirrors ios/AIDungeonMaster/Config/AppConfig.swift
using UnityEngine;

public static class AppConfig
{
    private const string BaseURLKey = "backend_url";
    private const string DefaultURL  = "http://localhost:8000";

    public static string BaseURL =>
        PlayerPrefs.GetString(BaseURLKey, DefaultURL).TrimEnd('/');

    // Convert http → ws, https → wss
    public static string WsBaseURL
    {
        get
        {
            var url = BaseURL;
            return url.StartsWith("https://")
                ? "wss://" + url.Substring(8)
                : "ws://"  + url.Substring(7);
        }
    }

    public static void SetBaseURL(string url)
    {
        PlayerPrefs.SetString(BaseURLKey, url.TrimEnd('/'));
        PlayerPrefs.Save();
    }
}
