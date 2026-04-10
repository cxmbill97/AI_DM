// AI DM → Setup Scenes
// Run from the menu bar: AI DM → Setup All Scenes
// Builds GameObjects, Canvas hierarchy, UI elements, and wires all Inspector
// references for every scene so you can hit Play immediately.
#if UNITY_EDITOR
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using UnityEngine.EventSystems;

public static class SceneSetupWizard
{
    // ── Colors ────────────────────────────────────────────────────────────────
    static readonly Color BgDark      = new(0.05f, 0.03f, 0.09f);   // #0d0820
    static readonly Color Accent      = new(0.78f, 0.66f, 0.30f);   // #c9a84c gold
    static readonly Color PanelDark   = new(0.08f, 0.07f, 0.14f, 0.92f);
    static readonly Color TextLight   = new(0.93f, 0.90f, 0.85f);
    static readonly Color ButtonNorm  = new(0.14f, 0.11f, 0.22f);

    // ── Entry point ───────────────────────────────────────────────────────────

    [MenuItem("AI DM/Setup All Scenes")]
    public static void SetupAll()
    {
        EnsureScenesFolder();
        SetupBoot();
        SetupLogin();
        SetupMainMenu();
        SetupRoomBrowser();
        SetupWaitingRoom();
        SetupGameRoom();
        EditorUtility.DisplayDialog("AI DM Setup", "All 6 scenes built successfully!\n\nPress Play from the Boot scene to test the full flow.", "OK");
    }

    [MenuItem("AI DM/Setup Boot Scene")]   public static void SetupBoot()       => BuildBoot();
    [MenuItem("AI DM/Setup Login Scene")]  public static void SetupLogin()      => BuildLogin();
    [MenuItem("AI DM/Setup MainMenu")]     public static void SetupMainMenu()   => BuildMainMenu();
    [MenuItem("AI DM/Setup RoomBrowser")] public static void SetupRoomBrowser()=> BuildRoomBrowser();
    [MenuItem("AI DM/Setup WaitingRoom")] public static void SetupWaitingRoom()=> BuildWaitingRoom();
    [MenuItem("AI DM/Setup GameRoom")]    public static void SetupGameRoom()   => BuildGameRoom();

    // ═════════════════════════════════════════════════════════════════════════
    // BOOT
    // ═════════════════════════════════════════════════════════════════════════

    static void BuildBoot()
    {
        var scene = OpenScene("Boot");
        ClearScene();

        // Services (singletons — DontDestroyOnLoad)
        var svc = NewGO("Services");
        svc.AddComponent<SceneLoader>();
        svc.AddComponent<TokenStore>();
        svc.AddComponent<APIManager>();
        svc.AddComponent<WebSocketManager>();
        svc.AddComponent<AuthManager>();

        // Minimal canvas just to hold BootController
        var canvas = MakeCanvas("Canvas");
        var content = NewChild("BootContent", canvas.gameObject);
        Stretch(content.GetComponent<RectTransform>());
        content.AddComponent<BootController>();

        // Dark background so it's not just a void
        var bg = content.AddComponent<Image>();
        bg.color = BgDark;

        SaveScene(scene, "Boot");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // LOGIN
    // ═════════════════════════════════════════════════════════════════════════

    static void BuildLogin()
    {
        var scene = OpenScene("Login");
        ClearScene();

        var canvas  = MakeCanvas("Canvas");
        var content = NewChild("ContentArea", canvas.gameObject);
        Stretch(content.GetComponent<RectTransform>());

        // Background
        var bg = content.AddComponent<Image>();
        bg.color = BgDark;

        // Title
        var title = MakeTMP("TitleLabel", content, "AI Dungeon Master",
            fontSize: 52, bold: true, color: Accent);
        RectAt(title, 0.5f, 0.72f, 600, 70);

        var sub = MakeTMP("SubLabel", content, "Your AI Game Master awaits",
            fontSize: 22, color: TextLight);
        RectAt(sub, 0.5f, 0.63f, 500, 35);

        // Google button
        var googleBtn = MakeButton("GoogleSignInButton", content,
            "Sign in with Google", ButtonNorm, Accent, 22);
        RectAt(googleBtn, 0.5f, 0.48f, 340, 62);

        // Guest button
        var guestBtn = MakeButton("GuestButton", content,
            "Play as Guest", new Color(0.18f, 0.15f, 0.28f), TextLight, 22);
        RectAt(guestBtn, 0.5f, 0.38f, 340, 62);

        // Error text
        var err = MakeTMP("ErrorText", content, "", fontSize: 18,
            color: new Color(1f, 0.35f, 0.35f));
        RectAt(err, 0.5f, 0.28f, 500, 30);
        err.GetComponent<TMP_Text>().alignment = TextAlignmentOptions.Center;
        err.SetActive(false);

        // Loading overlay
        var overlay = NewChild("LoadingOverlay", content);
        Stretch(overlay.GetComponent<RectTransform>());
        var overlayImg = overlay.AddComponent<Image>();
        overlayImg.color = new Color(0, 0, 0, 0.6f);
        var loadingLbl = MakeTMP("LoadingLabel", overlay, "Loading…",
            fontSize: 30, color: Color.white);
        RectAt(loadingLbl, 0.5f, 0.5f, 300, 50);
        overlay.SetActive(false);

        // Wire LoginController
        var ctrl = content.AddComponent<LoginController>();
        SetField(ctrl, "googleSignInButton", googleBtn.GetComponent<Button>());
        SetField(ctrl, "guestButton",         guestBtn.GetComponent<Button>());
        SetField(ctrl, "errorText",           err.GetComponent<TMP_Text>());
        SetField(ctrl, "loadingOverlay",      overlay);

        SaveScene(scene, "Login");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // MAIN MENU
    // ═════════════════════════════════════════════════════════════════════════

    static void BuildMainMenu()
    {
        var scene = OpenScene("MainMenu");
        ClearScene();

        var canvas  = MakeCanvas("Canvas");
        var safe    = NewChild("SafeAreaPanel", canvas.gameObject);
        Stretch(safe.GetComponent<RectTransform>());

        // Sky background
        var bgImg = safe.AddComponent<Image>();
        bgImg.color = BgDark;

        // Cherry blossom layer (behind everything)
        var blossomGO = NewChild("CherryBlossom", safe);
        blossomGO.transform.SetSiblingIndex(0);
        blossomGO.AddComponent<CherryBlossomSystem>();

        // Content area
        var content = NewChild("ContentArea", safe);
        Stretch(content.GetComponent<RectTransform>());

        // Character placeholder (left 40%)
        var charRoot = NewChild("CharacterRoot", content);
        var charRT   = charRoot.GetComponent<RectTransform>();
        charRT.anchorMin = new Vector2(0, 0);
        charRT.anchorMax = new Vector2(0.42f, 1f);
        charRT.offsetMin = charRT.offsetMax = Vector2.zero;
        var charImg  = charRoot.AddComponent<Image>();
        charImg.color = new Color(0.18f, 0.10f, 0.30f, 0.85f);  // placeholder silhouette

        // Top HUD bar
        var hud = NewChild("TopHUD", content);
        var hudRT = hud.GetComponent<RectTransform>();
        hudRT.anchorMin = new Vector2(0, 1); hudRT.anchorMax = new Vector2(1, 1);
        hudRT.pivot = new Vector2(0.5f, 1f);
        hudRT.sizeDelta = new Vector2(0, 70);
        hudRT.anchoredPosition = Vector2.zero;
        var hudBg = hud.AddComponent<Image>();
        hudBg.color = new Color(0.05f, 0.05f, 0.09f, 0.88f);

        var logoLbl  = MakeTMP("LogoLabel",       hud, "AI DM", 28, bold: true, color: Accent);
        RectAt(logoLbl, 0.12f, 0.5f, 120, 45);

        var playerLbl = MakeTMP("PlayerNameLabel", hud, "Adventurer", 20, color: TextLight);
        RectAt(playerLbl, 0.72f, 0.5f, 200, 35);

        var coinLbl  = MakeTMP("CoinLabel",        hud, "—",  20, color: Accent);
        RectAt(coinLbl, 0.88f, 0.5f, 100, 35);

        // Avatar bg circle
        var avatarGO  = NewChild("AvatarBg", hud);
        var avatarRT  = avatarGO.GetComponent<RectTransform>();
        avatarRT.anchorMin = avatarRT.anchorMax = new Vector2(0.62f, 0.5f);
        avatarRT.pivot = new Vector2(0.5f, 0.5f);
        avatarRT.sizeDelta = new Vector2(44, 44);
        avatarRT.anchoredPosition = Vector2.zero;
        var avatarImg  = avatarGO.AddComponent<Image>();
        avatarImg.color = Accent;

        var initLbl = MakeTMP("PlayerInitialLabel", avatarGO, "?", 20,
            bold: true, color: BgDark);
        Stretch(initLbl.GetComponent<RectTransform>());

        // Right panel — three game mode buttons
        var btnPanel = NewChild("ButtonPanel", content);
        var btnPanelRT = btnPanel.GetComponent<RectTransform>();
        btnPanelRT.anchorMin = new Vector2(0.52f, 0.3f);
        btnPanelRT.anchorMax = new Vector2(0.96f, 0.85f);
        btnPanelRT.offsetMin = btnPanelRT.offsetMax = Vector2.zero;

        var tsBtn  = MakeButton("TurtleSoupButton",    btnPanel, "🐢  Turtle Soup  海龟汤",
                                ButtonNorm, TextLight, 22);
        var mmBtn  = MakeButton("MurderMysteryButton", btnPanel, "🔍  Murder Mystery  剧本杀",
                                ButtonNorm, TextLight, 22);
        var flBtn  = MakeButton("FriendsLobbyButton",  btnPanel, "🚪  Friends / Lobby",
                                ButtonNorm, TextLight, 22);

        // Stack the three buttons vertically
        LayoutButton(tsBtn,  btnPanelRT, 0.83f);
        LayoutButton(mmBtn,  btnPanelRT, 0.50f);
        LayoutButton(flBtn,  btnPanelRT, 0.17f);

        // MainMenuController
        var ctrl = content.AddComponent<MainMenuController>();
        SetField(ctrl, "characterRoot",       charRT);
        SetField(ctrl, "characterImage",      charImg);
        SetField(ctrl, "playerNameLabel",     playerLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "coinBalanceLabel",    coinLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "playerAvatarBg",      avatarImg);
        SetField(ctrl, "playerInitialLabel",  initLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "turtleSoupButton",    tsBtn.GetComponent<Button>());
        SetField(ctrl, "murderMysteryButton", mmBtn.GetComponent<Button>());
        SetField(ctrl, "friendsLobbyButton",  flBtn.GetComponent<Button>());

        SaveScene(scene, "MainMenu");
    }

    static void LayoutButton(GameObject btn, RectTransform parent, float anchorY)
    {
        var rt = btn.GetComponent<RectTransform>();
        rt.anchorMin = new Vector2(0f, anchorY - 0.14f);
        rt.anchorMax = new Vector2(1f, anchorY + 0.14f);
        rt.offsetMin = rt.offsetMax = Vector2.zero;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // ROOM BROWSER
    // ═════════════════════════════════════════════════════════════════════════

    static void BuildRoomBrowser()
    {
        var scene = OpenScene("RoomBrowser");
        ClearScene();

        var canvas  = MakeCanvas("Canvas");
        var content = NewChild("ContentArea", canvas.gameObject);
        Stretch(content.GetComponent<RectTransform>());
        content.AddComponent<Image>().color = BgDark;

        // Header
        var header = MakeTMP("Header", content, "Choose a Game", 32, bold: true, color: Accent);
        RectAt(header, 0.5f, 0.92f, 500, 50);

        // Tab buttons
        var tabAR = MakeButton("TabActiveRooms",    content, "Active Rooms", ButtonNorm, TextLight, 18);
        var tabTS = MakeButton("TabTurtleSoup",      content, "Turtle Soup",  ButtonNorm, TextLight, 18);
        var tabMM = MakeButton("TabMurderMystery",   content, "Murder Mystery", ButtonNorm, TextLight, 18);
        RectAt(tabAR, 0.18f, 0.82f, 220, 44);
        RectAt(tabTS, 0.50f, 0.82f, 220, 44);
        RectAt(tabMM, 0.82f, 0.82f, 220, 44);

        // Join by code row
        var joinInput = MakeInputField("JoinCodeInput", content, "Room code…");
        RectAt(joinInput, 0.38f, 0.72f, 280, 48);
        var joinBtn = MakeButton("JoinButton", content, "Join", ButtonNorm, Accent, 20);
        RectAt(joinBtn, 0.72f, 0.72f, 120, 48);

        // Scroll view for cards
        var scroll = MakeScrollView("CardScroll", content);
        var scrollRT = scroll.GetComponent<RectTransform>();
        scrollRT.anchorMin = new Vector2(0.04f, 0.06f);
        scrollRT.anchorMax = new Vector2(0.96f, 0.66f);
        scrollRT.offsetMin = scrollRT.offsetMax = Vector2.zero;
        var cardContainer = scroll.transform.Find("Viewport/Content");

        // Loading overlay
        var loading = NewChild("LoadingOverlay", content);
        Stretch(loading.GetComponent<RectTransform>());
        loading.AddComponent<Image>().color = new Color(0,0,0,0.5f);
        MakeTMP("LoadingLabel", loading, "Loading…", 28, color: Color.white);
        loading.SetActive(false);

        // Error text
        var err = MakeTMP("ErrorText", content, "", 18, color: new Color(1f,0.3f,0.3f));
        RectAt(err, 0.5f, 0.03f, 600, 30);
        err.SetActive(false);

        var ctrl = content.AddComponent<RoomBrowserController>();
        SetField(ctrl, "tabActiveRooms",   tabAR.GetComponent<Button>());
        SetField(ctrl, "tabTurtleSoup",    tabTS.GetComponent<Button>());
        SetField(ctrl, "tabMurderMystery", tabMM.GetComponent<Button>());
        SetField(ctrl, "joinCodeInput",    joinInput.GetComponent<TMP_InputField>());
        SetField(ctrl, "joinButton",       joinBtn.GetComponent<Button>());
        SetField(ctrl, "cardContainer",    (Transform)cardContainer);
        SetField(ctrl, "scrollRect",       scroll.GetComponent<ScrollRect>());
        SetField(ctrl, "loadingOverlay",   loading);
        SetField(ctrl, "errorText",        err.GetComponent<TMP_Text>());

        SaveScene(scene, "RoomBrowser");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // WAITING ROOM
    // ═════════════════════════════════════════════════════════════════════════

    static void BuildWaitingRoom()
    {
        var scene = OpenScene("WaitingRoom");
        ClearScene();

        var canvas  = MakeCanvas("Canvas");
        var content = NewChild("ContentArea", canvas.gameObject);
        Stretch(content.GetComponent<RectTransform>());
        content.AddComponent<Image>().color = BgDark;

        var roomCodeLbl = MakeTMP("RoomCodeLabel", content, "ROOM", 40, bold: true, color: Accent);
        RectAt(roomCodeLbl, 0.5f, 0.88f, 300, 55);

        var subLbl = MakeTMP("SubLabel", content, "Share this code with friends", 18, color: TextLight);
        RectAt(subLbl, 0.5f, 0.81f, 400, 30);

        // Player slots container
        var slots = NewChild("SlotsContainer", content);
        var slotsRT = slots.GetComponent<RectTransform>();
        slotsRT.anchorMin = new Vector2(0.1f, 0.35f);
        slotsRT.anchorMax = new Vector2(0.9f, 0.75f);
        slotsRT.offsetMin = slotsRT.offsetMax = Vector2.zero;
        var slotLayout = slots.AddComponent<VerticalLayoutGroup>();
        slotLayout.spacing = 12;
        slotLayout.childControlHeight = true;
        slotLayout.childControlWidth  = true;

        // Buttons
        var startBtn  = MakeButton("StartButton",  content, "Start Game",    Accent,      BgDark,    24);
        var readyBtn  = MakeButton("ReadyButton",  content, "I'm Ready",     ButtonNorm,  TextLight, 22);
        var backBtn   = MakeButton("BackButton",   content, "← Back",        ButtonNorm,  TextLight, 20);
        var publicBtn = MakeButton("PublicToggle", content, "🔒 Private Room",ButtonNorm,  TextLight, 18);
        RectAt(startBtn,  0.5f, 0.20f, 300, 58);
        RectAt(readyBtn,  0.5f, 0.20f, 300, 58);
        RectAt(backBtn,   0.12f, 0.94f, 120, 44);
        RectAt(publicBtn, 0.78f, 0.94f, 200, 44);

        var readyLbl = readyBtn.GetComponentInChildren<TMP_Text>();

        var err = MakeTMP("ErrorText", content, "", 18, color: new Color(1f,0.3f,0.3f));
        RectAt(err, 0.5f, 0.10f, 600, 30);
        err.SetActive(false);

        var ctrl = content.AddComponent<WaitingRoomController>();
        SetField(ctrl, "roomCodeLabel",     roomCodeLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "slotsContainer",    slots.transform);
        SetField(ctrl, "startButton",       startBtn.GetComponent<Button>());
        SetField(ctrl, "readyButton",       readyBtn.GetComponent<Button>());
        SetField(ctrl, "readyButtonLabel",  readyLbl);
        SetField(ctrl, "backButton",        backBtn.GetComponent<Button>());
        SetField(ctrl, "publicToggle",      publicBtn.GetComponent<Button>());
        SetField(ctrl, "publicToggleLabel", publicBtn.GetComponentInChildren<TMP_Text>());
        SetField(ctrl, "errorText",         err.GetComponent<TMP_Text>());

        SaveScene(scene, "WaitingRoom");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // GAME ROOM
    // ═════════════════════════════════════════════════════════════════════════

    static void BuildGameRoom()
    {
        var scene = OpenScene("GameRoom");
        ClearScene();

        var canvas  = MakeCanvas("Canvas");
        var content = NewChild("ContentArea", canvas.gameObject);
        Stretch(content.GetComponent<RectTransform>());
        content.AddComponent<Image>().color = BgDark;

        // Top nav bar
        var nav    = NewChild("NavBar", content);
        var navRT  = nav.GetComponent<RectTransform>();
        navRT.anchorMin = new Vector2(0, 1); navRT.anchorMax = new Vector2(1, 1);
        navRT.pivot = new Vector2(0.5f, 1f);
        navRT.sizeDelta = new Vector2(0, 60);
        navRT.anchoredPosition = Vector2.zero;
        nav.AddComponent<Image>().color = PanelDark;

        var backBtn  = MakeButton("BackButton",  nav, "←", ButtonNorm, TextLight, 22);
        RectAt(backBtn, 0.05f, 0.5f, 60, 44);
        var titleLbl = MakeTMP("GameTitleLabel", nav, "Game Room", 22, bold: true, color: TextLight);
        RectAt(titleLbl, 0.42f, 0.5f, 300, 40);
        var clueBtn  = MakeButton("CluesButton", nav, "Clues", ButtonNorm, Accent, 18);
        RectAt(clueBtn, 0.84f, 0.5f, 110, 40);
        var clueCnt  = MakeTMP("ClueCountLabel", clueBtn, "0", 14, color: BgDark);
        RectAt(clueCnt, 0.85f, 0.75f, 24, 24);

        // Chat scroll view
        var scroll = MakeScrollView("ChatScrollView", content);
        var scrollRT = scroll.GetComponent<RectTransform>();
        scrollRT.anchorMin = new Vector2(0.01f, 0.12f);
        scrollRT.anchorMax = new Vector2(0.99f, 0.90f);
        scrollRT.offsetMin = scrollRT.offsetMax = Vector2.zero;
        var chatContent = scroll.transform.Find("Viewport/Content");

        // Input row
        var inputRow = NewChild("InputRow", content);
        var inputRowRT = inputRow.GetComponent<RectTransform>();
        inputRowRT.anchorMin = new Vector2(0.01f, 0.01f);
        inputRowRT.anchorMax = new Vector2(0.99f, 0.11f);
        inputRowRT.offsetMin = inputRowRT.offsetMax = Vector2.zero;

        var inputField = MakeInputField("InputField", inputRow, "Ask a question…");
        var inputRT = inputField.GetComponent<RectTransform>();
        inputRT.anchorMin = new Vector2(0, 0); inputRT.anchorMax = new Vector2(0.78f, 1f);
        inputRT.offsetMin = inputRT.offsetMax = Vector2.zero;

        var sendBtn = MakeButton("SendButton", inputRow, "Send", Accent, BgDark, 20);
        var sendRT  = sendBtn.GetComponent<RectTransform>();
        sendRT.anchorMin = new Vector2(0.80f, 0.1f); sendRT.anchorMax = new Vector2(1f, 0.9f);
        sendRT.offsetMin = sendRT.offsetMax = Vector2.zero;

        // Win banner (hidden)
        var winBanner = NewChild("WinBanner", content);
        Stretch(winBanner.GetComponent<RectTransform>());
        winBanner.AddComponent<Image>().color = new Color(0, 0, 0, 0.75f);
        var truthLbl = MakeTMP("TruthRevealText", winBanner, "", 28, color: TextLight);
        RectAt(truthLbl, 0.5f, 0.5f, 700, 200);
        var leaveBtn = MakeButton("LeaveButton", winBanner, "Leave Room", ButtonNorm, TextLight, 22);
        RectAt(leaveBtn, 0.5f, 0.25f, 220, 54);
        winBanner.SetActive(false);

        var ctrl = content.AddComponent<GameRoomController>();
        SetField(ctrl, "gameTitleLabel",   titleLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "backButton",       backBtn.GetComponent<Button>());
        SetField(ctrl, "cluesButton",      clueBtn.GetComponent<Button>());
        SetField(ctrl, "clueCountLabel",   clueCnt.GetComponent<TMP_Text>());
        SetField(ctrl, "chatScrollRect",   scroll.GetComponent<ScrollRect>());
        SetField(ctrl, "chatContent",      (RectTransform)chatContent);
        SetField(ctrl, "inputField",       inputField.GetComponent<TMP_InputField>());
        SetField(ctrl, "sendButton",       sendBtn.GetComponent<Button>());
        SetField(ctrl, "sendButtonBg",     sendBtn.GetComponent<Image>());
        SetField(ctrl, "winBanner",        winBanner);
        SetField(ctrl, "truthRevealText",  truthLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "leaveButton",      leaveBtn.GetComponent<Button>());

        SaveScene(scene, "GameRoom");
    }

    // ═════════════════════════════════════════════════════════════════════════
    // HELPERS
    // ═════════════════════════════════════════════════════════════════════════

    static UnityEngine.SceneManagement.Scene OpenScene(string name)
    {
        var path = $"Assets/Scenes/{name}.unity";
        if (!File.Exists(Path.Combine(Application.dataPath, $"../Assets/Scenes/{name}.unity")))
        {
            var s = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            EditorSceneManager.SaveScene(s, path);
        }
        return EditorSceneManager.OpenScene(path, OpenSceneMode.Single);
    }

    static void ClearScene()
    {
        var roots = UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects();
        foreach (var go in roots) Object.DestroyImmediate(go);
    }

    static void SaveScene(UnityEngine.SceneManagement.Scene scene, string name)
    {
        EditorSceneManager.SaveScene(scene, $"Assets/Scenes/{name}.unity");
        Debug.Log($"[AI DM Setup] {name} scene saved.");
    }

    static void EnsureScenesFolder()
    {
        if (!AssetDatabase.IsValidFolder("Assets/Scenes"))
            AssetDatabase.CreateFolder("Assets", "Scenes");
    }

    static GameObject NewGO(string name)
    {
        var go = new GameObject(name);
        go.AddComponent<RectTransform>();
        return go;
    }

    static GameObject NewChild(string name, GameObject parent)
    {
        var go = new GameObject(name, typeof(RectTransform));
        go.transform.SetParent(parent.transform, false);
        return go;
    }

    static Canvas MakeCanvas(string name)
    {
        // Camera — required so the Game view doesn't show "No cameras rendering"
        var camGO  = new GameObject("Main Camera");
        var cam    = camGO.AddComponent<Camera>();
        cam.clearFlags       = CameraClearFlags.SolidColor;
        cam.backgroundColor  = new Color(0.05f, 0.03f, 0.09f);
        cam.orthographic     = true;
        cam.depth            = -1;
        camGO.tag            = "MainCamera";

        var go     = new GameObject(name);
        var canvas = go.AddComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;

        var scaler = go.AddComponent<CanvasScaler>();
        scaler.uiScaleMode         = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920, 1080);
        scaler.matchWidthOrHeight  = 0.5f;

        go.AddComponent<GraphicRaycaster>();

        // EventSystem (one per scene)
        if (Object.FindFirstObjectByType<EventSystem>() == null)
        {
            var es = new GameObject("EventSystem");
            es.AddComponent<EventSystem>();
            es.AddComponent<StandaloneInputModule>();
        }

        return canvas;
    }

    static void Stretch(RectTransform rt)
    {
        rt.anchorMin  = Vector2.zero;
        rt.anchorMax  = Vector2.one;
        rt.offsetMin  = Vector2.zero;
        rt.offsetMax  = Vector2.zero;
    }

    /// Place a child at normalised anchor position with fixed pixel size.
    static void RectAt(GameObject go, float ax, float ay, float w, float h)
    {
        var rt      = go.GetComponent<RectTransform>();
        rt.anchorMin = rt.anchorMax = new Vector2(ax, ay);
        rt.pivot     = new Vector2(0.5f, 0.5f);
        rt.sizeDelta = new Vector2(w, h);
        rt.anchoredPosition = Vector2.zero;
    }

    static GameObject MakeTMP(string name, GameObject parent, string text,
        float fontSize = 20, bool bold = false, Color? color = null)
    {
        var go  = NewChild(name, parent);
        var tmp = go.AddComponent<TextMeshProUGUI>();
        tmp.text      = text;
        tmp.fontSize  = fontSize;
        tmp.color     = color ?? TextLight;
        tmp.fontStyle = bold ? FontStyles.Bold : FontStyles.Normal;
        tmp.alignment = TextAlignmentOptions.Center;
        tmp.raycastTarget = false;
        return go;
    }

    static GameObject MakeButton(string name, GameObject parent,
        string label, Color bgColor, Color textColor, float fontSize = 20)
    {
        var go  = NewChild(name, parent);
        var img = go.AddComponent<Image>();
        img.color = bgColor;
        var btn = go.AddComponent<Button>();
        var cs  = btn.colors;
        cs.highlightedColor = new Color(
            Mathf.Min(bgColor.r + 0.1f, 1f),
            Mathf.Min(bgColor.g + 0.1f, 1f),
            Mathf.Min(bgColor.b + 0.1f, 1f));
        cs.pressedColor = new Color(
            Mathf.Max(bgColor.r - 0.1f, 0f),
            Mathf.Max(bgColor.g - 0.1f, 0f),
            Mathf.Max(bgColor.b - 0.1f, 0f));
        btn.colors = cs;

        var lbl = MakeTMP("Label", go, label, fontSize, color: textColor);
        Stretch(lbl.GetComponent<RectTransform>());
        return go;
    }

    static GameObject MakeInputField(string name, GameObject parent, string placeholder)
    {
        var go   = NewChild(name, parent);
        go.AddComponent<Image>().color = new Color(0.12f, 0.10f, 0.18f);

        var field = go.AddComponent<TMP_InputField>();

        var textArea = NewChild("Text Area", go);
        Stretch(textArea.GetComponent<RectTransform>());
        var mask = textArea.AddComponent<RectMask2D>();

        var phGO  = NewChild("Placeholder", textArea);
        Stretch(phGO.GetComponent<RectTransform>());
        var ph    = phGO.AddComponent<TextMeshProUGUI>();
        ph.text   = placeholder;
        ph.color  = new Color(0.5f, 0.5f, 0.5f);
        ph.fontSize = 20;
        ph.fontStyle = FontStyles.Italic;

        var txtGO = NewChild("Text", textArea);
        Stretch(txtGO.GetComponent<RectTransform>());
        var txt   = txtGO.AddComponent<TextMeshProUGUI>();
        txt.color = TextLight;
        txt.fontSize = 20;

        field.textViewport   = textArea.GetComponent<RectTransform>();
        field.textComponent  = txt;
        field.placeholder    = ph;

        return go;
    }

    static GameObject MakeScrollView(string name, GameObject parent)
    {
        var go   = NewChild(name, parent);
        go.AddComponent<Image>().color = new Color(0.06f, 0.05f, 0.10f);

        var scroll = go.AddComponent<ScrollRect>();

        var viewport = NewChild("Viewport", go);
        Stretch(viewport.GetComponent<RectTransform>());
        viewport.AddComponent<Image>().color = Color.clear;
        viewport.AddComponent<Mask>().showMaskGraphic = false;

        var contentGO = NewChild("Content", viewport);
        var contentRT = contentGO.GetComponent<RectTransform>();
        contentRT.anchorMin = new Vector2(0, 1);
        contentRT.anchorMax = new Vector2(1, 1);
        contentRT.pivot     = new Vector2(0.5f, 1f);
        contentRT.sizeDelta = new Vector2(0, 0);
        var vlg = contentGO.AddComponent<VerticalLayoutGroup>();
        vlg.spacing = 8;
        vlg.padding = new RectOffset(8, 8, 8, 8);
        vlg.childControlWidth  = true;
        vlg.childControlHeight = true;
        contentGO.AddComponent<ContentSizeFitter>().verticalFit =
            ContentSizeFitter.FitMode.PreferredSize;

        scroll.viewport  = viewport.GetComponent<RectTransform>();
        scroll.content   = contentRT;
        scroll.horizontal = false;
        scroll.vertical   = true;
        scroll.scrollSensitivity = 30;

        return go;
    }

    /// Set a private [SerializeField] field via SerializedObject.
    static void SetField(Object target, string fieldName, Object value)
    {
        if (value == null) return;
        var so   = new SerializedObject(target);
        var prop = so.FindProperty(fieldName);
        if (prop == null)
        {
            Debug.LogWarning($"[AI DM Setup] Field '{fieldName}' not found on {target.GetType().Name}");
            return;
        }
        prop.objectReferenceValue = value;
        so.ApplyModifiedPropertiesWithoutUndo();
    }

    /// Overload for Transform.
    static void SetField(Object target, string fieldName, Transform value)
        => SetField(target, fieldName, (Object)value);

    /// Overload for RectTransform.
    static void SetField(Object target, string fieldName, RectTransform value)
        => SetField(target, fieldName, (Object)value);
}
#endif
