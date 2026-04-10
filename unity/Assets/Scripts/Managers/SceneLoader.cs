// Scene transition manager — persists across all scenes (DontDestroyOnLoad).
// Mirrors the implicit navigation stack pattern in the SwiftUI app.
using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

public class SceneLoader : MonoBehaviour
{
    public static SceneLoader Instance { get; private set; }

    // Simple key-value store for passing data between scenes
    private static readonly Dictionary<string, string> _sceneData = new();

    private void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(gameObject); return; }
        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    // ── Public API ──────────────────────────────────────────────────────────

    public static void SetData(string key, string value) => _sceneData[key] = value;
    public static string GetData(string key)             => _sceneData.TryGetValue(key, out var v) ? v : null;
    public static void ClearData(string key)             => _sceneData.Remove(key);

    public static void LoadScene(string sceneName)
        => Instance.StartCoroutine(Instance.LoadAsync(sceneName));

    /// Overload that accepts key-value pairs to store before loading.
    public static void LoadScene(string sceneName, params (string key, string value)[] data)
    {
        foreach (var (key, value) in data) SetData(key, value);
        LoadScene(sceneName);
    }

    /// Convenience overload that pre-populates a roomId before loading.
    public static void LoadGameRoom(string roomId)
    {
        SetData("roomId", roomId);
        LoadScene("GameRoom");
    }

    public static void LoadWaitingRoom(string roomId, string gameType = "turtle_soup")
    {
        SetData("roomId", roomId);
        SetData("gameType", gameType);
        LoadScene("WaitingRoom");
    }

    // ── Internal ────────────────────────────────────────────────────────────

    private IEnumerator LoadAsync(string sceneName)
    {
        var op = SceneManager.LoadSceneAsync(sceneName);
        op.allowSceneActivation = false;

        while (op.progress < 0.9f) yield return null;

        // Small buffer frame so outgoing scene can finish cleanup
        yield return new WaitForEndOfFrame();
        op.allowSceneActivation = true;
    }
}
