// Mirrors ios/AIDungeonMaster/Explore/ExploreView.swift + Lobby/LobbyView.swift.
// Displays active rooms, puzzles, scripts and lets users create/join a game.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using Cysharp.Threading.Tasks;

public class RoomBrowserController : MonoBehaviour
{
    [Header("Tabs")]
    [SerializeField] private Button   tabActiveRooms;
    [SerializeField] private Button   tabTurtleSoup;
    [SerializeField] private Button   tabMurderMystery;

    [Header("Search / Join")]
    [SerializeField] private TMP_InputField joinCodeInput;
    [SerializeField] private Button         joinButton;

    [Header("Card List")]
    [SerializeField] private Transform    cardContainer;
    [SerializeField] private GameObject   cardPrefab;
    [SerializeField] private ScrollRect   scrollRect;

    [Header("State")]
    [SerializeField] private GameObject   loadingOverlay;
    [SerializeField] private TMP_Text     errorText;
    [SerializeField] private Button       retryButton;

    private const int PageSize = 20;

    // Read language preference set in SettingsController
    private static string Lang => PlayerPrefs.GetString("lang", "zh");

    private enum Tab { ActiveRooms, TurtleSoup, MurderMystery }
    private Tab _currentTab = Tab.TurtleSoup;

    private List<ActiveRoom>    _activeRooms  = new();
    private List<PuzzleSummary> _puzzles      = new();
    private List<ScriptSummary> _scripts      = new();

    // Pagination state per content tab
    private int  _puzzlePage,  _scriptPage;
    private bool _puzzlesDone, _scriptsDone;
    private bool _isLoadingMore;

    private void Start()
    {
        tabActiveRooms?.onClick.AddListener(()    => SwitchTab(Tab.ActiveRooms));
        tabTurtleSoup?.onClick.AddListener(()     => SwitchTab(Tab.TurtleSoup));
        tabMurderMystery?.onClick.AddListener(()  => SwitchTab(Tab.MurderMystery));
        joinButton?.onClick.AddListener(OnJoinByCode);
        retryButton?.onClick.AddListener(() => Refresh().Forget());
        if (scrollRect) scrollRect.onValueChanged.AddListener(OnScroll);
        HideError();
        Refresh().Forget();
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    private async UniTaskVoid Refresh()
    {
        // Reset pagination and reload from page 0
        _puzzles.Clear(); _puzzlePage = 0; _puzzlesDone = false;
        _scripts.Clear(); _scriptPage = 0; _scriptsDone = false;
        _activeRooms.Clear();

        SetLoading(true);
        HideError();

        if (APIManager.Instance == null)
        {
            SetLoading(false);
            ShowError("Services not initialised.\nPlease start from the Boot scene.");
            return;
        }

        try
        {
            // Always load active rooms in full (usually < 20)
            _activeRooms = await APIManager.Instance.GetActiveRooms();

            // Load first page for current tab
            await LoadNextPage(_currentTab);
            Debug.Log($"[RoomBrowser] Loaded {_puzzles.Count} puzzles, {_scripts.Count} scripts, {_activeRooms.Count} active rooms");
        }
        catch (System.Exception ex)
        {
            Debug.LogError($"[RoomBrowser] Load failed: {ex.Message}");
            ShowError($"Cannot reach backend ({AppConfig.BaseURL})\n{ex.Message}");
        }
        finally { SetLoading(false); }

        RebuildCards();
    }

    private async UniTask LoadNextPage(Tab tab)
    {
        if (tab == Tab.TurtleSoup && !_puzzlesDone)
        {
            var page = await APIManager.Instance.ListPuzzles(lang: Lang, skip: _puzzlePage * PageSize, limit: PageSize);
            _puzzles.AddRange(page);
            _puzzlePage++;
            if (page.Count < PageSize) _puzzlesDone = true;
        }
        else if (tab == Tab.MurderMystery && !_scriptsDone)
        {
            var page = await APIManager.Instance.ListScripts(lang: Lang, skip: _scriptPage * PageSize, limit: PageSize);
            _scripts.AddRange(page);
            _scriptPage++;
            if (page.Count < PageSize) _scriptsDone = true;
        }
    }

    private void OnScroll(Vector2 pos)
    {
        // pos.y = 0 means scrolled to bottom
        if (pos.y > 0.1f || _isLoadingMore) return;
        bool moreAvailable = _currentTab == Tab.TurtleSoup   && !_puzzlesDone
                          || _currentTab == Tab.MurderMystery && !_scriptsDone;
        if (moreAvailable) LoadMore().Forget();
    }

    private async UniTaskVoid LoadMore()
    {
        _isLoadingMore = true;
        try
        {
            int countBefore = _currentTab == Tab.TurtleSoup ? _puzzles.Count : _scripts.Count;
            await LoadNextPage(_currentTab);
            int countAfter  = _currentTab == Tab.TurtleSoup ? _puzzles.Count : _scripts.Count;
            // Append only the new cards rather than rebuilding the whole list
            AppendNewCards(countBefore, countAfter);
        }
        catch (System.Exception ex) { Debug.LogWarning($"[RoomBrowser] Load more failed: {ex.Message}"); }
        finally { _isLoadingMore = false; }
    }

    private void SwitchTab(Tab tab)
    {
        _currentTab = tab;
        // If we haven't loaded any data for this tab yet, fetch first page now
        bool needsLoad = (tab == Tab.TurtleSoup    && _puzzles.Count == 0 && !_puzzlesDone)
                      || (tab == Tab.MurderMystery && _scripts.Count == 0 && !_scriptsDone);
        if (needsLoad)
            LoadAndRebuild().Forget();
        else
            RebuildCards();
    }

    private async UniTaskVoid LoadAndRebuild()
    {
        SetLoading(true);
        try   { await LoadNextPage(_currentTab); }
        catch (System.Exception ex) { ShowError(ex.Message); }
        finally { SetLoading(false); }
        RebuildCards();
    }

    private void RebuildCards()
    {
        // Fallback: load prefab from Resources if Inspector didn't wire it
        if (cardPrefab == null)
        {
            cardPrefab = Resources.Load<GameObject>("RoomCard");
            if (cardPrefab == null)
            {
                Debug.LogError("[RoomBrowser] cardPrefab is null and not found in Resources/RoomCard. Re-run AI DM → Setup RoomBrowser.");
                return;
            }
        }

        // Auto-find the scroll content if not wired
        if (cardContainer == null)
        {
            var scroll = GetComponentInChildren<ScrollRect>();
            if (scroll != null) cardContainer = scroll.content;
            if (cardContainer == null)
            {
                Debug.LogError("[RoomBrowser] cardContainer is null. Re-run AI DM → Setup RoomBrowser.");
                return;
            }
        }

        // Clear existing cards
        for (int i = cardContainer.childCount - 1; i >= 0; i--)
            Destroy(cardContainer.GetChild(i).gameObject);

        switch (_currentTab)
        {
            case Tab.ActiveRooms:
                if (_activeRooms.Count == 0)
                    SpawnEmptyLabel("No active rooms. Create one from Turtle Soup or Murder Mystery!");
                foreach (var r in _activeRooms)
                {
                    var go   = Instantiate(cardPrefab, cardContainer);
                    var card = go.GetComponent<RoomCardItem>();
                    var room = r;
                    card?.SetData(room, () => JoinRoom(room.RoomId));
                }
                break;

            case Tab.TurtleSoup:
                foreach (var p in _puzzles)
                {
                    var go     = Instantiate(cardPrefab, cardContainer);
                    var card   = go.GetComponent<RoomCardItem>();
                    var puzzle = p;
                    card?.SetData(puzzle, () => CreateAndJoin("turtle_soup", puzzleId: puzzle.Id));
                }
                Debug.Log($"[RoomBrowser] Spawned {_puzzles.Count} puzzle cards into {cardContainer.name}");
                break;

            case Tab.MurderMystery:
                foreach (var s in _scripts)
                {
                    var go     = Instantiate(cardPrefab, cardContainer);
                    var card   = go.GetComponent<RoomCardItem>();
                    var script = s;
                    card?.SetData(script, () => CreateAndJoin("murder_mystery", scriptId: script.Id));
                }
                Debug.Log($"[RoomBrowser] Spawned {_scripts.Count} script cards into {cardContainer.name}");
                break;
        }

        // ContentSizeFitter + VerticalLayoutGroup won't recalculate until the next frame.
        // Force it: rebuild content, then the entire canvas tree.
        var contentRT = cardContainer as RectTransform ?? cardContainer.GetComponent<RectTransform>();
        UnityEngine.UI.LayoutRebuilder.ForceRebuildLayoutImmediate(contentRT);
        Canvas.ForceUpdateCanvases();
        UnityEngine.UI.LayoutRebuilder.ForceRebuildLayoutImmediate(contentRT);

        // Belt-and-suspenders: also rebuild after one frame in case the above isn't enough
        StartCoroutine(RebuildAfterFrame(contentRT));
    }

    // Append only cards at indices [from, to) without clearing existing ones
    private void AppendNewCards(int from, int to)
    {
        if (cardPrefab == null || cardContainer == null) return;
        var list = _currentTab == Tab.TurtleSoup
            ? _puzzles.GetRange(from, to - from).ConvertAll(p => (object)p)
            : _scripts.GetRange(from, to - from).ConvertAll(s => (object)s);

        foreach (var item in list)
        {
            var go   = Instantiate(cardPrefab, cardContainer);
            var card = go.GetComponent<RoomCardItem>();
            if (item is PuzzleSummary p) { var pp = p; card?.SetData(pp, () => CreateAndJoin("turtle_soup",   puzzleId: pp.Id)); }
            if (item is ScriptSummary s) { var ss = s; card?.SetData(ss, () => CreateAndJoin("murder_mystery", scriptId: ss.Id)); }
        }

        var rt = cardContainer as RectTransform ?? cardContainer.GetComponent<RectTransform>();
        UnityEngine.UI.LayoutRebuilder.ForceRebuildLayoutImmediate(rt);
    }

    private System.Collections.IEnumerator RebuildAfterFrame(RectTransform rt)
    {
        yield return null;
        UnityEngine.UI.LayoutRebuilder.ForceRebuildLayoutImmediate(rt);
        Canvas.ForceUpdateCanvases();
        if (scrollRect != null) scrollRect.verticalNormalizedPosition = 1f;
        Debug.Log($"[RoomBrowser] Content size after rebuild: {rt.rect.width}x{rt.rect.height}");
    }

    private void SpawnEmptyLabel(string msg)
    {
        var go  = new GameObject("EmptyLabel", typeof(RectTransform));
        go.transform.SetParent(cardContainer, false);
        var le  = go.AddComponent<UnityEngine.UI.LayoutElement>();
        le.preferredHeight = 80;
        le.flexibleWidth   = 1;
        var tmp = go.AddComponent<TMPro.TextMeshProUGUI>();
        // Assign the default TMP font — required when creating TMP components at runtime
        tmp.font      = TMPro.TMP_Settings.defaultFontAsset
                        ?? Resources.Load<TMPro.TMP_FontAsset>("Fonts & Materials/LiberationSans SDF");
        tmp.text      = msg;
        tmp.fontSize  = 18;
        tmp.color     = new Color(0.6f, 0.55f, 0.5f);
        tmp.alignment = TMPro.TextAlignmentOptions.Center;
    }

    // ── Actions ───────────────────────────────────────────────────────────────

    private void OnJoinByCode()
    {
        var code = (joinCodeInput?.text ?? "").Trim().ToUpper();
        if (string.IsNullOrEmpty(code)) return;
        joinCodeInput.text = "";
        JoinRoom(code);
    }

    private void JoinRoom(string roomId)
        => SceneLoader.LoadWaitingRoom(roomId);

    private void CreateAndJoin(string gameType, string puzzleId = null, string scriptId = null)
    {
        SetLoading(true);
        DoCreateAndJoin(gameType, puzzleId, scriptId).Forget();
    }

    private async UniTaskVoid DoCreateAndJoin(string gameType, string puzzleId, string scriptId)
    {
        try
        {
            var resp = await APIManager.Instance.CreateRoom(gameType, puzzleId: puzzleId, scriptId: scriptId);
            SetLoading(false);
            SceneLoader.LoadWaitingRoom(resp.RoomId, gameType);
        }
        catch (System.Exception ex) { SetLoading(false); ShowError(ex.Message); }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void SetLoading(bool on) => loadingOverlay?.SetActive(on);

    private void ShowError(string msg)
    {
        if (errorText)
        {
            errorText.text = msg;
            errorText.gameObject.SetActive(true);
        }
        retryButton?.gameObject.SetActive(true);
    }

    private void HideError()
    {
        if (errorText) errorText.gameObject.SetActive(false);
        retryButton?.gameObject.SetActive(false);
    }
}
