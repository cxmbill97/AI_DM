// Mirrors ios/AIDungeonMaster/Lobby/WaitingRoomViewModel.swift + WaitingRoomView.swift.
// Handles lobby ready-up flow: room_snapshot → player_joined/ready → game_started → GameRoom.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using Cysharp.Threading.Tasks;

public class WaitingRoomController : MonoBehaviour
{
    [Header("Room Code")]
    [SerializeField] private TMP_Text  roomCodeLabel;

    [Header("Player Slots")]
    [SerializeField] private Transform      slotsContainer;
    [SerializeField] private GameObject     slotPrefab;

    [Header("Buttons")]
    [SerializeField] private Button    startButton;    // host only
    [SerializeField] private Button    readyButton;    // non-host
    [SerializeField] private TMP_Text  readyButtonLabel;
    [SerializeField] private Button    backButton;
    [SerializeField] private Button    publicToggle;
    [SerializeField] private TMP_Text  publicToggleLabel;

    [Header("Error")]
    [SerializeField] private TMP_Text  errorText;

    // ── State ────────────────────────────────────────────────────────────────

    private string              _roomId;
    private string              _myPlayerId;
    private string              _hostPlayerId;
    private bool                _isReady;
    private bool                _isPublic;
    private bool                _started;
    private int                 _maxPlayers = 4;
    private readonly List<PlayerInfo>    _players   = new();
    private readonly HashSet<string>     _readyIds  = new();

    private bool IsHost   => !string.IsNullOrEmpty(_myPlayerId) && _myPlayerId == _hostPlayerId;
    private bool CanStart => IsHost && _players.Count >= 1;

    // ── Lifecycle ────────────────────────────────────────────────────────────

    private void Start()
    {
        _roomId      = SceneLoader.GetData("roomId")   ?? "";
        _myPlayerId  = JwtDecoder.GetSubject(TokenStore.Instance.LoadToken());

        if (roomCodeLabel) roomCodeLabel.text = _roomId;

        startButton?.onClick.AddListener(OnStartGame);
        readyButton?.onClick.AddListener(OnReady);
        backButton?.onClick.AddListener(OnBack);
        publicToggle?.onClick.AddListener(OnPublicToggle);

        WebSocketManager.Instance.OnMessage += HandleMessage;

        var token = TokenStore.Instance.LoadTokenOrEmpty();
        WebSocketManager.Instance.Connect(_roomId, token);

        RefreshButtons();
    }

    private void OnDestroy()
    {
        if (WebSocketManager.Instance)
        {
            WebSocketManager.Instance.OnMessage -= HandleMessage;
            if (!_started) WebSocketManager.Instance.Disconnect();
        }
    }

    // ── Message handling ──────────────────────────────────────────────────────

    private void HandleMessage(GameMessage msg)
    {
        switch (msg.Type)
        {
            case GameMessageType.RoomSnapshot:
                var snap = msg.RoomSnapshot;
                _players.Clear();
                _players.AddRange(snap.Players);
                _maxPlayers   = snap.MaxPlayers ?? 4;
                _hostPlayerId = snap.HostPlayerId;
                if (!string.IsNullOrEmpty(snap.MyPlayerId)) _myPlayerId = snap.MyPlayerId;
                _readyIds.Clear();
                foreach (var p in snap.Players) if (p.IsReady == true) _readyIds.Add(p.Id);
                if (snap.Started == true) TransitionToGame();
                RefreshSlots();
                RefreshButtons();
                break;

            case GameMessageType.PlayerJoined:
                var pj = msg.PlayerJoined;
                if (!_players.Exists(p => p.Id == pj.PlayerId))
                    _players.Add(new PlayerInfo { Id = pj.PlayerId, Name = pj.PlayerName, IsHost = pj.IsHost, Connected = true, IsReady = false });
                RefreshSlots();
                RefreshButtons();
                break;

            case GameMessageType.PlayerReady:
                var pr = msg.PlayerReady;
                _readyIds.Add(pr.PlayerId);
                for (int i = 0; i < _players.Count; i++)
                    if (_players[i].Id == pr.PlayerId) _players[i] = new PlayerInfo { Id = _players[i].Id, Name = _players[i].Name, IsHost = _players[i].IsHost, Connected = _players[i].Connected, IsReady = true };
                RefreshSlots();
                break;

            case GameMessageType.GameStarted:
                TransitionToGame();
                break;

            case GameMessageType.Error:
                ShowError(msg.Error.Message);
                break;
        }
    }

    // ── Button handlers ───────────────────────────────────────────────────────

    private void OnStartGame()
    {
        if (!CanStart) return;
        APIManager.Instance.StartRoom(_roomId)
            .ContinueWith(() => { }, ex => ShowError(ex.Message))
            .Forget();
    }

    private void OnReady()
    {
        if (_isReady) return;
        _isReady = true;
        RefreshButtons();
        WebSocketManager.Instance.Send(new ClientMessage("ready"));
    }

    private void OnBack()
    {
        WebSocketManager.Instance.Disconnect();
        SceneLoader.LoadScene("RoomBrowser");
    }

    private void OnPublicToggle()
    {
        _isPublic = !_isPublic;
        APIManager.Instance.PatchRoom(_roomId, isPublic: _isPublic)
            .ContinueWith(() => RefreshButtons(), ex => ShowError(ex.Message))
            .Forget();
    }

    private void TransitionToGame()
    {
        if (_started) return;
        _started = true;
        // Disconnect lobby WS before game WS connects (mirrors WaitingRoomViewModel.disconnect())
        WebSocketManager.Instance.Disconnect();
        SceneLoader.LoadGameRoom(_roomId);
    }

    // ── UI refresh ────────────────────────────────────────────────────────────

    private void RefreshSlots()
    {
        if (slotsContainer == null || slotPrefab == null) return;

        // Destroy old slots
        foreach (Transform c in slotsContainer) Destroy(c.gameObject);

        for (int i = 0; i < _maxPlayers; i++)
        {
            var go   = Instantiate(slotPrefab, slotsContainer);
            var slot = go.GetComponent<PlayerSlotItem>();
            if (slot == null) continue;
            if (i < _players.Count)
                slot.SetPlayer(_players[i], _readyIds.Contains(_players[i].Id));
            else
                slot.SetEmpty();
        }
    }

    private void RefreshButtons()
    {
        startButton?.gameObject.SetActive(IsHost);
        readyButton?.gameObject.SetActive(!IsHost);

        if (startButton)  startButton.interactable = CanStart;
        if (readyButton)  readyButton.interactable  = !_isReady;
        if (readyButtonLabel) readyButtonLabel.text = _isReady ? "Ready!" : "I'm Ready";
        if (publicToggleLabel) publicToggleLabel.text = _isPublic ? "🌐 Public Room" : "🔒 Private Room";
    }

    private void ShowError(string msg)
    {
        if (errorText) { errorText.text = msg; errorText.gameObject.SetActive(true); }
    }
}
