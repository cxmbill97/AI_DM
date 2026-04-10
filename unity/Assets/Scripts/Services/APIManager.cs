// Mirrors ios/AIDungeonMaster/Services/APIService.swift
using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json;

public class ApiException : Exception
{
    public int    StatusCode { get; }
    public ApiException(int code, string message) : base(message) { StatusCode = code; }
    public ApiException(string message)           : base(message) { StatusCode = 0; }
}

public class APIManager : MonoBehaviour
{
    public static APIManager Instance { get; private set; }

    private void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(gameObject); return; }
        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    // ── Core request helper ──────────────────────────────────────────────────

    private async UniTask<string> Request(
        string path,
        string method  = "GET",
        object body    = null,
        bool   noAuth  = false)
    {
        var url = AppConfig.BaseURL + path;
        var req = new UnityWebRequest(url, method);

        // Auth header
        if (!noAuth)
        {
            var token = TokenStore.Instance.LoadTokenOrEmpty();
            if (!string.IsNullOrEmpty(token))
                req.SetRequestHeader("Authorization", "Bearer " + token);
        }

        // Body
        if (body != null)
        {
            var json  = JsonConvert.SerializeObject(body);
            var bytes = Encoding.UTF8.GetBytes(json);
            req.uploadHandler   = new UploadHandlerRaw(bytes);
            req.SetRequestHeader("Content-Type", "application/json");
        }

        req.downloadHandler = new DownloadHandlerBuffer();

        await req.SendWebRequest().ToUniTask();

        if (req.result != UnityWebRequest.Result.Success)
        {
            int code = (int)req.responseCode;
            if (code == 401) throw new ApiException(401, "Unauthorized");
            // Try to extract detail from JSON body
            string detail = req.downloadHandler.text ?? req.error;
            try
            {
                var err = JsonConvert.DeserializeObject<Dictionary<string, string>>(detail);
                if (err != null && err.TryGetValue("detail", out var d)) detail = d;
            }
            catch { /* use raw error */ }
            throw new ApiException(code, detail);
        }
        return req.downloadHandler.text;
    }

    private async UniTask<T> Request<T>(string path, string method = "GET", object body = null)
    {
        var json = await Request(path, method, body);
        return JsonConvert.DeserializeObject<T>(json);
    }

    // ── Auth / User ──────────────────────────────────────────────────────────

    public UniTask<User> GetMe()
        => Request<User>("/api/me");

    // ── Puzzles & Scripts ────────────────────────────────────────────────────

    public UniTask<List<PuzzleSummary>> ListPuzzles(string lang = "zh")
        => Request<List<PuzzleSummary>>($"/api/puzzles?lang={lang}");

    public UniTask<List<ScriptSummary>> ListScripts(string lang = "zh")
        => Request<List<ScriptSummary>>($"/api/scripts?lang={lang}");

    public UniTask<List<CommunityScript>> GetCommunityScripts(string lang = "zh", string search = "")
        => Request<List<CommunityScript>>($"/api/community/scripts?lang={lang}&search={UnityWebRequest.EscapeURL(search)}");

    public UniTask<int> LikeScript(string scriptId)
        => Request<int>($"/api/community/scripts/{scriptId}/like", "POST");

    // ── Rooms ────────────────────────────────────────────────────────────────

    public UniTask<List<ActiveRoom>> GetActiveRooms()
        => Request<List<ActiveRoom>>("/api/rooms");

    public UniTask<CreateRoomResponse> CreateRoom(
        string gameType,
        string puzzleId  = null,
        string scriptId  = null,
        string lang      = "zh",
        bool   isPublic  = false,
        bool   lobbyMode = true,
        bool   turnMode  = false)
    {
        var body = new Dictionary<string, object>
        {
            ["game_type"]   = gameType,
            ["language"]    = lang,
            ["is_public"]   = isPublic,
            ["lobby_mode"]  = lobbyMode,
            ["turn_mode"]   = turnMode,
        };
        if (!string.IsNullOrEmpty(puzzleId)) body["puzzle_id"] = puzzleId;
        if (!string.IsNullOrEmpty(scriptId)) body["script_id"] = scriptId;
        return Request<CreateRoomResponse>("/api/rooms", "POST", body);
    }

    public UniTask StartRoom(string roomId)
        => Request($"/api/rooms/{roomId}/start", "POST");

    public UniTask PatchRoom(string roomId, bool? isPublic = null, int? maxPlayers = null)
    {
        var body = new Dictionary<string, object>();
        if (isPublic   != null) body["is_public"]   = isPublic;
        if (maxPlayers != null) body["max_players"]  = maxPlayers;
        return Request($"/api/rooms/{roomId}", "PATCH", body);
    }

    public UniTask CompleteRoom(string roomId, string outcome = "success")
        => Request($"/api/rooms/{roomId}/complete", "POST", new { outcome });

    // ── Favorites / History ──────────────────────────────────────────────────

    public UniTask<List<FavoriteItem>> GetFavorites()
        => Request<List<FavoriteItem>>("/api/favorites");

    public UniTask AddFavorite(string itemType, string itemId)
        => Request($"/api/favorites/{itemType}/{itemId}", "POST");

    public UniTask RemoveFavorite(string itemType, string itemId)
        => Request($"/api/favorites/{itemType}/{itemId}", "DELETE");

    public UniTask<List<HistoryItem>> GetHistory()
        => Request<List<HistoryItem>>("/api/history");
}
