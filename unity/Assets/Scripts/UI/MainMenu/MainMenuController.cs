// Mystery Shrine main menu — Mahjong Soul-inspired home screen.
// Character entrance, idle breath, parallax bg, game mode banners, pet companion.
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

    [Header("Pet Companion")]
    [SerializeField] private RectTransform petRoot;
    [SerializeField] private Image         petImage;

    [Header("Skill Bubbles")]
    [SerializeField] private RectTransform skillBubble1;
    [SerializeField] private RectTransform skillBubble2;

    [Header("Top HUD (legacy — now handled by TopHUD component)")]
    [SerializeField] private TMP_Text playerNameLabel;
    [SerializeField] private TMP_Text coinBalanceLabel;
    [SerializeField] private Image    playerAvatarBg;
    [SerializeField] private TMP_Text playerInitialLabel;

    [Header("Game Mode Banners")]
    [SerializeField] private Button turtleSoupButton;
    [SerializeField] private Button murderMysteryButton;
    [SerializeField] private Button friendsLobbyButton;
    [SerializeField] private Image  turtleSoupBannerBg;
    [SerializeField] private Image  murderMysteryBannerBg;

    [Header("Parallax")]
    [SerializeField] private RectTransform[] parallaxLayers;
    [SerializeField] private float[]         parallaxSpeeds;

    [Header("Announcement")]
    [SerializeField] private TMP_Text announcementMarquee;
    [SerializeField] private RectTransform marqueeRect;
    [SerializeField] private float marqueeSpeed = 60f;

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    private void Start()
    {
        turtleSoupButton?.onClick.AddListener(OnTurtleSoup);
        murderMysteryButton?.onClick.AddListener(OnMurderMystery);
        friendsLobbyButton?.onClick.AddListener(OnFriendsLobby);

        StartCoroutine(CharacterEntrance());
        StartCoroutine(IdleBreath());
        StartCoroutine(ParallaxLoop());
        StartCoroutine(PetFloat());
        StartCoroutine(SkillBubbleFloat());
        if (marqueeRect != null) StartCoroutine(MarqueeScroll());
        HookButtonPressAnimations();
        LoadPlayerHUD().Forget();
    }

    // ── Animations ────────────────────────────────────────────────────────────

    private IEnumerator CharacterEntrance()
    {
        if (characterRoot == null) yield break;

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

    private IEnumerator PetFloat()
    {
        if (petRoot == null) yield break;
        var origin = petRoot.anchoredPosition;
        float time = 0f;
        while (petRoot != null)
        {
            time += Time.deltaTime;
            float y = origin.y + Mathf.Sin(time * 1.5f) * 8f;
            float x = origin.x + Mathf.Sin(time * 0.7f) * 4f;
            petRoot.anchoredPosition = new Vector2(x, y);
            yield return null;
        }
    }

    private IEnumerator SkillBubbleFloat()
    {
        if (skillBubble1 == null && skillBubble2 == null) yield break;

        Vector2 origin1 = skillBubble1 != null ? skillBubble1.anchoredPosition : Vector2.zero;
        Vector2 origin2 = skillBubble2 != null ? skillBubble2.anchoredPosition : Vector2.zero;
        float time = 0f;

        while (true)
        {
            time += Time.deltaTime;
            if (skillBubble1 != null)
            {
                float y = origin1.y + Mathf.Sin(time * 1.2f) * 6f;
                skillBubble1.anchoredPosition = new Vector2(origin1.x, y);
            }
            if (skillBubble2 != null)
            {
                float y = origin2.y + Mathf.Sin(time * 1.2f + Mathf.PI) * 6f;
                skillBubble2.anchoredPosition = new Vector2(origin2.x, y);
            }
            yield return null;
        }
    }

    private IEnumerator MarqueeScroll()
    {
        if (marqueeRect == null || announcementMarquee == null) yield break;

        var parent = marqueeRect.parent as RectTransform;
        float parentW = parent != null ? parent.rect.width : 600f;
        float textW = announcementMarquee.preferredWidth;

        marqueeRect.anchoredPosition = new Vector2(parentW, marqueeRect.anchoredPosition.y);

        while (true)
        {
            var pos = marqueeRect.anchoredPosition;
            pos.x -= marqueeSpeed * Time.deltaTime;
            if (pos.x < -(textW + 50f))
                pos.x = parentW;
            marqueeRect.anchoredPosition = pos;
            yield return null;
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
