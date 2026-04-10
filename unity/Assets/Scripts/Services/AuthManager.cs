// Mirrors ios/AIDungeonMaster/Auth/AuthViewModel.swift
using System;
using System.Threading;
using UnityEngine;
using Cysharp.Threading.Tasks;

public class AuthManager : MonoBehaviour
{
    public static AuthManager Instance { get; private set; }

    public User CurrentUser { get; private set; }
    public bool IsLoading   { get; private set; }
    public string Error     { get; private set; }

    public event Action OnUserChanged;

    private void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(gameObject); return; }
        Instance = this;
        DontDestroyOnLoad(gameObject);

        // Deep link handling (Google OAuth callback: aidm://auth?token=...)
        Application.deepLinkActivated += OnDeepLink;
        if (!string.IsNullOrEmpty(Application.absoluteURL))
            OnDeepLink(Application.absoluteURL);
    }

    private void OnDestroy()
    {
        Application.deepLinkActivated -= OnDeepLink;
    }

    // ── Session ─────────────────────────────────────────────────────────────

    /// Called from BootController on app start. Returns true if session is valid.
    public async UniTask<bool> ValidateSession()
    {
        var token = TokenStore.Instance.LoadToken();
        if (string.IsNullOrEmpty(token)) return false;

        IsLoading = true;
        try
        {
            // 5-second timeout — mirrors AuthViewModel.withTimeout(seconds: 5)
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            var user = await APIManager.Instance.GetMe().AttachExternalCancellation(cts.Token);
            CurrentUser = user;
            OnUserChanged?.Invoke();
            return true;
        }
        catch (ApiException ex) when (ex.StatusCode == 401)
        {
            TokenStore.Instance.DeleteToken();
            return false;
        }
        catch
        {
            // Network error or timeout — treat as unauthenticated
            return false;
        }
        finally
        {
            IsLoading = false;
        }
    }

    public void SignOut()
    {
        TokenStore.Instance.DeleteToken();
        CurrentUser = null;
        OnUserChanged?.Invoke();
    }

    // ── Google OAuth ─────────────────────────────────────────────────────────

    public void GoogleSignIn()
    {
        var url = $"{AppConfig.BaseURL}/auth/google/mobile";
        Application.OpenURL(url);
    }

    // ── Deep link handler ────────────────────────────────────────────────────

    private void OnDeepLink(string url)
    {
        if (string.IsNullOrEmpty(url)) return;

        // aidm://auth?token=...
        if (url.StartsWith("aidm://auth"))
        {
            var uri   = new Uri(url);
            var query = System.Web.HttpUtility.ParseQueryString(uri.Query);
            var token = query["token"];
            if (!string.IsNullOrEmpty(token))
            {
                TokenStore.Instance.SaveToken(token);
                ValidateAndNavigate().Forget();
            }
            else
            {
                Error = "Google Sign-In failed";
            }
        }

        // aidm://room/{room_id}
        if (url.StartsWith("aidm://room"))
        {
            var uri    = new Uri(url);
            var roomId = uri.AbsolutePath.TrimStart('/');
            if (!string.IsNullOrEmpty(roomId))
                SceneLoader.LoadGameRoom(roomId);
        }
    }

    private async UniTaskVoid ValidateAndNavigate()
    {
        var valid = await ValidateSession();
        if (valid)
            SceneLoader.LoadScene("MainMenu");
        else
            SceneLoader.LoadScene("Login");
    }
}
