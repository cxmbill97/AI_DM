// Mahjong Soul-style main menu.
// Layer stack (back → front):
//   1. Sky gradient (set in Inspector)
//   2. Parallax mountains (ParallaxLayer[] — assigned in Inspector)
//   3. Cherry blossom particles (CherryBlossomSystem on same GameObject)
//   4. Anime character placeholder (characterRoot RectTransform)
//   5. Top HUD bar
//   6. Three game-mode button panels
//   7. BottomNavBar (always visible on MainMenu)
//
// DOTween animations are guarded with #if DOTWEEN — the script compiles and runs
// without DOTween installed (no animations); import DOTween from the Asset Store
// to unlock all animations.
#if DOTWEEN
using DG.Tweening;
#endif
using System.Collections;
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

#if DOTWEEN
    private DG.Tweening.Sequence _idleBreath;
    private DG.Tweening.Sequence _parallaxLoop;
#endif

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
#if DOTWEEN
        _idleBreath?.Kill();
        _parallaxLoop?.Kill();
#endif
    }

    // ── Animations ────────────────────────────────────────────────────────────

    private void PlayCharacterEntrance()
    {
        if (characterRoot == null) return;
#if DOTWEEN
        var startX = characterRoot.anchoredPosition.x - 120f;
        characterRoot.anchoredPosition = new Vector2(startX, characterRoot.anchoredPosition.y);
        if (characterImage) characterImage.color = new Color(1, 1, 1, 0);

        var seq = DG.Tweening.DOTween.Sequence();
        seq.Append(characterRoot.DOAnchorPosX(characterRoot.anchoredPosition.x + 120f, 0.7f)
                                .SetEase(DG.Tweening.Ease.OutCubic));
        if (characterImage != null)
            seq.Join(characterImage.DOFade(1f, 0.5f));
#else
        // Fallback: keep existing color, just ensure alpha is fully visible
        if (characterImage)
        {
            var c = characterImage.color;
            c.a = 1f;
            characterImage.color = c;
        }
#endif
    }

    private void PlayIdleBreath()
    {
        if (characterRoot == null) return;
#if DOTWEEN
        _idleBreath = DG.Tweening.DOTween.Sequence();
        _idleBreath.Append(characterRoot.DOScaleY(1.02f, 2f).SetEase(DG.Tweening.Ease.InOutSine));
        _idleBreath.Append(characterRoot.DOScaleY(1.00f, 2f).SetEase(DG.Tweening.Ease.InOutSine));
        _idleBreath.SetLoops(-1, DG.Tweening.LoopType.Restart);
#else
        StartCoroutine(BreathCoroutine());
#endif
    }

#if !DOTWEEN
    private IEnumerator BreathCoroutine()
    {
        while (characterRoot != null)
        {
            float t = 0f;
            while (t < 2f) { t += Time.deltaTime; characterRoot.localScale = new Vector3(1f, Mathf.Lerp(1f, 1.02f, t / 2f), 1f); yield return null; }
            t = 0f;
            while (t < 2f) { t += Time.deltaTime; characterRoot.localScale = new Vector3(1f, Mathf.Lerp(1.02f, 1f, t / 2f), 1f); yield return null; }
        }
    }
#endif

    private void PlayParallaxLoop()
    {
        if (parallaxLayers == null || parallaxLayers.Length == 0) return;
#if DOTWEEN
        _parallaxLoop = DG.Tweening.DOTween.Sequence();
        for (int i = 0; i < parallaxLayers.Length; i++)
        {
            var layer = parallaxLayers[i];
            if (layer == null) continue;
            float speed    = (parallaxSpeeds != null && i < parallaxSpeeds.Length) ? parallaxSpeeds[i] : 20f;
            float duration = 30f / Mathf.Max(speed, 1f);
            _parallaxLoop.Insert(0,
                layer.DOAnchorPosX(layer.anchoredPosition.x - speed * 30f, duration)
                     .SetEase(DG.Tweening.Ease.Linear)
                     .SetLoops(-1, DG.Tweening.LoopType.Restart));
        }
#else
        StartCoroutine(ParallaxCoroutine());
#endif
    }

#if !DOTWEEN
    private IEnumerator ParallaxCoroutine()
    {
        var origins = new Vector2[parallaxLayers.Length];
        for (int i = 0; i < parallaxLayers.Length; i++)
            if (parallaxLayers[i] != null) origins[i] = parallaxLayers[i].anchoredPosition;

        while (true)
        {
            for (int i = 0; i < parallaxLayers.Length; i++)
            {
                if (parallaxLayers[i] == null) continue;
                float speed = (parallaxSpeeds != null && i < parallaxSpeeds.Length) ? parallaxSpeeds[i] : 20f;
                var pos = parallaxLayers[i].anchoredPosition;
                pos.x -= speed * Time.deltaTime;
                if (pos.x < origins[i].x - 1920f) pos.x = origins[i].x;
                parallaxLayers[i].anchoredPosition = pos;
            }
            yield return null;
        }
    }
#endif

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
#if DOTWEEN
        down.callback.AddListener(_ => btn.transform.DOScale(0.97f, 0.08f).SetEase(DG.Tweening.Ease.OutQuad));
#else
        down.callback.AddListener(_ => btn.transform.localScale = new Vector3(0.97f, 0.97f, 1f));
#endif
        trigger.triggers.Add(down);

        var up = new UnityEngine.EventSystems.EventTrigger.Entry
            { eventID = UnityEngine.EventSystems.EventTriggerType.PointerUp };
#if DOTWEEN
        up.callback.AddListener(_ => btn.transform.DOScale(1f, 0.12f).SetEase(DG.Tweening.Ease.OutBack));
#else
        up.callback.AddListener(_ => btn.transform.localScale = Vector3.one);
#endif
        trigger.triggers.Add(up);
    }

    // ── HUD data ──────────────────────────────────────────────────────────────

    private async UniTaskVoid LoadPlayerHUD()
    {
        try
        {
            var me = await APIManager.Instance.GetMe();
            if (playerNameLabel)    playerNameLabel.text    = me.Name ?? "Adventurer";
            if (playerInitialLabel) playerInitialLabel.text = GetInitial(me.Name);
            if (playerAvatarBg)     playerAvatarBg.color    = ColorPalette.AvatarColor(me.Name ?? "");
            if (coinBalanceLabel)   coinBalanceLabel.text   = "—";
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
