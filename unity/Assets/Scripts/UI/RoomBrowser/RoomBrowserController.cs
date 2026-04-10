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

    private enum Tab { ActiveRooms, TurtleSoup, MurderMystery }
    private Tab _currentTab = Tab.TurtleSoup;

    private List<ActiveRoom>    _activeRooms  = new();
    private List<PuzzleSummary> _puzzles      = new();
    private List<ScriptSummary> _scripts      = new();

    private void Start()
    {
        tabActiveRooms?.onClick.AddListener(()    => SwitchTab(Tab.ActiveRooms));
        tabTurtleSoup?.onClick.AddListener(()     => SwitchTab(Tab.TurtleSoup));
        tabMurderMystery?.onClick.AddListener(()  => SwitchTab(Tab.MurderMystery));
        joinButton?.onClick.AddListener(OnJoinByCode);
        errorText?.gameObject.SetActive(false);
        LoadAll().Forget();
    }

    // ── Data loading ──────────────────────────────────────────────────────────

    private async UniTaskVoid LoadAll()
    {
        SetLoading(true);
        try
        {
            _activeRooms = await APIManager.Instance.GetActiveRooms();
            _puzzles     = await APIManager.Instance.ListPuzzles();
            _scripts     = await APIManager.Instance.ListScripts();
        }
        catch (System.Exception ex) { ShowError(ex.Message); }
        finally { SetLoading(false); }

        RebuildCards();
    }

    private void SwitchTab(Tab tab) { _currentTab = tab; RebuildCards(); }

    private void RebuildCards()
    {
        foreach (Transform c in cardContainer) Destroy(c.gameObject);

        switch (_currentTab)
        {
            case Tab.ActiveRooms:
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
                break;

            case Tab.MurderMystery:
                foreach (var s in _scripts)
                {
                    var go     = Instantiate(cardPrefab, cardContainer);
                    var card   = go.GetComponent<RoomCardItem>();
                    var script = s;
                    card?.SetData(script, () => CreateAndJoin("murder_mystery", scriptId: script.Id));
                }
                break;
        }
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
        APIManager.Instance.CreateRoom(gameType, puzzleId: puzzleId, scriptId: scriptId)
            .ContinueWith(resp => { SetLoading(false); SceneLoader.LoadWaitingRoom(resp.RoomId, gameType); },
                          ex   => { SetLoading(false); ShowError(ex.Message); })
            .Forget();
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void SetLoading(bool on) => loadingOverlay?.SetActive(on);
    private void ShowError(string msg)
    {
        if (errorText) { errorText.text = msg; errorText.gameObject.SetActive(true); }
    }
}
