// AI DM → Setup Scenes
// Run from the menu bar: AI DM → Setup All Scenes
// Builds GameObjects, Canvas hierarchy, UI elements, and wires all Inspector
// references for every scene so you can hit Play immediately.
#if UNITY_EDITOR
using System.IO;
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.TextCore.LowLevel;
using TMPro;
using UnityEngine.EventSystems;

public static class SceneSetupWizard
{
    // ── 300Mind sprite helpers ────────────────────────────────────────────────
    const string Sheet1 = "Assets/300Mind/2D Game UI Kit/Sprites/UI-pack_Sprite_1.png";
    const string Sheet2 = "Assets/300Mind/2D Game UI Kit/Sprites/UI-pack_Sprite_2.png";

    // Load a named sub-sprite from the 300Mind sprite sheet.
    static Sprite SubSprite(string sheet, string name)
    {
        foreach (var a in AssetDatabase.LoadAllAssetsAtPath(sheet))
            if (a is Sprite s && s.name == name) return s;
        Debug.LogWarning($"[AI DM Setup] Sub-sprite '{name}' not found in {System.IO.Path.GetFileName(sheet)}");
        return null;
    }
    static void ApplySpr(Image img, Sprite sprite, Image.Type type = Image.Type.Simple)
    {
        if (img == null || sprite == null) return;
        img.sprite = sprite; img.type = type; img.color = Color.white;
    }
    // Legacy overload — kept for call-sites that haven't migrated yet.
    static void ApplySpr(Image img, string name, Image.Type type = Image.Type.Simple)
    {
        var s = AssetDatabase.LoadAssetAtPath<Sprite>($"Assets/Art/UI/Components/{name}.png");
        if (s != null) ApplySpr(img, s, type);
    }

    // ── Colors (dark navy mobile theme) ──────────────────────────────────────
    static readonly Color BgDark      = new(0.04f, 0.09f, 0.16f);   // #0a1628 dark navy
    static readonly Color CardBg      = new(0.10f, 0.15f, 0.27f);   // #1a2745 card bg
    static readonly Color Accent      = new(0.95f, 0.76f, 0.20f);   // #f2c233 gold
    static readonly Color PanelDark   = new(0.06f, 0.10f, 0.20f, 0.95f);
    static readonly Color TextLight   = new(0.95f, 0.95f, 0.98f);
    static readonly Color ButtonNorm  = new(0.13f, 0.20f, 0.35f);
    static readonly Color EasyGreen   = new(0.15f, 0.68f, 0.38f);   // #27AE60
    static readonly Color MedBlue     = new(0.16f, 0.50f, 0.73f);   // #2980B9
    static readonly Color HardOrange  = new(0.90f, 0.49f, 0.13f);   // #E67E22
    static readonly Color ClassicPurp = new(0.56f, 0.27f, 0.68f);   // #8E44AD

    // ── Entry point ───────────────────────────────────────────────────────────

    [MenuItem("AI DM/Setup All Scenes")]
    public static void SetupAll()
    {
        EnsureScenesFolder();
        SetupCJKFont();   // font first — scenes reference it
        SetupBoot();
        SetupLogin();
        SetupMainMenu();
        SetupRoomBrowser();
        SetupWaitingRoom();
        SetupGameRoom();
        RegisterBuildSettings();
        // Re-open Boot so it's ready to Play
        EditorSceneManager.OpenScene("Assets/Scenes/Boot.unity");
        EditorUtility.DisplayDialog("AI DM Setup", "All 6 scenes built and registered!\n\nPress ▶ Play now — Boot → Login → MainMenu.", "OK");
    }

    [MenuItem("AI DM/Setup CJK Font")]
    public static void SetupCJKFont()
    {
        const string src    = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf";
        const string dstRel = "Assets/Fonts/ArialUnicode.ttf";
        const string faPath = "Assets/Fonts/ArialUnicode SDF.asset";

        // ── 1. Copy font into project ─────────────────────────────────────────
        if (!AssetDatabase.IsValidFolder("Assets/Fonts"))
            AssetDatabase.CreateFolder("Assets", "Fonts");

        string dstAbs = Path.GetFullPath(Path.Combine(Application.dataPath, "../" + dstRel));
        if (!File.Exists(dstAbs))
        {
            if (!File.Exists(src)) { Debug.LogWarning("[AI DM] Arial Unicode not found — CJK will show boxes."); return; }
            File.Copy(src, dstAbs);
        }
        AssetDatabase.ImportAsset(dstRel, ImportAssetOptions.ForceUpdate);

        // ── 2. Create Dynamic font asset with a guaranteed valid atlas texture ──
        {
            // Always delete and recreate to clear any broken references.
            if (AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(faPath) != null)
                AssetDatabase.DeleteAsset(faPath);

            var font = AssetDatabase.LoadAssetAtPath<Font>(dstRel);
            if (font == null) { Debug.LogError("[AI DM] Font import failed: " + dstRel); return; }

            var fa = TMP_FontAsset.CreateFontAsset(
                font, 90, 9, GlyphRenderMode.SDFAA, 1024, 1024,
                AtlasPopulationMode.Dynamic, true);
            fa.name = "ArialUnicode SDF";

            // Dynamic mode does NOT pre-allocate atlas textures — m_AtlasTextures
            // is null/empty after CreateFontAsset(). We must create the atlas
            // texture ourselves, add it as a sub-asset, then reload from disk and
            // wire up the reference via SerializedObject. Direct property mutation
            // on the in-memory object will not survive serialization.
            var atlas = new Texture2D(1024, 1024, TextureFormat.Alpha8, false, true);
            atlas.name = fa.name + " Atlas";

            // Step 1: save the font asset root
            AssetDatabase.CreateAsset(fa, faPath);
            // Step 2: embed the atlas texture so it gets a stable file ID
            AssetDatabase.AddObjectToAsset(atlas, fa);
            // Step 3: also embed any material CreateFontAsset did create
            if (fa.material != null && !AssetDatabase.Contains(fa.material))
            {
                fa.material.name = fa.name + " Material";
                AssetDatabase.AddObjectToAsset(fa.material, fa);
            }
            AssetDatabase.SaveAssets();

            // Step 4: reload from disk — only disk-resident objects have stable IDs
            var savedFa = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(faPath);
            Texture2D savedAtlas = null;
            Material  savedMat   = null;
            foreach (var obj in AssetDatabase.LoadAllAssetsAtPath(faPath))
            {
                if (obj is Texture2D t) savedAtlas = t;
                else if (obj is Material m) savedMat = m;
            }

            if (savedFa == null || savedAtlas == null)
            {
                Debug.LogError($"[AI DM] CJK font wiring failed — fa={savedFa}, atlas={savedAtlas}");
                return;
            }

            // If CreateFontAsset didn't produce a material, create one now
            if (savedMat == null)
            {
                var dfShader = Shader.Find("TextMeshPro/Distance Field");
                if (dfShader != null)
                {
                    savedMat = new Material(dfShader);
                    savedMat.name = savedFa.name + " Material";
                    AssetDatabase.AddObjectToAsset(savedMat, faPath);
                    AssetDatabase.SaveAssets();
                    // Reload savedMat so it has a stable file ID
                    foreach (var obj in AssetDatabase.LoadAllAssetsAtPath(faPath))
                        if (obj is Material m2) savedMat = m2;
                }
            }

            // Always wire _MainTex on the material to our saved atlas sub-asset.
            // When savedMat comes from fa.material, its _MainTex still points to
            // the original in-memory Texture2D which becomes null after save/reload.
            // TMP_MaterialManager.GetFallbackMaterial crashes at tex.GetEntityId()
            // when _MainTex returns null, so this must run regardless of source.
            if (savedMat != null && savedAtlas != null)
            {
                var soMat = new SerializedObject(savedMat);
                // Find the _MainTex property by its TMP shader name
                var mainTexProp = soMat.FindProperty("_MainTex");
                if (mainTexProp != null)
                {
                    mainTexProp.objectReferenceValue = savedAtlas;
                    soMat.ApplyModifiedProperties();
                }
                else
                {
                    // Fallback: use direct SetTexture with the shader property ID
                    savedMat.SetTexture(ShaderUtilities.ID_MainTex, savedAtlas);
                }
                EditorUtility.SetDirty(savedMat);
                AssetDatabase.SaveAssets();
            }

            // Step 5: wire m_AtlasTextures[0] AND m_Material via SerializedObject.
            // TMP_MaterialManager.GetFallbackMaterial crashes if m_Material is null,
            // even if material was added as a sub-asset but not properly referenced.
            var soFa = new SerializedObject(savedFa);
            var atlasProp = soFa.FindProperty("m_AtlasTextures");
            if (atlasProp != null)
            {
                atlasProp.arraySize = 1;
                atlasProp.GetArrayElementAtIndex(0).objectReferenceValue = savedAtlas;
            }
            else Debug.LogWarning("[AI DM] m_AtlasTextures property not found.");

            if (savedMat != null)
            {
                var matProp = soFa.FindProperty("m_Material");
                if (matProp != null)
                    matProp.objectReferenceValue = savedMat;
                else Debug.LogWarning("[AI DM] m_Material property not found.");
            }

            soFa.ApplyModifiedProperties();
            EditorUtility.SetDirty(savedFa);
            AssetDatabase.SaveAssets();

            AssetDatabase.Refresh();
            Debug.Log("[AI DM] Created Dynamic TMP font asset with wired atlas+material → " + faPath);
        }

        var cjkFa = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(faPath);
        if (cjkFa == null) { Debug.LogError("[AI DM] CJK asset not found after creation: " + faPath); return; }

        // ── 3. Add to LiberationSans SDF fallback via SerializedObject ────────
        var liberation = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(
            "Assets/TextMesh Pro/Resources/Fonts & Materials/LiberationSans SDF.asset");
        if (liberation != null)
            AddFallback(liberation, cjkFa, "LiberationSans SDF");

        // ── 4. Add to TMP_Settings global fallback (catches all other fonts) ──
        var settingsPath = "Assets/TextMesh Pro/Resources/TMP Settings.asset";
        var settings = AssetDatabase.LoadAssetAtPath<TMP_Settings>(settingsPath);
        if (settings != null)
        {
            var so   = new SerializedObject(settings);
            var list = so.FindProperty("m_FallbackFontAssets");
            if (list != null)
            {
                bool found = false;
                for (int i = 0; i < list.arraySize; i++)
                    if (list.GetArrayElementAtIndex(i).objectReferenceValue == cjkFa) { found = true; break; }
                if (!found)
                {
                    list.arraySize++;
                    list.GetArrayElementAtIndex(list.arraySize - 1).objectReferenceValue = cjkFa;
                    so.ApplyModifiedProperties();
                    EditorUtility.SetDirty(settings);
                    AssetDatabase.SaveAssets();
                    Debug.Log("[AI DM] CJK added to TMP_Settings global fallback.");
                }
            }
        }
        else Debug.LogWarning("[AI DM] TMP Settings not found at " + settingsPath);

        _font = null;   // force DefaultFont() to reload on next call
        Debug.Log("[AI DM] SetupCJKFont complete — Chinese characters should now render.");
    }

    static void AddFallback(TMP_FontAsset target, TMP_FontAsset fallback, string label)
    {
        var so   = new SerializedObject(target);
        var list = so.FindProperty("m_FallbackFontAssetTable");
        if (list == null) { Debug.LogWarning("[AI DM] m_FallbackFontAssetTable not found on " + label); return; }

        for (int i = 0; i < list.arraySize; i++)
            if (list.GetArrayElementAtIndex(i).objectReferenceValue == fallback)
            { Debug.Log("[AI DM] Fallback already set on " + label); return; }

        list.arraySize++;
        list.GetArrayElementAtIndex(list.arraySize - 1).objectReferenceValue = fallback;
        so.ApplyModifiedProperties();
        EditorUtility.SetDirty(target);
        AssetDatabase.SaveAssetIfDirty(target);
        Debug.Log("[AI DM] CJK fallback added to " + label);
    }

    [MenuItem("AI DM/Register Build Settings")]
    public static void RegisterBuildSettings()
    {
        string[] names = { "Boot", "Login", "MainMenu", "RoomBrowser", "WaitingRoom", "GameRoom" };
        var entries = new EditorBuildSettingsScene[names.Length];
        for (int i = 0; i < names.Length; i++)
            entries[i] = new EditorBuildSettingsScene($"Assets/Scenes/{names[i]}.unity", true);
        EditorBuildSettings.scenes = entries;

        // Portrait — iPhone 15/16 native resolution
        PlayerSettings.defaultScreenWidth  = 1170;
        PlayerSettings.defaultScreenHeight = 2532;
        PlayerSettings.fullScreenMode      = FullScreenMode.FullScreenWindow;
        PlayerSettings.defaultInterfaceOrientation = UIOrientation.Portrait;
        PlayerSettings.runInBackground     = true;

        SetGameViewResolution(1170, 2532);  // iPhone 15/16 portrait

        Debug.Log("[AI DM Setup] Build Settings + resolution updated.");
    }

    static void SetGameViewResolution(int w, int h)
    {
        // Unity internal GameViewSizes API
        var gvsType = System.Type.GetType(
            "UnityEditor.GameViewSizes,UnityEditor");
        var svType  = System.Type.GetType(
            "UnityEditor.ScriptableSingleton`1,UnityEditor");
        if (gvsType == null || svType == null) return;

        var singletonType = svType.MakeGenericType(gvsType);
        var instance = singletonType.GetProperty("instance")
                                    ?.GetValue(null);
        if (instance == null) return;

        var currentGroup = instance.GetType()
                                   .GetMethod("GetGroup")
                                   ?.Invoke(instance, new object[] { (int)UnityEditor.GameViewSizeGroupType.Standalone });
        if (currentGroup == null) return;

        // Check if already exists
        var getCount = currentGroup.GetType().GetMethod("GetTotalCount");
        var getView  = currentGroup.GetType().GetMethod("GetGameViewSize");
        int count    = (int)(getCount?.Invoke(currentGroup, null) ?? 0);
        for (int i = 0; i < count; i++)
        {
            var existing = getView?.Invoke(currentGroup, new object[] { i });
            if (existing == null) continue;
            var ew = existing.GetType().GetProperty("width")?.GetValue(existing);
            var eh = existing.GetType().GetProperty("height")?.GetValue(existing);
            if ((int)ew == w && (int)eh == h) return; // already present
        }

        // Add new size
        var gvsSizeType = System.Type.GetType("UnityEditor.GameViewSize,UnityEditor");
        var gvsSizeGT   = System.Type.GetType("UnityEditor.GameViewSizeType,UnityEditor");
        if (gvsSizeType == null || gvsSizeGT == null) return;

        var newSize = System.Activator.CreateInstance(
            gvsSizeType,
            System.Enum.Parse(gvsSizeGT, "FixedResolution"),
            w, h, $"{w}x{h}");

        currentGroup.GetType().GetMethod("AddCustomSize")
                    ?.Invoke(currentGroup, new object[] { newSize });
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

        var canvas = MakeCanvas("Canvas");
        var safe   = NewChild("SafeAreaPanel", canvas.gameObject);
        Stretch(safe.GetComponent<RectTransform>());

        // ── BACKGROUND LAYERS (back → front) ─────────────────────────────────
        // Layer 0: Sky (swap Image.sprite with real shrine background art later)
        var bgSky = safe.AddComponent<Image>();
        bgSky.color = new Color(0.47f, 0.72f, 0.88f); // daytime sky blue

        // Layer 1: Midground — shrine/forest silhouette strip (10%–55%)
        // Replace Image.sprite with a layered environment illustration
        var bgMid = NewChild("BgMidground", safe);
        var bgMidRT = bgMid.GetComponent<RectTransform>();
        bgMidRT.anchorMin = new Vector2(0f, 0.08f);
        bgMidRT.anchorMax = new Vector2(1f, 0.58f);
        bgMidRT.offsetMin = bgMidRT.offsetMax = Vector2.zero;
        bgMid.AddComponent<Image>().color = new Color(0.14f, 0.28f, 0.14f, 0.50f);

        // Layer 2: Ground strip (bottom 10%)
        var bgGround = NewChild("BgGround", safe);
        var bgGroundRT = bgGround.GetComponent<RectTransform>();
        bgGroundRT.anchorMin = Vector2.zero;
        bgGroundRT.anchorMax = new Vector2(1f, 0.12f);
        bgGroundRT.offsetMin = bgGroundRT.offsetMax = Vector2.zero;
        bgGround.AddComponent<Image>().color = new Color(0.16f, 0.30f, 0.12f);

        // Layer 3: Cherry blossom particles
        var blossomGO = NewChild("CherryBlossom", safe);
        blossomGO.AddComponent<CherryBlossomSystem>();

        // Content area (UI elements above background)
        var content = NewChild("ContentArea", safe);
        Stretch(content.GetComponent<RectTransform>());

        // ── CHARACTER (center, full height, behind buttons) ──────────────────
        var charRoot = NewChild("CharacterRoot", content);
        var charRT   = charRoot.GetComponent<RectTransform>();
        charRT.anchorMin = new Vector2(0.05f, 0f);
        charRT.anchorMax = new Vector2(0.85f, 1f);
        charRT.offsetMin = charRT.offsetMax = Vector2.zero;
        var charImg = charRoot.AddComponent<Image>();
        charImg.raycastTarget = false;

        const string charSpritePath = "Assets/Art/MainMenu/Character/character1.png";
        var charSprite = AssetDatabase.LoadAssetAtPath<Sprite>(charSpritePath);
        if (charSprite != null)
        {
            charImg.sprite = charSprite; charImg.color = Color.white;
            charImg.type = Image.Type.Simple; charImg.preserveAspect = true;
            Debug.Log("[AI DM Setup] Character sprite loaded.");
        }
        else
        {
            charImg.color = new Color(0.22f, 0.12f, 0.38f);
            Debug.LogWarning("[AI DM Setup] Character sprite not found — using placeholder.");
        }

        // ── PET COMPANION — bottom-right above nav bar ────────────────────────
        var petGO = NewChild("PetRoot", content);
        var petRT = petGO.GetComponent<RectTransform>();
        petRT.anchorMin = petRT.anchorMax = new Vector2(0.80f, 0f);
        petRT.pivot = new Vector2(0.5f, 0f);
        petRT.sizeDelta = new Vector2(110, 110);
        petRT.anchoredPosition = new Vector2(0, 82);
        var petImg = petGO.AddComponent<Image>();
        petImg.color = new Color(1f, 1f, 1f, 0.80f); // swap sprite: pet icon

        // ── TOP HUD BAR (72px) ────────────────────────────────────────────────
        var hud   = NewChild("TopHUD", content);
        var hudRT = hud.GetComponent<RectTransform>();
        hudRT.anchorMin = new Vector2(0, 1); hudRT.anchorMax = new Vector2(1, 1);
        hudRT.pivot = new Vector2(0.5f, 1f);
        hudRT.sizeDelta = new Vector2(0, 72);
        hudRT.anchoredPosition = Vector2.zero;
        hud.AddComponent<Image>().color = new Color(0.06f, 0.04f, 0.14f, 0.85f);

        // Ornate avatar frame (left) — outer gold ring + inner colored circle
        var afGO = NewChild("AvatarFrame", hud);
        var afRT = afGO.GetComponent<RectTransform>();
        afRT.anchorMin = afRT.anchorMax = new Vector2(0f, 0.5f);
        afRT.pivot = new Vector2(0f, 0.5f);
        afRT.sizeDelta = new Vector2(58, 58);
        afRT.anchoredPosition = new Vector2(8, 0);
        afGO.AddComponent<Image>().color = Accent; // gold outer ring

        var afInner = NewChild("AvatarInner", afGO);
        var afInnerRT = afInner.GetComponent<RectTransform>();
        afInnerRT.anchorMin = new Vector2(0.10f, 0.10f);
        afInnerRT.anchorMax = new Vector2(0.90f, 0.90f);
        afInnerRT.offsetMin = afInnerRT.offsetMax = Vector2.zero;
        var avatarImg = afInner.AddComponent<Image>();
        avatarImg.color = new Color(0.45f, 0.22f, 0.65f); // set by controller at runtime

        var initLbl = MakeTMP("PlayerInitialLabel", afInner, "?", 22, bold: true, color: Color.white);
        Stretch(initLbl.GetComponent<RectTransform>());

        // Rank badge — overlapping bottom edge of avatar frame
        var rankGO = NewChild("RankBadge", afGO);
        var rankRT = rankGO.GetComponent<RectTransform>();
        rankRT.anchorMin = rankRT.anchorMax = new Vector2(0.5f, 0f);
        rankRT.pivot = new Vector2(0.5f, 0f);
        rankRT.sizeDelta = new Vector2(46, 18);
        rankRT.anchoredPosition = new Vector2(0, -3);
        rankGO.AddComponent<Image>().color = new Color(0.36f, 0.14f, 0.54f);
        var rankLbl = MakeTMP("RankLabel", rankGO, "Beginner", 11, color: Color.white);
        Stretch(rankLbl.GetComponent<RectTransform>());

        // Player name (right of avatar frame)
        var playerLbl = MakeTMP("PlayerNameLabel", hud, "Adventurer", 18, color: TextLight);
        RectAt(playerLbl, 0.23f, 0.5f, 150, 32);

        // Gold coin frame
        var coinFrame = NewChild("CoinFrame", hud);
        var cfRT = coinFrame.GetComponent<RectTransform>();
        cfRT.anchorMin = cfRT.anchorMax = new Vector2(0.50f, 0.5f);
        cfRT.pivot = new Vector2(0.5f, 0.5f);
        cfRT.sizeDelta = new Vector2(108, 34);
        cfRT.anchoredPosition = Vector2.zero;
        coinFrame.AddComponent<Image>().color = new Color(0.12f, 0.08f, 0.04f, 0.90f);
        var coinBorder = NewChild("CoinBorder", coinFrame);
        var coinBorderRT = coinBorder.GetComponent<RectTransform>();
        coinBorderRT.anchorMin = Vector2.zero; coinBorderRT.anchorMax = Vector2.one;
        coinBorderRT.offsetMin = new Vector2(2, 2); coinBorderRT.offsetMax = new Vector2(-2, -2);
        coinBorder.AddComponent<Image>().color = new Color(Accent.r, Accent.g, Accent.b, 0.50f);
        var coinIcon = MakeTMP("CoinIcon", coinFrame, "★", 18, bold: true, color: Accent);
        RectAt(coinIcon, 0.16f, 0.5f, 22, 28);
        var coinLbl = MakeTMP("CoinLabel", coinFrame, "0", 17, color: TextLight);
        RectAt(coinLbl, 0.60f, 0.5f, 70, 28);

        // Gem frame
        var gemFrame = NewChild("GemFrame", hud);
        var gfRT = gemFrame.GetComponent<RectTransform>();
        gfRT.anchorMin = gfRT.anchorMax = new Vector2(0.72f, 0.5f);
        gfRT.pivot = new Vector2(0.5f, 0.5f);
        gfRT.sizeDelta = new Vector2(96, 34);
        gfRT.anchoredPosition = Vector2.zero;
        gemFrame.AddComponent<Image>().color = new Color(0.04f, 0.08f, 0.18f, 0.90f);
        var gemBorder = NewChild("GemBorder", gemFrame);
        var gemBorderRT = gemBorder.GetComponent<RectTransform>();
        gemBorderRT.anchorMin = Vector2.zero; gemBorderRT.anchorMax = Vector2.one;
        gemBorderRT.offsetMin = new Vector2(2, 2); gemBorderRT.offsetMax = new Vector2(-2, -2);
        gemBorder.AddComponent<Image>().color = new Color(0.38f, 0.76f, 1f, 0.45f);
        var gemIcon = MakeTMP("GemIcon", gemFrame, "◆", 16, bold: true, color: new Color(0.4f, 0.8f, 1f));
        RectAt(gemIcon, 0.17f, 0.5f, 20, 28);
        var gemLbl = MakeTMP("GemLabel", gemFrame, "0", 17, color: TextLight);
        RectAt(gemLbl, 0.60f, 0.5f, 60, 28);

        // Top-right utility icons: mailbox, announcement bell, settings gear
        MakeHudIconBtn("MailBtn",     hud, "✉", 0.85f);
        MakeHudIconBtn("BellBtn",     hud, "◎", 0.91f);
        MakeHudIconBtn("SettingsBtn", hud, "⚙", 0.97f);

        // ── ANNOUNCEMENT MARQUEE (just below top HUD) ─────────────────────────
        var marqBar = NewChild("MarqueeBar", content);
        var marqBarRT = marqBar.GetComponent<RectTransform>();
        marqBarRT.anchorMin = new Vector2(0, 1); marqBarRT.anchorMax = new Vector2(1, 1);
        marqBarRT.pivot = new Vector2(0.5f, 1f);
        marqBarRT.sizeDelta = new Vector2(0, 30);
        marqBarRT.anchoredPosition = new Vector2(0, -72);
        marqBar.AddComponent<Image>().color = new Color(0.08f, 0.04f, 0.18f, 0.78f);

        var marqMask = NewChild("MarqueeMask", marqBar);
        Stretch(marqMask.GetComponent<RectTransform>());
        marqMask.AddComponent<Image>().color = Color.clear;
        marqMask.AddComponent<Mask>().showMaskGraphic = false;

        var marqTextGO = NewChild("AnnouncementText", marqMask);
        var marqTextRT = marqTextGO.GetComponent<RectTransform>();
        marqTextRT.anchorMin = new Vector2(0, 0); marqTextRT.anchorMax = new Vector2(0, 1);
        marqTextRT.pivot = new Vector2(0, 0.5f);
        marqTextRT.sizeDelta = new Vector2(1400, 0);
        marqTextRT.anchoredPosition = Vector2.zero;
        var marqTMP = marqTextGO.AddComponent<TextMeshProUGUI>();
        marqTMP.font = DefaultFont();
        marqTMP.text = "New Event: Shrine Festival!   New Pet: Nine-Tailed Fox   Limited Puzzle: The Vanishing Magistrate";
        marqTMP.fontSize = 19; marqTMP.color = new Color(1f, 0.90f, 0.55f);
        marqTMP.alignment = TextAlignmentOptions.MidlineLeft;
        marqTMP.raycastTarget = false;

        // ── SKILL BADGE SLOTS (left edge, next to character) ─────────────────
        var skillBadge1 = BuildSkillBadge("SkillBadge1", content, new Vector2(0.07f, 0.65f), "Hint");
        var skillBadge2 = BuildSkillBadge("SkillBadge2", content, new Vector2(0.07f, 0.52f), "Clue");
        var bSlot1RT    = skillBadge1.GetComponent<RectTransform>();
        var bSlot2RT    = skillBadge2.GetComponent<RectTransform>();

        // ── GAME MODE BUTTONS — 2 modes, bottom-center ────────────────────────
        var btnPanel   = NewChild("ButtonPanel", content);
        var btnPanelRT = btnPanel.GetComponent<RectTransform>();
        btnPanelRT.anchorMin = new Vector2(0.06f, 0.10f);
        btnPanelRT.anchorMax = new Vector2(0.94f, 0.42f);
        btnPanelRT.offsetMin = btnPanelRT.offsetMax = Vector2.zero;

        var tsBtn = BuildOrnateButton("TurtleSoupButton",    btnPanel, "Turtle Soup",     "海龟汤", "◉");
        var mmBtn = BuildOrnateButton("MurderMysteryButton", btnPanel, "Murder Mystery",  "剧本杀", "⬡");

        // Two buttons stacked, larger gap
        LayoutButton(tsBtn, btnPanelRT, 0.73f);
        LayoutButton(mmBtn, btnPanelRT, 0.27f);

        // ── BOTTOM NAVIGATION — 4 tabs ────────────────────────────────────────
        var bottomNav = NewChild("BottomNav", content);
        var bnRT = bottomNav.GetComponent<RectTransform>();
        bnRT.anchorMin = Vector2.zero; bnRT.anchorMax = new Vector2(1, 0);
        bnRT.pivot = new Vector2(0.5f, 0f);
        bnRT.sizeDelta = new Vector2(0, 80);
        bnRT.anchoredPosition = Vector2.zero;
        bottomNav.AddComponent<Image>().color = new Color(0.07f, 0.04f, 0.14f, 0.94f);

        // Gold separator line at top of nav bar
        var navLine = NewChild("NavLine", bottomNav);
        var nlRT    = navLine.GetComponent<RectTransform>();
        nlRT.anchorMin = new Vector2(0, 1); nlRT.anchorMax = new Vector2(1, 1);
        nlRT.pivot = new Vector2(0.5f, 1f);
        nlRT.sizeDelta = new Vector2(0, 2);
        nlRT.anchoredPosition = Vector2.zero;
        navLine.AddComponent<Image>().color = new Color(Accent.r, Accent.g, Accent.b, 0.55f);

        BuildNavTab("ShopTab",     bottomNav, "⊞", "Shop",    0.125f);
        BuildNavTab("FriendsTab",  bottomNav, "⊕", "Friends", 0.375f);
        BuildNavTab("BackpackTab", bottomNav, "⊟", "Pack",    0.625f);
        BuildNavTab("PetTab",      bottomNav, "⊛", "Pet",     0.875f);

        // ── MAIN MENU CONTROLLER ─────────────────────────────────────────────
        var ctrl = content.AddComponent<MainMenuController>();
        SetField(ctrl, "characterRoot",       charRT);
        SetField(ctrl, "characterImage",      charImg);
        SetField(ctrl, "petRoot",             petRT);
        SetField(ctrl, "petImage",            petImg);
        SetField(ctrl, "skillBubble1",        bSlot1RT);
        SetField(ctrl, "skillBubble2",        bSlot2RT);
        SetField(ctrl, "playerNameLabel",     playerLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "coinBalanceLabel",    coinLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "playerAvatarBg",      avatarImg);
        SetField(ctrl, "playerInitialLabel",  initLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "announcementMarquee", marqTMP);
        SetField(ctrl, "marqueeRect",         marqTextRT);
        SetField(ctrl, "turtleSoupButton",    tsBtn.GetComponent<Button>());
        SetField(ctrl, "murderMysteryButton", mmBtn.GetComponent<Button>());
        // friendsLobbyButton intentionally null — Friends moved to bottom nav

        SaveScene(scene, "MainMenu");
    }

    // ── Ornate game-mode button (two-row text, left icon, right chevron) ──────
    static GameObject BuildOrnateButton(string name, GameObject parent,
        string titleEn, string titleZh, string iconSymbol)
    {
        // Outer dark wood frame
        var go  = NewChild(name, parent);
        go.AddComponent<Image>().color = new Color(0.13f, 0.07f, 0.03f, 0.96f);
        go.AddComponent<Button>();

        // Gold border (3 px inset each side)
        var border   = NewChild("Border", go);
        var borderRT = border.GetComponent<RectTransform>();
        borderRT.anchorMin = Vector2.zero; borderRT.anchorMax = Vector2.one;
        borderRT.offsetMin = new Vector2(3, 3); borderRT.offsetMax = new Vector2(-3, -3);
        border.AddComponent<Image>().color = new Color(0.80f, 0.62f, 0.15f, 0.68f);

        // Inner content panel (slightly inset from border)
        var inner   = NewChild("Inner", go);
        var innerRT = inner.GetComponent<RectTransform>();
        innerRT.anchorMin = Vector2.zero; innerRT.anchorMax = Vector2.one;
        innerRT.offsetMin = new Vector2(5, 5); innerRT.offsetMax = new Vector2(-5, -5);
        inner.AddComponent<Image>().color = new Color(0.20f, 0.11f, 0.05f, 0.92f);

        // Left icon panel
        var iconPanel   = NewChild("IconPanel", inner);
        var ipRT        = iconPanel.GetComponent<RectTransform>();
        ipRT.anchorMin  = new Vector2(0, 0); ipRT.anchorMax = new Vector2(0, 1);
        ipRT.pivot      = new Vector2(0, 0.5f);
        ipRT.sizeDelta  = new Vector2(68, 0);
        ipRT.anchoredPosition = new Vector2(4, 0);
        iconPanel.AddComponent<Image>().color = new Color(0.09f, 0.05f, 0.02f, 0.85f);
        var iconLbl = MakeTMP("IconLbl", iconPanel, iconSymbol, 26, bold: true, color: Accent);
        Stretch(iconLbl.GetComponent<RectTransform>());

        // English title (upper half, left-aligned)
        var titleEnGO  = MakeTMP("TitleEn", inner, titleEn, 22, bold: true, color: TextLight);
        var titleEnRT  = titleEnGO.GetComponent<RectTransform>();
        titleEnRT.anchorMin = new Vector2(0.21f, 0.52f); titleEnRT.anchorMax = new Vector2(0.84f, 1f);
        titleEnRT.offsetMin = titleEnRT.offsetMax = Vector2.zero;
        titleEnGO.GetComponent<TMP_Text>().alignment = TextAlignmentOptions.MidlineLeft;

        // Chinese subtitle (lower half, left-aligned, dimmer gold)
        var titleZhGO  = MakeTMP("TitleZh", inner, titleZh, 17, color: new Color(0.85f, 0.72f, 0.42f));
        var titleZhRT  = titleZhGO.GetComponent<RectTransform>();
        titleZhRT.anchorMin = new Vector2(0.21f, 0f); titleZhRT.anchorMax = new Vector2(0.84f, 0.50f);
        titleZhRT.offsetMin = titleZhRT.offsetMax = Vector2.zero;
        titleZhGO.GetComponent<TMP_Text>().alignment = TextAlignmentOptions.MidlineLeft;

        // Right chevron
        var chevGO  = MakeTMP("Chevron", inner, "›", 30, bold: true,
                               color: new Color(Accent.r, Accent.g, Accent.b, 0.80f));
        var chevRT  = chevGO.GetComponent<RectTransform>();
        chevRT.anchorMin = new Vector2(0.86f, 0f); chevRT.anchorMax = new Vector2(1f, 1f);
        chevRT.offsetMin = chevRT.offsetMax = Vector2.zero;

        return go;
    }

    // ── Skill badge: gold ring + dark fill + icon symbol + name label + level ─
    static GameObject BuildSkillBadge(string name, GameObject parent,
        Vector2 anchorCenter, string skillName)
    {
        var go = NewChild(name, parent);
        var rt = go.GetComponent<RectTransform>();
        rt.anchorMin = rt.anchorMax = anchorCenter;
        rt.pivot     = new Vector2(0.5f, 0.5f);
        rt.sizeDelta = new Vector2(64, 82);
        rt.anchoredPosition = Vector2.zero;

        // Gold outer ring (top 78% of the badge height = the circle)
        var ring   = NewChild("Ring", go);
        var ringRT = ring.GetComponent<RectTransform>();
        ringRT.anchorMin = new Vector2(0f, 0.22f); ringRT.anchorMax = new Vector2(1f, 1f);
        ringRT.offsetMin = ringRT.offsetMax = Vector2.zero;
        ring.AddComponent<Image>().color = Accent;

        // Dark inner fill
        var fill   = NewChild("Fill", ring);
        var fillRT = fill.GetComponent<RectTransform>();
        fillRT.anchorMin = new Vector2(0.10f, 0.10f); fillRT.anchorMax = new Vector2(0.90f, 0.90f);
        fillRT.offsetMin = fillRT.offsetMax = Vector2.zero;
        fill.AddComponent<Image>().color = new Color(0.11f, 0.06f, 0.20f);

        // Skill icon
        var iconGO = MakeTMP("SkillIcon", fill, "◉", 22, bold: true,
                              color: new Color(1f, 0.85f, 0.40f));
        Stretch(iconGO.GetComponent<RectTransform>());

        // Level badge — top-right corner of ring
        var lvlGO  = NewChild("LevelBadge", ring);
        var lvlRT  = lvlGO.GetComponent<RectTransform>();
        lvlRT.anchorMin = lvlRT.anchorMax = new Vector2(1f, 1f);
        lvlRT.pivot     = new Vector2(0.5f, 0.5f);
        lvlRT.sizeDelta = new Vector2(22, 22);
        lvlRT.anchoredPosition = new Vector2(-5, -5);
        lvlGO.AddComponent<Image>().color = new Color(0.56f, 0.27f, 0.68f);
        var lvlLbl = MakeTMP("LvlLbl", lvlGO, "1", 12, bold: true, color: Color.white);
        Stretch(lvlLbl.GetComponent<RectTransform>());

        // Skill name label (bottom strip)
        var nameLbl = MakeTMP("NameLabel", go, skillName, 13, color: TextLight);
        var nameLblRT = nameLbl.GetComponent<RectTransform>();
        nameLblRT.anchorMin = new Vector2(0f, 0f); nameLblRT.anchorMax = new Vector2(1f, 0.22f);
        nameLblRT.offsetMin = nameLblRT.offsetMax = Vector2.zero;

        return go;
    }

    // ── Small HUD icon button (top-right cluster) ─────────────────────────────
    static void MakeHudIconBtn(string name, GameObject parent, string symbol, float xAnchor)
    {
        var go = NewChild(name, parent);
        var rt = go.GetComponent<RectTransform>();
        rt.anchorMin = rt.anchorMax = new Vector2(xAnchor, 0.5f);
        rt.pivot     = new Vector2(1f, 0.5f);
        rt.sizeDelta = new Vector2(36, 36);
        rt.anchoredPosition = new Vector2(-4, 0);
        go.AddComponent<Image>().color = new Color(0.18f, 0.12f, 0.28f, 0.75f);
        go.AddComponent<Button>();
        var lbl = MakeTMP("Icon", go, symbol, 20, color: new Color(0.86f, 0.80f, 0.65f));
        Stretch(lbl.GetComponent<RectTransform>());
    }

    // ── Bottom nav tab (icon + label) ─────────────────────────────────────────
    static void BuildNavTab(string name, GameObject parent, string symbol,
        string label, float xAnchorCenter)
    {
        var go = NewChild(name, parent);
        var rt = go.GetComponent<RectTransform>();
        rt.anchorMin = new Vector2(xAnchorCenter - 0.115f, 0f);
        rt.anchorMax = new Vector2(xAnchorCenter + 0.115f, 1f);
        rt.offsetMin = rt.offsetMax = Vector2.zero;
        go.AddComponent<Button>();

        var iconGO = MakeTMP("Icon",  go, symbol, 26, color: new Color(0.84f, 0.75f, 0.58f));
        var iconRT = iconGO.GetComponent<RectTransform>();
        iconRT.anchorMin = new Vector2(0f, 0.42f); iconRT.anchorMax = new Vector2(1f, 1f);
        iconRT.offsetMin = iconRT.offsetMax = Vector2.zero;

        var lblGO  = MakeTMP("Label", go, label,  15, color: new Color(0.74f, 0.66f, 0.54f));
        var lblRT  = lblGO.GetComponent<RectTransform>();
        lblRT.anchorMin = new Vector2(0f, 0f); lblRT.anchorMax = new Vector2(1f, 0.40f);
        lblRT.offsetMin = lblRT.offsetMax = Vector2.zero;
    }

    static void LayoutButton(GameObject btn, RectTransform parent, float anchorY)
    {
        var rt = btn.GetComponent<RectTransform>();
        rt.anchorMin = new Vector2(0f, anchorY - 0.20f);
        rt.anchorMax = new Vector2(1f, anchorY + 0.20f);
        rt.offsetMin = rt.offsetMax = Vector2.zero;
    }

    // ═════════════════════════════════════════════════════════════════════════
    // ROOM BROWSER
    // ═════════════════════════════════════════════════════════════════════════

    static void BuildRoomBrowser()
    {
        var scene   = OpenScene("RoomBrowser");
        ClearScene();

        var canvas  = MakeCanvas("Canvas");
        var root    = NewChild("SafeAreaPanel", canvas.gameObject);
        Stretch(root.GetComponent<RectTransform>());
        root.AddComponent<Image>().color = BgDark;

        // ── Top HUD bar (120px, anchored top) ────────────────────────────────
        var topBar   = NewChild("TopBar", root);
        var topRT    = topBar.GetComponent<RectTransform>();
        topRT.anchorMin = new Vector2(0, 1); topRT.anchorMax = new Vector2(1, 1);
        topRT.pivot  = new Vector2(0.5f, 1f);
        topRT.sizeDelta = new Vector2(0, 120);
        topRT.anchoredPosition = Vector2.zero;
        topBar.AddComponent<Image>().color = PanelDark;

        // Avatar circle
        var avGO = NewChild("AvatarBg", topBar);
        var avRT = avGO.GetComponent<RectTransform>();
        avRT.anchorMin = avRT.anchorMax = new Vector2(0.08f, 0.5f);
        avRT.pivot = Vector2.one * 0.5f;
        avRT.sizeDelta = new Vector2(72, 72);
        avRT.anchoredPosition = Vector2.zero;
        avGO.AddComponent<Image>().color = MedBlue;
        var initL = MakeTMP("InitialLabel", avGO, "?", 26, bold: true, color: Color.white);
        Stretch(initL.GetComponent<RectTransform>());

        var nameL  = MakeTMP("PlayerNameLabel", topBar, "Username", 26, bold: true, color: TextLight);
        var nameRT = nameL.GetComponent<RectTransform>();
        nameRT.anchorMin = new Vector2(0.18f, 0.55f); nameRT.anchorMax = new Vector2(0.60f, 0.95f);
        nameRT.offsetMin = nameRT.offsetMax = Vector2.zero;
        nameL.GetComponent<TMP_Text>().alignment = TextAlignmentOptions.Left;

        var coinL  = MakeTMP("CoinLabel",  topBar, "0", 20, color: Accent);
        var coinRT = coinL.GetComponent<RectTransform>();
        coinRT.anchorMin = new Vector2(0.18f, 0.05f); coinRT.anchorMax = new Vector2(0.55f, 0.52f);
        coinRT.offsetMin = coinRT.offsetMax = Vector2.zero;
        coinL.GetComponent<TMP_Text>().alignment = TextAlignmentOptions.Left;

        // Settings button top-right
        var settBtn = MakeButton("SettingsButton", topBar, "=", PanelDark, TextLight, 26);
        var settRT  = settBtn.GetComponent<RectTransform>();
        settRT.anchorMin = settRT.anchorMax = new Vector2(0.93f, 0.5f);
        settRT.pivot = Vector2.one * 0.5f;
        settRT.sizeDelta = new Vector2(60, 60);
        settRT.anchoredPosition = Vector2.zero;

        // ── Tab pills row (70px, below TopBar) ───────────────────────────────
        var tabRow   = NewChild("TabRow", root);
        var tabRowRT = tabRow.GetComponent<RectTransform>();
        tabRowRT.anchorMin = new Vector2(0, 1); tabRowRT.anchorMax = new Vector2(1, 1);
        tabRowRT.pivot  = new Vector2(0.5f, 1f);
        tabRowRT.sizeDelta = new Vector2(0, 70);
        tabRowRT.anchoredPosition = new Vector2(0, -120);
        tabRow.AddComponent<Image>().color = PanelDark;

        var tabAR = MakeButton("TabActiveRooms",  tabRow, "Active",        ButtonNorm, TextLight, 20);
        var tabTS = MakeButton("TabTurtleSoup",   tabRow, "Turtle Soup",   Accent,     Color.white, 20);
        var tabMM = MakeButton("TabMurderMystery",tabRow, "Mystery",       ButtonNorm, TextLight, 20);
        // 300Mind pill sprite — active tab gets purple pill, inactive get dark badge
        ApplySpr(tabTS.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_1"), Image.Type.Sliced);
        ApplySpr(tabAR.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_10"), Image.Type.Sliced);
        ApplySpr(tabMM.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_10"), Image.Type.Sliced);
        var tabBtnRT_AR = tabAR.GetComponent<RectTransform>();
        var tabBtnRT_TS = tabTS.GetComponent<RectTransform>();
        var tabBtnRT_MM = tabMM.GetComponent<RectTransform>();
        tabBtnRT_AR.anchorMin = new Vector2(0.02f, 0.15f); tabBtnRT_AR.anchorMax = new Vector2(0.32f, 0.85f); tabBtnRT_AR.offsetMin = tabBtnRT_AR.offsetMax = Vector2.zero;
        tabBtnRT_TS.anchorMin = new Vector2(0.35f, 0.15f); tabBtnRT_TS.anchorMax = new Vector2(0.65f, 0.85f); tabBtnRT_TS.offsetMin = tabBtnRT_TS.offsetMax = Vector2.zero;
        tabBtnRT_MM.anchorMin = new Vector2(0.68f, 0.15f); tabBtnRT_MM.anchorMax = new Vector2(0.98f, 0.85f); tabBtnRT_MM.offsetMin = tabBtnRT_MM.offsetMax = Vector2.zero;

        // ── Join-by-code row (72px, below tabs) ───────────────────────────────
        var joinRow   = NewChild("JoinRow", root);
        var joinRowRT = joinRow.GetComponent<RectTransform>();
        joinRowRT.anchorMin = new Vector2(0, 1); joinRowRT.anchorMax = new Vector2(1, 1);
        joinRowRT.pivot  = new Vector2(0.5f, 1f);
        joinRowRT.sizeDelta = new Vector2(0, 72);
        joinRowRT.anchoredPosition = new Vector2(0, -190);
        joinRow.AddComponent<Image>().color = new Color(0.07f, 0.12f, 0.22f);

        // Apply 300Mind dark bar to join row bg
        ApplySpr(joinRow.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_5"), Image.Type.Sliced);

        var joinInput = MakeInputField("JoinCodeInput", joinRow, "Enter room code…");
        var jiRT = joinInput.GetComponent<RectTransform>();
        jiRT.anchorMin = new Vector2(0.03f, 0.1f); jiRT.anchorMax = new Vector2(0.72f, 0.9f);
        jiRT.offsetMin = jiRT.offsetMax = Vector2.zero;

        var joinBtn = MakeButton("JoinButton", joinRow, "JOIN", EasyGreen, Color.white, 22);
        ApplySpr(joinBtn.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_16"), Image.Type.Sliced);
        var jbRT = joinBtn.GetComponent<RectTransform>();
        jbRT.anchorMin = new Vector2(0.75f, 0.1f); jbRT.anchorMax = new Vector2(0.97f, 0.9f);
        jbRT.offsetMin = jbRT.offsetMax = Vector2.zero;

        // ── Card scroll (fills space between join row and bottom nav) ─────────
        var scroll   = MakeScrollView("CardScroll", root);
        var scrollRT = scroll.GetComponent<RectTransform>();
        scrollRT.anchorMin = new Vector2(0, 0);
        scrollRT.anchorMax = new Vector2(1, 1);
        scrollRT.offsetMin = new Vector2(0, 100);     // above bottom nav
        scrollRT.offsetMax = new Vector2(0, -262);    // below join row (120+70+72)
        // Transparent background — dark bg from root shows through
        scroll.GetComponent<Image>().color = Color.clear;
        var cardContainer = scroll.transform.Find("Viewport/Content");
        // Card spacing
        var vlg = cardContainer.GetComponent<VerticalLayoutGroup>();
        vlg.spacing = 12;
        vlg.padding = new RectOffset(16, 16, 12, 12);

        // ── Bottom nav bar (100px, anchored bottom) ───────────────────────────
        var botNav   = NewChild("BottomNavBar", root);
        var botRT    = botNav.GetComponent<RectTransform>();
        botRT.anchorMin = new Vector2(0, 0); botRT.anchorMax = new Vector2(1, 0);
        botRT.pivot  = new Vector2(0.5f, 0f);
        botRT.sizeDelta = new Vector2(0, 100);
        botRT.anchoredPosition = Vector2.zero;
        var botNavImg = botNav.AddComponent<Image>();
        ApplySpr(botNavImg, SubSprite(Sheet1, "UI-pack_Sprite_1_55"), Image.Type.Sliced);

        var navGames = MakeButton("NavGames",  botNav, "Games",   ButtonNorm, Accent,     18);
        var navExpl  = MakeButton("NavExplore",botNav, "Explore", ButtonNorm, TextLight,  18);
        var navProf  = MakeButton("NavProfile",botNav, "Profile", ButtonNorm, TextLight,  18);
        // 300Mind dark badge sprite for nav buttons
        ApplySpr(navGames.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_10"), Image.Type.Sliced);
        ApplySpr(navExpl.GetComponent<Image>(),  SubSprite(Sheet2, "UI-pack_Sprite_2_10"), Image.Type.Sliced);
        ApplySpr(navProf.GetComponent<Image>(),  SubSprite(Sheet2, "UI-pack_Sprite_2_10"), Image.Type.Sliced);
        var navBR = navGames.GetComponent<RectTransform>();
        var navER = navExpl.GetComponent<RectTransform>();
        var navPR = navProf.GetComponent<RectTransform>();
        navBR.anchorMin=new Vector2(0.01f,0); navBR.anchorMax=new Vector2(0.33f,1); navBR.offsetMin=navBR.offsetMax=Vector2.zero;
        navER.anchorMin=new Vector2(0.34f,0); navER.anchorMax=new Vector2(0.66f,1); navER.offsetMin=navER.offsetMax=Vector2.zero;
        navPR.anchorMin=new Vector2(0.67f,0); navPR.anchorMax=new Vector2(0.99f,1); navPR.offsetMin=navPR.offsetMax=Vector2.zero;

        // ── Loading + Error ───────────────────────────────────────────────────
        var loading = NewChild("LoadingOverlay", root);
        Stretch(loading.GetComponent<RectTransform>());
        loading.AddComponent<Image>().color = new Color(0, 0, 0, 0.65f);
        var loadLbl = MakeTMP("LoadingLabel", loading, "Loading…", 34, color: Color.white);
        RectAt(loadLbl, 0.5f, 0.5f, 400, 60);
        loading.SetActive(false);

        var err    = MakeTMP("ErrorText", root, "", 22, color: new Color(1f, 0.4f, 0.4f));
        var errRT  = err.GetComponent<RectTransform>();
        errRT.anchorMin = new Vector2(0.05f, 0.35f);
        errRT.anchorMax = new Vector2(0.95f, 0.65f);
        errRT.offsetMin = errRT.offsetMax = Vector2.zero;
        err.GetComponent<TMP_Text>().alignment = TextAlignmentOptions.Center;
        err.GetComponent<TMP_Text>().enableWordWrapping = true;
        err.SetActive(false);

        var retryBtn = MakeButton("RetryButton", root, "Retry", Accent, BgDark, 24);
        RectAt(retryBtn, 0.5f, 0.3f, 200, 64);
        retryBtn.SetActive(false);

        // ── Settings panel (full overlay, hidden) ────────────────────────────
        var settingsPanel = NewChild("SettingsPanel", root);
        Stretch(settingsPanel.GetComponent<RectTransform>());
        settingsPanel.AddComponent<Image>().color = new Color(0f, 0f, 0f, 0.75f);

        var settInner = NewChild("SettingsInner", settingsPanel);
        var siRT = settInner.GetComponent<RectTransform>();
        siRT.anchorMin = new Vector2(0.06f, 0.28f); siRT.anchorMax = new Vector2(0.94f, 0.78f);
        siRT.offsetMin = siRT.offsetMax = Vector2.zero;
        ApplySpr(settInner.AddComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_0"), Image.Type.Sliced);
        if (settInner.GetComponent<Image>().sprite == null) settInner.GetComponent<Image>().color = CardBg;

        var settTitle = MakeTMP("SettingsTitle", settInner, "Settings", 32, bold: true, color: Accent);
        RectAt(settTitle, 0.5f, 0.88f, 400, 48);

        var settClose = MakeButton("SettingsCloseButton", settInner, "✕", ButtonNorm, TextLight, 24);
        RectAt(settClose, 0.88f, 0.88f, 52, 52);

        // Language row
        var langTitle = MakeTMP("LangTitle", settInner, "Language", 22, color: TextLight);
        RectAt(langTitle, 0.22f, 0.66f, 220, 36);

        var langCurrent = MakeTMP("CurrentLangLabel", settInner, "中文", 22, bold: true, color: Accent);
        RectAt(langCurrent, 0.75f, 0.66f, 160, 36);

        var langZh = MakeButton("LangZhButton", settInner, "中文", MedBlue, Color.white, 20);
        RectAt(langZh, 0.28f, 0.50f, 180, 52);
        var langEn = MakeButton("LangEnButton", settInner, "English", ButtonNorm, TextLight, 20);
        RectAt(langEn, 0.72f, 0.50f, 180, 52);

        // Volume row
        var volTitle = MakeTMP("VolumeTitle", settInner, "Volume", 22, color: TextLight);
        RectAt(volTitle, 0.22f, 0.30f, 220, 36);

        var volSliderGO = NewChild("VolumeSlider", settInner);
        var volRT = volSliderGO.GetComponent<RectTransform>();
        volRT.anchorMin = new Vector2(0.08f, 0.14f); volRT.anchorMax = new Vector2(0.92f, 0.22f);
        volRT.offsetMin = volRT.offsetMax = Vector2.zero;
        var volSlider = volSliderGO.AddComponent<Slider>();
        volSlider.minValue = 0f; volSlider.maxValue = 1f; volSlider.value = 1f;
        var volBg = NewChild("Background", volSliderGO); Stretch(volBg.GetComponent<RectTransform>());
        volBg.AddComponent<Image>().color = new Color(0.2f, 0.2f, 0.35f);
        var volFillArea = NewChild("Fill Area", volSliderGO); Stretch(volFillArea.GetComponent<RectTransform>());
        var volFill = NewChild("Fill", volFillArea); Stretch(volFill.GetComponent<RectTransform>());
        volFill.AddComponent<Image>().color = Accent;
        volSlider.fillRect = volFill.GetComponent<RectTransform>();
        var volHandle = NewChild("Handle Slide Area", volSliderGO); Stretch(volHandle.GetComponent<RectTransform>());
        var volHandleDot = NewChild("Handle", volHandle);
        volHandleDot.GetComponent<RectTransform>().sizeDelta = new Vector2(28, 28);
        volHandleDot.AddComponent<Image>().color = Color.white;
        volSlider.handleRect = volHandleDot.GetComponent<RectTransform>();
        settingsPanel.SetActive(false);

        // Wire SettingsController
        var settCtrl = settingsPanel.AddComponent<SettingsController>();
        SetField(settCtrl, "openButton",       settBtn.GetComponent<Button>());
        SetField(settCtrl, "closeButton",       settClose.GetComponent<Button>());
        SetField(settCtrl, "langZhButton",      langZh.GetComponent<Button>());
        SetField(settCtrl, "langEnButton",      langEn.GetComponent<Button>());
        SetField(settCtrl, "volumeSlider",      volSlider);
        SetField(settCtrl, "currentLangLabel",  langCurrent.GetComponent<TMP_Text>());

        // ── Wire BottomNavBar ─────────────────────────────────────────────────
        var navBar   = botNav.AddComponent<BottomNavBar>();
        var soNav    = new SerializedObject(navBar);
        var tabsProp = soNav.FindProperty("tabs");
        if (tabsProp != null)
        {
            tabsProp.arraySize = 3;

            var t0 = tabsProp.GetArrayElementAtIndex(0);  // Games → MainMenu
            SetTabEntry(t0, navGames.GetComponent<Button>(), navGames.GetComponentInChildren<TMP_Text>(), "MainMenu", null);
            var t1 = tabsProp.GetArrayElementAtIndex(1);
            SetTabEntry(t1, navExpl.GetComponent<Button>(), navExpl.GetComponentInChildren<TMP_Text>(), "RoomBrowser", null);
            var t2 = tabsProp.GetArrayElementAtIndex(2);
            SetTabEntry(t2, navProf.GetComponent<Button>(), navProf.GetComponentInChildren<TMP_Text>(), "", settingsPanel);

            soNav.ApplyModifiedPropertiesWithoutUndo();
        }

        // ── Wire RoomBrowserController ────────────────────────────────────────
        var ctrl = root.AddComponent<RoomBrowserController>();
        SetField(ctrl, "tabActiveRooms",   tabAR.GetComponent<Button>());
        SetField(ctrl, "tabTurtleSoup",    tabTS.GetComponent<Button>());
        SetField(ctrl, "tabMurderMystery", tabMM.GetComponent<Button>());
        SetField(ctrl, "joinCodeInput",    joinInput.GetComponent<TMP_InputField>());
        SetField(ctrl, "joinButton",       joinBtn.GetComponent<Button>());
        SetField(ctrl, "cardContainer",    (Transform)cardContainer);
        SetField(ctrl, "scrollRect",       scroll.GetComponent<ScrollRect>());
        SetField(ctrl, "loadingOverlay",   loading);
        SetField(ctrl, "errorText",        err.GetComponent<TMP_Text>());
        SetField(ctrl, "retryButton",      retryBtn.GetComponent<Button>());
        SetField(ctrl, "cardPrefab",       CreateCardPrefab());

        SaveScene(scene, "RoomBrowser");
    }

    static GameObject CreateCardPrefab()
    {
        const string path    = "Assets/Prefabs/RoomCard.prefab";
        const string resPath = "Assets/Resources/RoomCard.prefab";
        if (!AssetDatabase.IsValidFolder("Assets/Prefabs"))
            AssetDatabase.CreateFolder("Assets", "Prefabs");
        if (!AssetDatabase.IsValidFolder("Assets/Resources"))
            AssetDatabase.CreateFolder("Assets", "Resources");

        // ── Card root (horizontal layout) ─────────────────────────────────────
        var card = new GameObject("RoomCard", typeof(RectTransform));
        var cardImg = card.AddComponent<Image>();
        // 300Mind large blue rounded panel as card background (9-sliced)
        ApplySpr(cardImg, SubSprite(Sheet2, "UI-pack_Sprite_2_0"), Image.Type.Sliced);
        if (cardImg.sprite == null) cardImg.color = CardBg;  // fallback color
        var le = card.AddComponent<LayoutElement>();
        le.preferredHeight = 110;
        le.minHeight       = 110;
        le.flexibleWidth   = 1;
        var hlg = card.AddComponent<HorizontalLayoutGroup>();
        hlg.childControlWidth  = true;
        hlg.childControlHeight = true;
        hlg.spacing            = 0;
        hlg.padding            = new RectOffset(0, 0, 0, 0);

        // ── Left: colored icon panel (fixed 88px) ────────────────────────────
        var iconPanel = NewChild("IconPanel", card);
        var iconLE    = iconPanel.AddComponent<LayoutElement>();
        iconLE.preferredWidth  = 88;
        iconLE.minWidth        = 88;
        iconLE.flexibleWidth   = 0;
        iconPanel.AddComponent<Image>().color = MedBlue;  // overridden at runtime by difficulty

        var iconLabel = MakeTMP("IconLabel", iconPanel, "?", 28, bold: true, color: Color.white);
        Stretch(iconLabel.GetComponent<RectTransform>());

        // ── Center: title + badges + description ──────────────────────────────
        var centerPanel = NewChild("CenterPanel", card);
        var centerLE    = centerPanel.AddComponent<LayoutElement>();
        centerLE.flexibleWidth = 1;
        var centerVLG = centerPanel.AddComponent<VerticalLayoutGroup>();
        centerVLG.childControlWidth  = true;
        centerVLG.childControlHeight = false;
        centerVLG.childForceExpandHeight = false;
        centerVLG.spacing  = 2;
        centerVLG.padding  = new RectOffset(10, 6, 8, 6);

        // Title
        var titleGO  = NewChild("TitleLabel", centerPanel);
        var titleLE  = titleGO.AddComponent<LayoutElement>();
        titleLE.preferredHeight = 28;
        var titleTMP = titleGO.AddComponent<TextMeshProUGUI>();
        titleTMP.font      = DefaultFont();
        titleTMP.text      = "Game Title";
        titleTMP.fontSize  = 22;
        titleTMP.fontStyle = FontStyles.Bold;
        titleTMP.color     = TextLight;
        titleTMP.alignment = TextAlignmentOptions.Left;
        titleTMP.enableWordWrapping = false;
        titleTMP.overflowMode = TextOverflowModes.Ellipsis;
        titleTMP.raycastTarget = false;

        // Badges row (difficulty + player count + game type)
        var badgeRow   = NewChild("BadgeRow", centerPanel);
        var badgeRowLE = badgeRow.AddComponent<LayoutElement>();
        badgeRowLE.preferredHeight = 26;
        var badgeHLG   = badgeRow.AddComponent<HorizontalLayoutGroup>();
        badgeHLG.childControlHeight = true;
        badgeHLG.childControlWidth  = false;
        badgeHLG.childForceExpandWidth = false;
        badgeHLG.spacing = 6;

        var diffGO = NewChild("DifficultyBadge", badgeRow);
        diffGO.AddComponent<LayoutElement>().preferredWidth = 90;
        diffGO.AddComponent<Image>().color = MedBlue;
        var diffLbl = NewChild("Label", diffGO);
        Stretch(diffLbl.GetComponent<RectTransform>());
        var diffTMP = diffLbl.AddComponent<TextMeshProUGUI>();
        diffTMP.font = DefaultFont();
        diffTMP.text = "Medium"; diffTMP.fontSize = 16;
        diffTMP.color = Color.white; diffTMP.alignment = TextAlignmentOptions.Center;
        diffTMP.raycastTarget = false;

        var countGO = NewChild("PlayerCountLabel", badgeRow);
        countGO.AddComponent<LayoutElement>().preferredWidth = 56;
        countGO.AddComponent<Image>().color = ButtonNorm;
        var countLbl = NewChild("Label", countGO);
        Stretch(countLbl.GetComponent<RectTransform>());
        var countTMP = countLbl.AddComponent<TextMeshProUGUI>();
        countTMP.font = DefaultFont();
        countTMP.text = "1P"; countTMP.fontSize = 16;
        countTMP.color = TextLight; countTMP.alignment = TextAlignmentOptions.Center;
        countTMP.raycastTarget = false;

        var typeGO  = NewChild("GameTypeLabel", badgeRow);
        typeGO.AddComponent<LayoutElement>().preferredWidth = 130;
        var typeTMP = typeGO.AddComponent<TextMeshProUGUI>();
        typeTMP.font = DefaultFont();
        typeTMP.text = "Turtle Soup"; typeTMP.fontSize = 15;
        typeTMP.color = new Color(0.7f, 0.7f, 0.8f); typeTMP.alignment = TextAlignmentOptions.Left;
        typeTMP.raycastTarget = false;

        // Description — single line, clipped
        var descGO  = NewChild("DescriptionLabel", centerPanel);
        var descLE  = descGO.AddComponent<LayoutElement>();
        descLE.preferredHeight = 24;
        var descTMP = descGO.AddComponent<TextMeshProUGUI>();
        descTMP.font      = DefaultFont();
        descTMP.text      = "A cooperative deduction game.";
        descTMP.fontSize  = 16;
        descTMP.color     = new Color(0.65f, 0.68f, 0.75f);
        descTMP.alignment = TextAlignmentOptions.Left;
        descTMP.enableWordWrapping = false;
        descTMP.overflowMode       = TextOverflowModes.Ellipsis;
        descTMP.maxVisibleLines    = 1;
        descTMP.raycastTarget      = false;

        // Room code (hidden for puzzle cards, shown for active rooms)
        var codeGO  = NewChild("RoomCodeLabel", centerPanel);
        var codeLE  = codeGO.AddComponent<LayoutElement>();
        codeLE.preferredHeight = 20;
        var codeTMP = codeGO.AddComponent<TextMeshProUGUI>();
        codeTMP.font = DefaultFont();
        codeTMP.text = ""; codeTMP.fontSize = 16;
        codeTMP.color = Accent; codeTMP.alignment = TextAlignmentOptions.Left;
        codeTMP.raycastTarget = false;

        // ── Right: PLAY button (fixed 82px) ──────────────────────────────────
        var playPanel  = NewChild("PlayPanel", card);
        var playPanelLE = playPanel.AddComponent<LayoutElement>();
        playPanelLE.preferredWidth = 82;
        playPanelLE.minWidth       = 82;
        playPanelLE.flexibleWidth  = 0;
        playPanel.AddComponent<Image>().color = new Color(0,0,0,0);
        var playPanelVLG = playPanel.AddComponent<VerticalLayoutGroup>();
        playPanelVLG.childAlignment     = TextAnchor.MiddleCenter;
        playPanelVLG.childControlHeight = false;
        playPanelVLG.childControlWidth  = false;

        var playBtn = MakeButton("PlayButton", playPanel, "PLAY", EasyGreen, Color.white, 20);
        ApplySpr(playBtn.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_16"), Image.Type.Sliced);
        var playBtnLE = playBtn.AddComponent<LayoutElement>();
        playBtnLE.preferredWidth  = 70;
        playBtnLE.preferredHeight = 44;
        playBtnLE.ignoreLayout    = false;

        // ── Wire RoomCardItem ─────────────────────────────────────────────────
        card.AddComponent<RoomCardItem>();
        var so = new SerializedObject(card.GetComponent<RoomCardItem>());
        void W(string f, Object v) { var p = so.FindProperty(f); if (p != null) p.objectReferenceValue = v; }
        W("titleLabel",       titleTMP);
        W("gameTypeLabel",    typeTMP);
        W("roomCodeLabel",    codeTMP);
        W("playerCountLabel", countTMP);
        W("difficultyBadge",  diffTMP);
        W("difficultyPanel",  diffGO.GetComponent<Image>());
        W("iconPanel",        iconPanel.GetComponent<Image>());
        W("descriptionLabel", descTMP);
        W("playButton",       playBtn.GetComponent<Button>());
        so.ApplyModifiedPropertiesWithoutUndo();

        var prefab = PrefabUtility.SaveAsPrefabAsset(card, path);
        PrefabUtility.SaveAsPrefabAsset(card, resPath);
        Object.DestroyImmediate(card);
        AssetDatabase.Refresh();
        Debug.Log($"[AI DM Setup] RoomCard prefab → {path}");
        return prefab;
    }

    // ── Chat message prefab ───────────────────────────────────────────────────

    static GameObject CreateChatPrefab(string prefabName, Color bgColor, bool hasBorder)
    {
        if (!AssetDatabase.IsValidFolder("Assets/Prefabs"))
            AssetDatabase.CreateFolder("Assets", "Prefabs");
        if (!AssetDatabase.IsValidFolder("Assets/Prefabs/Chat"))
            AssetDatabase.CreateFolder("Assets/Prefabs", "Chat");

        var root = new GameObject(prefabName, typeof(RectTransform));

        // Background image on root
        var bg = root.AddComponent<Image>();
        bg.color = bgColor;

        // Layout: vertical, auto-height
        var vlg = root.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(hasBorder ? 18 : 14, 14, 10, 10);
        vlg.spacing = 4;
        vlg.childControlWidth    = true;
        vlg.childControlHeight   = true;
        vlg.childForceExpandWidth  = true;
        vlg.childForceExpandHeight = false;
        root.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        root.AddComponent<LayoutElement>().flexibleWidth = 1;

        // Left accent bar (DM positive answer, absolute, outside layout)
        var accentGO = NewChild("LeftAccent", root);
        var accentRT = accentGO.GetComponent<RectTransform>();
        accentRT.anchorMin = Vector2.zero; accentRT.anchorMax = new Vector2(0f, 1f);
        accentRT.pivot = new Vector2(0f, 0.5f);
        accentRT.sizeDelta = new Vector2(4, 0);
        accentRT.anchoredPosition = Vector2.zero;
        var accentImg = accentGO.AddComponent<Image>();
        accentImg.color = ColorPalette.Success;
        accentGO.AddComponent<LayoutElement>().ignoreLayout = true;
        accentGO.SetActive(false);

        // Sender label
        var senderGO  = NewChild("SenderLabel", root);
        senderGO.AddComponent<LayoutElement>().preferredHeight = 22;
        var senderTMP = senderGO.AddComponent<TextMeshProUGUI>();
        senderTMP.font = DefaultFont();
        senderTMP.text = "Player"; senderTMP.fontSize = 15; senderTMP.fontStyle = FontStyles.Bold;
        senderTMP.color = ColorPalette.SenderPlayer;
        senderTMP.alignment = TextAlignmentOptions.Left; senderTMP.raycastTarget = false;

        // Body text (wraps)
        var bodyGO  = NewChild("BodyText", root);
        bodyGO.AddComponent<LayoutElement>().flexibleWidth = 1;
        var bodyTMP = bodyGO.AddComponent<TextMeshProUGUI>();
        bodyTMP.font = DefaultFont();
        bodyTMP.text = "…"; bodyTMP.fontSize = 19;
        bodyTMP.color = ColorPalette.TextPrimary;
        bodyTMP.alignment = TextAlignmentOptions.Left;
        bodyTMP.enableWordWrapping = true; bodyTMP.raycastTarget = false;

        // Judgment badge (hidden by default)
        var badgeGO  = NewChild("JudgmentBadge", root);
        badgeGO.AddComponent<LayoutElement>().preferredHeight = 22;
        var badgeTMP = badgeGO.AddComponent<TextMeshProUGUI>();
        badgeTMP.font = DefaultFont();
        badgeTMP.text = ""; badgeTMP.fontSize = 14;
        badgeTMP.color = ColorPalette.Success;
        badgeTMP.alignment = TextAlignmentOptions.Left; badgeTMP.raycastTarget = false;
        badgeGO.SetActive(false);

        // Wire ChatMessageItem
        var item = root.AddComponent<ChatMessageItem>();
        SetField(item, "senderLabel",    senderTMP);
        SetField(item, "bodyText",       bodyTMP);
        SetField(item, "judgmentBadge",  badgeTMP);
        SetField(item, "leftAccent",     accentImg);
        SetField(item, "background",     bg);

        string path = $"Assets/Prefabs/Chat/{prefabName}.prefab";
        var prefab = PrefabUtility.SaveAsPrefabAsset(root, path);
        Object.DestroyImmediate(root);
        Debug.Log($"[AI DM Setup] Chat prefab → {path}");
        return prefab;
    }

    // ── Clue item prefab ──────────────────────────────────────────────────────

    static GameObject CreateClueItemPrefab()
    {
        if (!AssetDatabase.IsValidFolder("Assets/Prefabs"))
            AssetDatabase.CreateFolder("Assets", "Prefabs");
        if (!AssetDatabase.IsValidFolder("Assets/Prefabs/Chat"))
            AssetDatabase.CreateFolder("Assets/Prefabs", "Chat");

        var root = new GameObject("ClueItem", typeof(RectTransform));
        root.AddComponent<LayoutElement>().flexibleWidth = 1;
        var vlg = root.AddComponent<VerticalLayoutGroup>();
        vlg.padding = new RectOffset(16, 16, 12, 12);
        vlg.spacing = 4;
        vlg.childControlWidth    = true; vlg.childControlHeight   = true;
        vlg.childForceExpandWidth  = true; vlg.childForceExpandHeight = false;
        root.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;
        var rootBg = root.AddComponent<Image>();
        ApplySpr(rootBg, SubSprite(Sheet2, "UI-pack_Sprite_2_4"), Image.Type.Sliced);

        var titleGO  = NewChild("TitleLabel", root);
        titleGO.AddComponent<LayoutElement>().preferredHeight = 28;
        var titleTMP = titleGO.AddComponent<TextMeshProUGUI>();
        titleTMP.font = DefaultFont();
        titleTMP.text = "Clue Title"; titleTMP.fontSize = 20;
        titleTMP.fontStyle = FontStyles.Bold; titleTMP.color = Accent;
        titleTMP.alignment = TextAlignmentOptions.Left; titleTMP.raycastTarget = false;

        var bodyGO  = NewChild("BodyText", root);
        bodyGO.AddComponent<LayoutElement>().flexibleWidth = 1;
        var bodyTMP = bodyGO.AddComponent<TextMeshProUGUI>();
        bodyTMP.font = DefaultFont();
        bodyTMP.text = "Clue description."; bodyTMP.fontSize = 18;
        bodyTMP.color = ColorPalette.TextPrimary;
        bodyTMP.alignment = TextAlignmentOptions.Left;
        bodyTMP.enableWordWrapping = true; bodyTMP.raycastTarget = false;

        string path = "Assets/Prefabs/Chat/ClueItem.prefab";
        var prefab = PrefabUtility.SaveAsPrefabAsset(root, path);
        Object.DestroyImmediate(root);
        Debug.Log("[AI DM Setup] ClueItem prefab → Assets/Prefabs/Chat/ClueItem.prefab");
        return prefab;
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

        // ── Nav Bar (top 80px) ────────────────────────────────────────────────
        var nav   = NewChild("NavBar", content);
        var navRT = nav.GetComponent<RectTransform>();
        navRT.anchorMin = new Vector2(0, 1); navRT.anchorMax = new Vector2(1, 1);
        navRT.pivot = new Vector2(0.5f, 1f);
        navRT.sizeDelta = new Vector2(0, 80);
        navRT.anchoredPosition = Vector2.zero;
        ApplySpr(nav.AddComponent<Image>(), SubSprite(Sheet1, "UI-pack_Sprite_1_35"), Image.Type.Sliced);

        var backBtn  = MakeButton("BackButton",  nav, "<", ButtonNorm, TextLight, 26);
        RectAt(backBtn, 0.07f, 0.5f, 64, 56);
        ApplySpr(backBtn.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_10"), Image.Type.Sliced);

        var dotGO  = NewChild("StatusDot", nav);
        RectAt(dotGO, 0.40f, 0.5f, 14, 14);
        var dotImg = dotGO.AddComponent<Image>();
        dotImg.color = ColorPalette.Danger;

        var titleLbl = MakeTMP("GameTitleLabel", nav, "Game Room", 22, bold: true, color: TextLight);
        RectAt(titleLbl, 0.54f, 0.5f, 340, 46);

        var clueBtn  = MakeButton("CluesButton", nav, "Clues", ButtonNorm, Accent, 18);
        ApplySpr(clueBtn.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_9"), Image.Type.Sliced);
        RectAt(clueBtn, 0.87f, 0.5f, 120, 48);
        var clueCnt  = MakeTMP("ClueCountLabel", clueBtn, "0", 14, color: BgDark);
        RectAt(clueCnt, 0.78f, 0.72f, 22, 22);

        // ── Status Strip (60px below nav, hidden by default) ─────────────────
        var strip   = NewChild("StatusStrip", content);
        var stripRT = strip.GetComponent<RectTransform>();
        stripRT.anchorMin = new Vector2(0, 1); stripRT.anchorMax = new Vector2(1, 1);
        stripRT.pivot = new Vector2(0.5f, 1f);
        stripRT.sizeDelta = new Vector2(0, 60);
        stripRT.anchoredPosition = new Vector2(0, -80);
        ApplySpr(strip.AddComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_5"), Image.Type.Sliced);

        var phaseLbl     = MakeTMP("PhaseLabel",     strip, "Investigation", 18, bold: true, color: Accent);
        RectAt(phaseLbl, 0.16f, 0.55f, 220, 28);
        var phaseDescLbl = MakeTMP("PhaseDescLabel", strip, "Find the truth", 15, color: TextLight);
        RectAt(phaseDescLbl, 0.46f, 0.55f, 300, 26);
        var timerLbl     = MakeTMP("TimerLabel",     strip, "", 18, bold: true, color: Accent);
        RectAt(timerLbl, 0.87f, 0.55f, 100, 28);

        var sliderGO = NewChild("TruthProgressBar", strip);
        var sliderRT = sliderGO.GetComponent<RectTransform>();
        sliderRT.anchorMin = new Vector2(0.02f, 0f); sliderRT.anchorMax = new Vector2(0.98f, 0f);
        sliderRT.pivot = new Vector2(0.5f, 0f);
        sliderRT.sizeDelta = new Vector2(0, 8);
        sliderRT.anchoredPosition = Vector2.zero;
        var slider = sliderGO.AddComponent<Slider>();
        slider.minValue = 0f; slider.maxValue = 1f; slider.value = 0f;
        var sliderBg = NewChild("Background", sliderGO);
        Stretch(sliderBg.GetComponent<RectTransform>());
        sliderBg.AddComponent<Image>().color = new Color(0.2f, 0.2f, 0.35f);
        var fillArea = NewChild("Fill Area", sliderGO);
        Stretch(fillArea.GetComponent<RectTransform>());
        var fill = NewChild("Fill", fillArea);
        Stretch(fill.GetComponent<RectTransform>());
        fill.AddComponent<Image>().color = ColorPalette.Success;
        slider.fillRect = fill.GetComponent<RectTransform>();
        strip.SetActive(false);

        // ── Turn Banner (54px below strip, hidden by default) ─────────────────
        var banner   = NewChild("TurnBanner", content);
        var bannerRT = banner.GetComponent<RectTransform>();
        bannerRT.anchorMin = new Vector2(0, 1); bannerRT.anchorMax = new Vector2(1, 1);
        bannerRT.pivot = new Vector2(0.5f, 1f);
        bannerRT.sizeDelta = new Vector2(0, 54);
        bannerRT.anchoredPosition = new Vector2(0, -140);
        ApplySpr(banner.AddComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_1"), Image.Type.Sliced);
        var bannerTxt = MakeTMP("TurnBannerText", banner, "Your turn! Ask the DM a question", 20, bold: true, color: Color.white);
        Stretch(bannerTxt.GetComponent<RectTransform>());
        banner.SetActive(false);

        // ── Chat Scroll View ──────────────────────────────────────────────────
        var scroll   = MakeScrollView("ChatScrollView", content);
        var scrollRT = scroll.GetComponent<RectTransform>();
        scrollRT.anchorMin = new Vector2(0.01f, 0.10f);
        scrollRT.anchorMax = new Vector2(0.99f, 0.87f);
        scrollRT.offsetMin = scrollRT.offsetMax = Vector2.zero;
        var chatContent = scroll.transform.Find("Viewport/Content");

        // ── Input Row (bottom 10% of screen) ─────────────────────────────────
        var inputRow   = NewChild("InputRow", content);
        var inputRowRT = inputRow.GetComponent<RectTransform>();
        inputRowRT.anchorMin = new Vector2(0.01f, 0.01f);
        inputRowRT.anchorMax = new Vector2(0.99f, 0.10f);
        inputRowRT.offsetMin = inputRowRT.offsetMax = Vector2.zero;
        inputRow.AddComponent<Image>().color = new Color(0, 0, 0, 0);

        var inputField = MakeInputField("InputField", inputRow, "Ask a question…");
        ApplySpr(inputField.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_5"), Image.Type.Sliced);
        var inputRT = inputField.GetComponent<RectTransform>();
        inputRT.anchorMin = new Vector2(0f, 0f); inputRT.anchorMax = new Vector2(0.77f, 1f);
        inputRT.offsetMin = inputRT.offsetMax = Vector2.zero;

        var sendBtn = MakeButton("SendButton", inputRow, "SEND", EasyGreen, Color.white, 20);
        ApplySpr(sendBtn.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_16"), Image.Type.Sliced);
        var sendRT  = sendBtn.GetComponent<RectTransform>();
        sendRT.anchorMin = new Vector2(0.80f, 0.08f); sendRT.anchorMax = new Vector2(1f, 0.92f);
        sendRT.offsetMin = sendRT.offsetMax = Vector2.zero;

        // ── Clue Panel (full-screen overlay, slide-in from right, hidden) ─────
        var cluePanel  = NewChild("CluePanel", content);
        Stretch(cluePanel.GetComponent<RectTransform>());
        cluePanel.AddComponent<Image>().color = new Color(0f, 0f, 0f, 0.80f);

        var cluePanelInner = NewChild("CluePanelInner", cluePanel);
        var cpiRT = cluePanelInner.GetComponent<RectTransform>();
        cpiRT.anchorMin = new Vector2(0.03f, 0.08f); cpiRT.anchorMax = new Vector2(0.97f, 0.94f);
        cpiRT.offsetMin = cpiRT.offsetMax = Vector2.zero;
        ApplySpr(cluePanelInner.AddComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_0"), Image.Type.Sliced);

        var clueHeader   = NewChild("ClueHeader", cluePanelInner);
        var clueHeaderRT = clueHeader.GetComponent<RectTransform>();
        clueHeaderRT.anchorMin = new Vector2(0, 1); clueHeaderRT.anchorMax = new Vector2(1, 1);
        clueHeaderRT.pivot = new Vector2(0.5f, 1f);
        clueHeaderRT.sizeDelta = new Vector2(0, 72);
        clueHeaderRT.anchoredPosition = Vector2.zero;
        clueHeader.AddComponent<Image>().color = new Color(0f, 0f, 0f, 0.15f);
        var clueTitleLbl = MakeTMP("ClueTitle", clueHeader, "Unlocked Clues", 26, bold: true, color: Accent);
        RectAt(clueTitleLbl, 0.38f, 0.5f, 420, 48);
        var clueCloseBtn = MakeButton("CloseButton", clueHeader, "✕", ButtonNorm, TextLight, 22);
        ApplySpr(clueCloseBtn.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_17"), Image.Type.Sliced);
        RectAt(clueCloseBtn, 0.90f, 0.5f, 64, 52);

        var clueScroll   = MakeScrollView("ClueScrollView", cluePanelInner);
        var clueScrollRT = clueScroll.GetComponent<RectTransform>();
        clueScrollRT.anchorMin = new Vector2(0f, 0f); clueScrollRT.anchorMax = new Vector2(1f, 1f);
        clueScrollRT.offsetMin = new Vector2(0f, 0f); clueScrollRT.offsetMax = new Vector2(0f, -72f);
        clueScroll.GetComponent<Image>().color = Color.clear;
        var clueListContainer = clueScroll.transform.Find("Viewport/Content");
        cluePanel.SetActive(false);

        // ── Win Banner (full-screen overlay, hidden) ──────────────────────────
        var winBanner = NewChild("WinBanner", content);
        Stretch(winBanner.GetComponent<RectTransform>());
        ApplySpr(winBanner.AddComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_2"), Image.Type.Simple);
        winBanner.GetComponent<Image>().color = new Color(1, 1, 1, 0.92f);
        var truthLbl  = MakeTMP("TruthRevealText", winBanner, "", 26, color: Color.white);
        var truthRT   = truthLbl.GetComponent<RectTransform>();
        truthRT.anchorMin = new Vector2(0.05f, 0.35f); truthRT.anchorMax = new Vector2(0.95f, 0.80f);
        truthRT.offsetMin = truthRT.offsetMax = Vector2.zero;
        truthLbl.GetComponent<TMP_Text>().alignment = TextAlignmentOptions.Center;
        truthLbl.GetComponent<TMP_Text>().enableWordWrapping = true;
        truthLbl.GetComponent<TMP_Text>().color = BgDark;
        var leaveBtn  = MakeButton("LeaveButton", winBanner, "Leave Room", ButtonNorm, TextLight, 22);
        ApplySpr(leaveBtn.GetComponent<Image>(), SubSprite(Sheet2, "UI-pack_Sprite_2_5"), Image.Type.Sliced);
        RectAt(leaveBtn, 0.5f, 0.18f, 340, 70);
        winBanner.SetActive(false);

        // ── Create chat prefabs ───────────────────────────────────────────────
        var playerPrefab   = CreateChatPrefab("PlayerMessage", new Color(0.10f, 0.12f, 0.28f, 0.9f), false);
        var dmPrefab       = CreateChatPrefab("DmMessage",     new Color(0.086f, 0.082f, 0.118f, 0.5f), true);
        var sysPrefab      = CreateChatPrefab("SystemMessage", Color.clear, false);
        var clueItemPrefab = CreateClueItemPrefab();

        // ── Wire GameRoomController ───────────────────────────────────────────
        var ctrl = content.AddComponent<GameRoomController>();
        SetField(ctrl, "gameTitleLabel",    titleLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "statusDot",         dotImg);
        SetField(ctrl, "backButton",        backBtn.GetComponent<Button>());
        SetField(ctrl, "cluesButton",       clueBtn.GetComponent<Button>());
        SetField(ctrl, "clueCountLabel",    clueCnt.GetComponent<TMP_Text>());
        SetField(ctrl, "phaseLabel",        phaseLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "phaseDescLabel",    phaseDescLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "timerLabel",        timerLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "truthProgressBar",  slider);
        SetField(ctrl, "statusStrip",       strip);
        SetField(ctrl, "turnBanner",        banner);
        SetField(ctrl, "turnBannerText",    bannerTxt.GetComponent<TMP_Text>());
        SetField(ctrl, "chatScrollRect",    scroll.GetComponent<ScrollRect>());
        SetField(ctrl, "chatContent",       (RectTransform)chatContent);
        SetField(ctrl, "playerMsgPrefab",   playerPrefab);
        SetField(ctrl, "dmMsgPrefab",       dmPrefab);
        SetField(ctrl, "systemMsgPrefab",   sysPrefab);
        SetField(ctrl, "inputField",        inputField.GetComponent<TMP_InputField>());
        SetField(ctrl, "sendButton",        sendBtn.GetComponent<Button>());
        SetField(ctrl, "sendButtonBg",      sendBtn.GetComponent<Image>());
        SetField(ctrl, "cluePanel",         cluePanel);
        SetField(ctrl, "clueCloseButton",   clueCloseBtn.GetComponent<Button>());
        SetField(ctrl, "clueListContainer", (Transform)clueListContainer);
        SetField(ctrl, "clueItemPrefab",    clueItemPrefab);
        SetField(ctrl, "winBanner",         winBanner);
        SetField(ctrl, "truthRevealText",   truthLbl.GetComponent<TMP_Text>());
        SetField(ctrl, "leaveButton",       leaveBtn.GetComponent<Button>());

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
        scaler.referenceResolution = new Vector2(1170, 2532);  // iPhone 15/16 portrait
        scaler.matchWidthOrHeight  = 0.5f;  // balance width+height — adapts cleanly across aspect ratios

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

    // Cache so we don't re-load on every MakeTMP call.
    static TMP_FontAsset _font;
    static TMP_FontAsset DefaultFont()
    {
        if (_font != null) return _font;
        // Bundled with TMP Essential Resources
        _font = AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(
            "Assets/TextMesh Pro/Resources/Fonts & Materials/LiberationSans SDF.asset");
        if (_font == null)
            _font = TMP_Settings.defaultFontAsset;
        if (_font == null)
            Debug.LogWarning("[AI DM Setup] TMP default font not found — import TextMesh Pro Essential Resources via Window > TextMeshPro > Import TMP Essential Resources");
        return _font;
    }

    static GameObject MakeTMP(string name, GameObject parent, string text,
        float fontSize = 20, bool bold = false, Color? color = null)
    {
        var go  = NewChild(name, parent);
        var tmp = go.AddComponent<TextMeshProUGUI>();
        tmp.font      = DefaultFont();
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
        ph.font   = DefaultFont();
        ph.text   = placeholder;
        ph.color  = new Color(0.5f, 0.5f, 0.5f);
        ph.fontSize = 20;
        ph.fontStyle = FontStyles.Italic;

        var txtGO = NewChild("Text", textArea);
        Stretch(txtGO.GetComponent<RectTransform>());
        var txt   = txtGO.AddComponent<TextMeshProUGUI>();
        txt.font  = DefaultFont();
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
        // RectMask2D clips by rect bounds — more reliable than Mask+Image(clear)
        viewport.AddComponent<RectMask2D>();

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

    /// Set Slider field (component, not UnityEngine.Object subclass that requires casting).
    static void SetField(Object target, string fieldName, Slider value)
        => SetField(target, fieldName, (Object)value);

    /// Wire one BottomNavBar TabEntry struct via SerializedProperty.
    static void SetTabEntry(SerializedProperty tabProp, Button btn, TMP_Text label, string scene, GameObject panel)
    {
        var p = tabProp.FindPropertyRelative("button");    if (p != null) p.objectReferenceValue = btn;
        var l = tabProp.FindPropertyRelative("label");     if (l != null) l.objectReferenceValue = label;
        var s = tabProp.FindPropertyRelative("sceneName"); if (s != null) s.stringValue = scene;
        var g = tabProp.FindPropertyRelative("localPanel");if (g != null) g.objectReferenceValue = panel;
    }
}
#endif
