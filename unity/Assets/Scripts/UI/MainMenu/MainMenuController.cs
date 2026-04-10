// Mahjong Soul-style main menu — no DOTween dependency.
// All animations use coroutines (character entrance, idle breath, parallax, button press).
using System.Collections;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using Cysharp.Threading.Tasks;

public class MainMenuController : MonoBehaviour
{
    [Header("Character")]
    [SerializeField] private RectTransform characterRoot;
    [SerializeField] private Image         characterImage;

    [Header("Top HUD")]
    [SerializeField] private TMP_Text playerNameLabel;
    [SerializeField] private TMP_Text coinBalanceLabel;
    [SerializeField] private Image    playerAvatarBg;
    [SerializeField] private TMP_Text playerInitialLabel;

    [Header("Game Buttons")]
    [SerializeField] private Button   turtleSoupButton;
    [SerializeField] private Button   murderMysteryButton;
    [SerializeField] private Button   friendsLobbyButton;

    [Header("Parallax")]
    [SerializeField] private RectTransform[] parallaxLayers;
    [SerializeField] private float[]         parallaxSpeeds;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    private void Start()
    {
        turtleSoupButton?.onClick.AddListener(OnTurtleSoup);
        murderMysteryButton?.onClick.AddListener(OnMurderMystery);
        friendsLobbyButton?.onClick.AddListener(OnFriendsLobby);

        StartCoroutine(CharacterEntrance());
        StartCoroutine(IdleBreath());
        StartCoroutine(ParallaxLoop());
        HookButtonPressAnimations();
        LoadPlayerHUD().Forget();
    }

    // ── Animations ────────────────────────────────────────────────────────────

    private IEnumerator CharacterEntrance()
    {
        if (characterRoot == null) yield break;

        // Start transparent and offset left
        var startPos = characterRoot.anchoredPosition;
        characterRoot.anchoredPosition = new Vector2(startPos.x - 120f, startPos.y);
        if (characterImage)
        {
            var c = characterImage.color; c.a = 0f; characterImage.color = c;
        }

        float t = 0f, dur = 0.7f;
        while (t < dur)
        {
            t += Time.deltaTime;
            float p = Mathf.SmoothStep(0f, 1f, t / dur);
            characterRoot.anchoredPosition = new Vector2(
                Mathf.Lerp(startPos.x - 120f, startPos.x, p), startPos.y);
            if (characterImage)
            {
                var c = characterImage.color; c.a = Mathf.Lerp(0f, 1f, p); characterImage.color = c;
            }
            yield return null;
        }
        characterRoot.anchoredPosition = startPos;
        if (characterImage)
        {
            var c = characterImage.color; c.a = 1f; characterImage.color = c;
        }
    }

    private IEnumerator IdleBreath()
    {
        if (characterRoot == null) yield break;
        while (characterRoot != null)
        {
            yield return ScaleTo(characterRoot, new Vector3(1f, 1.02f, 1f), 2f);
            yield return ScaleTo(characterRoot, Vector3.one, 2f);
        }
    }

    private IEnumerator ParallaxLoop()
    {
        if (parallaxLayers == null) yield break;
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

    private static IEnumerator ScaleTo(Transform t, Vector3 target, float dur)
    {
        if (t == null) yield break;
        var start = t.localScale;
        float elapsed = 0f;
        while (elapsed < dur)
        {
            elapsed += Time.deltaTime;
            t.localScale = Vector3.Lerp(start, target, Mathf.SmoothStep(0f, 1f, elapsed / dur));
            yield return null;
        }
        t.localScale = target;
    }

    private void HookButtonPressAnimations()
    {
        HookButton(turtleSoupButton,    this);
        HookButton(murderMysteryButton, this);
        HookButton(friendsLobbyButton,  this);
    }

    private static void HookButton(Button btn, MonoBehaviour host)
    {
        if (btn == null) return;
        var trigger = btn.gameObject.GetComponent<UnityEngine.EventSystems.EventTrigger>()
                      ?? btn.gameObject.AddComponent<UnityEngine.EventSystems.EventTrigger>();

        var down = new UnityEngine.EventSystems.EventTrigger.Entry
            { eventID = UnityEngine.EventSystems.EventTriggerType.PointerDown };
        down.callback.AddListener(_ =>
        {
            if (btn != null) host.StartCoroutine(ScaleTo(btn.transform, new Vector3(0.95f, 0.95f, 1f), 0.08f));
        });
        trigger.triggers.Add(down);

        var up = new UnityEngine.EventSystems.EventTrigger.Entry
            { eventID = UnityEngine.EventSystems.EventTriggerType.PointerUp };
        up.callback.AddListener(_ =>
        {
            if (btn != null) host.StartCoroutine(ScaleTo(btn.transform, Vector3.one, 0.12f));
        });
        trigger.triggers.Add(up);
    }

    // ── HUD ───────────────────────────────────────────────────────────────────

    private async UniTaskVoid LoadPlayerHUD()
    {
        try
        {
            var me = await APIManager.Instance.GetMe();
            if (playerNameLabel)    playerNameLabel.text    = me.Name ?? "Adventurer";
            if (playerInitialLabel) playerInitialLabel.text = string.IsNullOrEmpty(me.Name) ? "?" : me.Name[0].ToString().ToUpper();
            if (playerAvatarBg)     playerAvatarBg.color    = ColorPalette.AvatarColor(me.Name ?? "");
            if (coinBalanceLabel)   coinBalanceLabel.text   = "—";
        }
        catch { if (playerNameLabel) playerNameLabel.text = "Adventurer"; }
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    private void OnTurtleSoup()    => SceneLoader.LoadScene("RoomBrowser", ("tab", "turtle_soup"));
    private void OnMurderMystery() => SceneLoader.LoadScene("RoomBrowser", ("tab", "murder_mystery"));
    private void OnFriendsLobby()  => SceneLoader.LoadScene("RoomBrowser", ("tab", "active_rooms"));
}
