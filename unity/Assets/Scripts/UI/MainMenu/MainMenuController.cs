// Mahjong Soul-style main menu.
// Layer stack (back → front):
//   1. Sky gradient (set in Inspector)
//   2. Parallax mountains (ParallaxLayer[] — assigned in Inspector)
//   3. Cherry blossom particles (CherryBlossomSystem on same GameObject)
//   4. Anime character placeholder (characterRoot RectTransform)
//   5. Top HUD bar
//   6. Three game-mode button panels
//   7. BottomNavBar (always visible on MainMenu)
using DG.Tweening;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using Cysharp.Threading.Tasks;

public class MainMenuController : MonoBehaviour
{
    // ── Character ────────────────────────────────────────────────────────────
    [Header("Character")]
    [SerializeField] private RectTransform characterRoot;   // left 40 % panel
    [SerializeField] private Image         characterImage;  // swap art here

    // ── Top HUD ──────────────────────────────────────────────────────────────
    [Header("Top HUD")]
    [SerializeField] private TMP_Text playerNameLabel;
    [SerializeField] private TMP_Text coinBalanceLabel;
    [SerializeField] private Image    playerAvatarBg;
    [SerializeField] private TMP_Text playerInitialLabel;

    // ── Game-mode buttons ─────────────────────────────────────────────────────
    [Header("Game Buttons")]
    [SerializeField] private Button   turtleSoupButton;
    [SerializeField] private Button   murderMysteryButton;
    [SerializeField] private Button   friendsLobbyButton;

    // ── Parallax ─────────────────────────────────────────────────────────────
    [Header("Parallax")]
    [SerializeField] private RectTransform[] parallaxLayers; // back → front
    [SerializeField] private float[]         parallaxSpeeds; // pixels per cycle

    // ── State ─────────────────────────────────────────────────────────────────
    private Sequence _idleBreath;
    private Sequence _parallaxLoop;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    private void Start()
    {
        turtleSoupButton?.onClick.AddListener(OnTurtleSoup);
        murderMysteryButton?.onClick.AddListener(OnMurderMystery);
        friendsLobbyButton?.onClick.AddListener(OnFriendsLobby);

        PlayCharacterEntrance();
        PlayIdleBreath();
        PlayParallaxLoop();
        LoadPlayerHUD().Forget();
        HookButtonPressAnimations();
    }

    private void OnDestroy()
    {
        _idleBreath?.Kill();
        _parallaxLoop?.Kill();
    }

    // ── Animations ────────────────────────────────────────────────────────────

    /// Slide character in from the left + fade up.
    private void PlayCharacterEntrance()
    {
        if (characterRoot == null) return;

        var startX = characterRoot.anchoredPosition.x - 120f;
        characterRoot.anchoredPosition = new Vector2(startX, characterRoot.anchoredPosition.y);

        if (characterImage) characterImage.color = new Color(1, 1, 1, 0);

        var seq = DOTween.Sequence();
        seq.Append(characterRoot.DOAnchorPosX(characterRoot.anchoredPosition.x + 120f, 0.7f)
                                .SetEase(Ease.OutCubic));
        seq.Join(characterImage != null
            ? characterImage.DOFade(1f, 0.5f)
            : null);
    }

    /// Subtle breathing: scale Y 1.0 → 1.02, loop.
    private void PlayIdleBreath()
    {
        if (characterRoot == null) return;

        _idleBreath = DOTween.Sequence();
        _idleBreath.Append(characterRoot.DOScaleY(1.02f, 2f).SetEase(Ease.InOutSine));
        _idleBreath.Append(characterRoot.DOScaleY(1.00f, 2f).SetEase(Ease.InOutSine));
        _idleBreath.SetLoops(-1, LoopType.Restart);
    }

    /// Slow horizontal drift for each mountain layer at different speeds.
    private void PlayParallaxLoop()
    {
        if (parallaxLayers == null || parallaxLayers.Length == 0) return;

        _parallaxLoop = DOTween.Sequence();

        for (int i = 0; i < parallaxLayers.Length; i++)
        {
            var layer = parallaxLayers[i];
            if (layer == null) continue;
            float speed = (parallaxSpeeds != null && i < parallaxSpeeds.Length) ? parallaxSpeeds[i] : 20f;
            float duration = 30f / Mathf.Max(speed, 1f);

            // Each layer drifts left then snaps back — seamless if texture is 2× screen width
            _parallaxLoop.Insert(0,
                layer.DOAnchorPosX(layer.anchoredPosition.x - speed * 30f, duration)
                     .SetEase(Ease.Linear)
                     .SetLoops(-1, LoopType.Restart));
        }
    }

    /// Scale 1.0 → 0.97 on press, back on release + gold glow.
    private void HookButtonPressAnimations()
    {
        HookButton(turtleSoupButton);
        HookButton(murderMysteryButton);
        HookButton(friendsLobbyButton);
    }

    private static void HookButton(Button btn)
    {
        if (btn == null) return;

        var trigger = btn.gameObject.GetComponent<UnityEngine.EventSystems.EventTrigger>()
                      ?? btn.gameObject.AddComponent<UnityEngine.EventSystems.EventTrigger>();

        var down = new UnityEngine.EventSystems.EventTrigger.Entry
            { eventID = UnityEngine.EventSystems.EventTriggerType.PointerDown };
        down.callback.AddListener(_ => btn.transform.DOScale(0.97f, 0.08f).SetEase(Ease.OutQuad));
        trigger.triggers.Add(down);

        var up = new UnityEngine.EventSystems.EventTrigger.Entry
            { eventID = UnityEngine.EventSystems.EventTriggerType.PointerUp };
        up.callback.AddListener(_ => btn.transform.DOScale(1f, 0.12f).SetEase(Ease.OutBack));
        trigger.triggers.Add(up);
    }

    // ── HUD data ──────────────────────────────────────────────────────────────

    private async UniTaskVoid LoadPlayerHUD()
    {
        try
        {
            var me = await APIManager.Instance.GetMe();
            if (playerNameLabel)    playerNameLabel.text    = me.Username ?? me.DisplayName ?? "Adventurer";
            if (playerInitialLabel) playerInitialLabel.text = GetInitial(me.Username ?? me.DisplayName);
            if (playerAvatarBg)     playerAvatarBg.color    = ColorPalette.AvatarColor(me.Username ?? "");
            // Coin balance omitted until Economy API is plumbed into Unity; stub:
            if (coinBalanceLabel) coinBalanceLabel.text = "—";
        }
        catch
        {
            if (playerNameLabel) playerNameLabel.text = "Adventurer";
        }
    }

    private static string GetInitial(string name)
        => string.IsNullOrEmpty(name) ? "?" : name[0].ToString().ToUpper();

    // ── Navigation ────────────────────────────────────────────────────────────

    private void OnTurtleSoup()
        => SceneLoader.LoadScene("RoomBrowser", ("tab", "turtle_soup"));

    private void OnMurderMystery()
        => SceneLoader.LoadScene("RoomBrowser", ("tab", "murder_mystery"));

    private void OnFriendsLobby()
        => SceneLoader.LoadScene("RoomBrowser", ("tab", "active_rooms"));
}
