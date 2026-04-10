// Mirrors ios/AIDungeonMaster/Auth/LoginView.swift + AuthViewModel login actions.
// Attach to a Canvas with: GoogleSignInButton, GuestButton, ErrorText (TMP).
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using Cysharp.Threading.Tasks;

public class LoginController : MonoBehaviour
{
    [Header("UI References")]
    [SerializeField] private Button    googleSignInButton;
    [SerializeField] private Button    guestButton;
    [SerializeField] private TMP_Text  errorText;
    [SerializeField] private GameObject loadingOverlay;

    private void Start()
    {
        if (errorText)     errorText.text    = "";
        if (loadingOverlay) loadingOverlay.SetActive(false);

        googleSignInButton?.onClick.AddListener(OnGoogleSignIn);
        guestButton?.onClick.AddListener(OnGuestLogin);

        AuthManager.Instance.OnUserChanged += OnUserChanged;
    }

    private void OnDestroy()
    {
        if (AuthManager.Instance)
            AuthManager.Instance.OnUserChanged -= OnUserChanged;
    }

    // ── Handlers ─────────────────────────────────────────────────────────────

    private void OnGoogleSignIn()
    {
        ClearError();
        AuthManager.Instance.GoogleSignIn();
        // Navigation happens in AuthManager.OnDeepLink after OAuth callback
    }

    private void OnGuestLogin()
    {
        ClearError();
        var token = TokenStore.Instance.StableGuestToken();
        // Guest: no server call needed — token is stored as "guest:<id>"
        // The backend accepts this as an anonymous user
        TokenStore.Instance.SaveToken(token);
        SetLoading(true);
        GuestValidate().Forget();
    }

    private async UniTaskVoid GuestValidate()
    {
        await UniTask.Delay(300); // brief visual feedback
        SetLoading(false);
        SceneLoader.LoadScene("MainMenu");
    }

    private void OnUserChanged()
    {
        if (AuthManager.Instance.CurrentUser != null)
            SceneLoader.LoadScene("MainMenu");
        else if (!string.IsNullOrEmpty(AuthManager.Instance.Error))
            ShowError(AuthManager.Instance.Error);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void ShowError(string msg)
    {
        if (errorText) { errorText.text = msg; errorText.gameObject.SetActive(true); }
        SetLoading(false);
    }

    private void ClearError()
    {
        if (errorText) errorText.text = "";
    }

    private void SetLoading(bool on)
    {
        loadingOverlay?.SetActive(on);
        googleSignInButton?.gameObject.SetActive(!on);
        guestButton?.gameObject.SetActive(!on);
    }
}
