// Mirrors ios/AIDungeonMaster/Room/RoomViewModel.swift — all 12 message cases,
// streaming accumulation, surfaceShown guard, turn mode, truth progress.
// Attach to the GameRoom scene root Canvas.
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using Cysharp.Threading.Tasks;

public class GameRoomController : MonoBehaviour
{
    [Header("Nav Bar")]
    [SerializeField] private TMP_Text   gameTitleLabel;
    [SerializeField] private Image      statusDot;
    [SerializeField] private Button     backButton;
    [SerializeField] private Button     cluesButton;
    [SerializeField] private TMP_Text   clueCountLabel;

    [Header("Status Strip")]
    [SerializeField] private TMP_Text   phaseLabel;
    [SerializeField] private TMP_Text   phaseDescLabel;
    [SerializeField] private TMP_Text   timerLabel;
    [SerializeField] private Slider     truthProgressBar;
    [SerializeField] private GameObject statusStrip;

    [Header("Turn Banner")]
    [SerializeField] private GameObject turnBanner;
    [SerializeField] private TMP_Text   turnBannerText;

    [Header("Chat")]
    [SerializeField] private ScrollRect      chatScrollRect;
    [SerializeField] private RectTransform   chatContent;
    [SerializeField] private GameObject      playerMsgPrefab;
    [SerializeField] private GameObject      dmMsgPrefab;
    [SerializeField] private GameObject      systemMsgPrefab;

    [Header("Input")]
    [SerializeField] private TMP_InputField  inputField;
    [SerializeField] private Button          sendButton;
    [SerializeField] private Image           sendButtonBg;

    [Header("Clue Panel")]
    [SerializeField] private GameObject      cluePanel;
    [SerializeField] private Button          clueCloseButton;
    [SerializeField] private Transform       clueListContainer;
    [SerializeField] private GameObject      clueItemPrefab;

    [Header("Win Banner")]
    [SerializeField] private GameObject winBanner;
    [SerializeField] private TMP_Text   truthRevealText;
    [SerializeField] private Button     leaveButton;

    [Header("Bottom Nav")]
    [SerializeField] private BottomNavBar    bottomNavBar;

    // ── State ────────────────────────────────────────────────────────────────

    private string     _roomId;
    private bool       _surfaceShown;
    private bool       _isSending;
    private bool       _gameWon;
    private float      _truthProgress;
    private string     _phase, _phaseDesc;
    private bool       _turnMode;
    private string     _currentTurnPlayerId, _myPlayerId;

    private readonly List<CluePayload>     _clues    = new();
    private readonly Dictionary<string, ChatMessageItem> _streamingItems = new(); // streamId → item

    // ── Lifecycle ────────────────────────────────────────────────────────────

    private void Start()
    {
        _roomId = SceneLoader.GetData("roomId") ?? "";

        sendButton?.onClick.AddListener(OnSend);
        backButton?.onClick.AddListener(OnBack);
        leaveButton?.onClick.AddListener(OnBack);
        if (cluePanel) cluesButton?.onClick.AddListener(() => cluePanel.SetActive(true));
        if (cluePanel) clueCloseButton?.onClick.AddListener(() => cluePanel.SetActive(false));
        inputField?.onValueChanged.AddListener(_ => RefreshSendButton());

        if (cluePanel) cluePanel.SetActive(false);
        winBanner?.SetActive(false);
        turnBanner?.SetActive(false);
        statusStrip?.SetActive(false);
        cluesButton?.gameObject.SetActive(false);

        bottomNavBar?.Hide();

        WebSocketManager.Instance.OnMessage    += HandleMessage;
        WebSocketManager.Instance.OnConnected  += OnWsConnected;
        WebSocketManager.Instance.OnDisconnected += OnWsDisconnected;

        var token = TokenStore.Instance.LoadTokenOrEmpty();
        WebSocketManager.Instance.Connect(_roomId, token);

        RefreshSendButton();
    }

    private void OnDestroy()
    {
        if (WebSocketManager.Instance)
        {
            WebSocketManager.Instance.OnMessage      -= HandleMessage;
            WebSocketManager.Instance.OnConnected    -= OnWsConnected;
            WebSocketManager.Instance.OnDisconnected -= OnWsDisconnected;
            WebSocketManager.Instance.Disconnect();
        }
        bottomNavBar?.Show();
    }

    // ── WS event handlers ────────────────────────────────────────────────────

    private void OnWsConnected()
    {
        if (statusDot) statusDot.color = ColorPalette.Success;
    }

    private void OnWsDisconnected()
    {
        if (statusDot) statusDot.color = ColorPalette.Danger;
    }

    private void HandleMessage(GameMessage msg)
    {
        switch (msg.Type)
        {
            case GameMessageType.PlayerMessage:
                var pm = msg.PlayerMessage;
                bool isEmote = IsEmote(pm.Text);
                AppendChat(pm.PlayerName, pm.Text, isEmote ? ChatMsgType.Emote : ChatMsgType.Player);
                break;

            case GameMessageType.DmResponse:
                var dr = msg.DmResponse;
                AppendChat("DM", dr.Response, ChatMsgType.Dm, dr.Judgment);
                SetTruthProgress(dr.TruthProgress);
                if (dr.ClueUnlocked != null) AddClue(dr.ClueUnlocked);
                if (!string.IsNullOrEmpty(dr.Truth)) Resolve(dr.Truth);
                break;

            case GameMessageType.DmStreamStart:
                var ss = msg.DmStreamStart;
                var streamItem = AppendChat("DM", "", ChatMsgType.Dm);
                if (streamItem != null) { streamItem.IsStreaming = true; streamItem.StreamId = ss.StreamId; _streamingItems[ss.StreamId] = streamItem; }
                break;

            case GameMessageType.DmStreamChunk:
                var sc = msg.DmStreamChunk;
                if (_streamingItems.TryGetValue(sc.StreamId, out var chunkItem)) chunkItem.AppendChunk(sc.Text);
                break;

            case GameMessageType.DmStreamEnd:
                var se = msg.DmStreamEnd;
                string sid = se.StreamId ?? "";
                if (_streamingItems.TryGetValue(sid, out var endItem))
                {
                    endItem.FinaliseStream(se.Response, se.Judgment);
                    _streamingItems.Remove(sid);
                }
                else
                {
                    // Fallback if start/chunk were missed
                    AppendChat("DM", se.Response ?? "", ChatMsgType.Dm, se.Judgment);
                }
                if (se.TruthProgress.HasValue) SetTruthProgress(se.TruthProgress.Value);
                if (se.ClueUnlocked != null)   AddClue(se.ClueUnlocked);
                if (!string.IsNullOrEmpty(se.Truth)) Resolve(se.Truth);
                break;

            case GameMessageType.System:
                AppendChat("System", msg.System.Text, ChatMsgType.System);
                break;

            case GameMessageType.RoomSnapshot:
                ApplySnapshot(msg.RoomSnapshot);
                break;

            case GameMessageType.TurnChange:
                var tc = msg.TurnChange;
                _currentTurnPlayerId = tc.PlayerId;
                AppendChat("System", tc.Text, ChatMsgType.System);
                RefreshTurnBanner();
                break;

            case GameMessageType.Error:
                AppendChat("System", $"⚠️ {msg.Error.Message}", ChatMsgType.Error);
                break;
        }
    }

    // ── Snapshot ─────────────────────────────────────────────────────────────

    private void ApplySnapshot(RoomSnapshotPayload snap)
    {
        if (!string.IsNullOrEmpty(snap.Title) && gameTitleLabel) gameTitleLabel.text = snap.Title;

        _phase    = snap.Phase ?? snap.CurrentPhase ?? "";
        _phaseDesc= snap.PhaseDescription ?? "";
        _turnMode = snap.TurnMode ?? false;
        _currentTurnPlayerId = snap.CurrentTurnPlayerId;
        if (!string.IsNullOrEmpty(snap.MyPlayerId)) _myPlayerId = snap.MyPlayerId;

        if (snap.Clues != null) foreach (var c in snap.Clues) { if (!_clues.Exists(x => x.Id == c.Id)) AddClue(c); }

        if (!_surfaceShown && !string.IsNullOrEmpty(snap.Surface))
        {
            _surfaceShown = true;
            var title = string.IsNullOrEmpty(snap.Title) ? "Mystery" : snap.Title;
            InsertChatAtTop(title, snap.Surface, ChatMsgType.Dm);
        }

        RefreshStatusStrip();
        RefreshTurnBanner();
    }

    // ── Chat helpers ──────────────────────────────────────────────────────────

    private ChatMessageItem AppendChat(string sender, string text, ChatMsgType type, string judgment = null)
    {
        GameObject prefab = type switch
        {
            ChatMsgType.Dm     => dmMsgPrefab,
            ChatMsgType.System => systemMsgPrefab,
            ChatMsgType.Error  => systemMsgPrefab,
            _                  => playerMsgPrefab,
        };
        if (prefab == null || chatContent == null) return null;

        var go   = Instantiate(prefab, chatContent);
        var item = go.GetComponent<ChatMessageItem>();
        item?.SetData(sender, text, type, judgment);

        ScrollToBottomNextFrame().Forget();
        return item;
    }

    private void InsertChatAtTop(string sender, string text, ChatMsgType type)
    {
        if (dmMsgPrefab == null || chatContent == null) return;
        var go   = Instantiate(dmMsgPrefab, chatContent);
        go.transform.SetAsFirstSibling();
        go.GetComponent<ChatMessageItem>()?.SetData(sender, text, type);
    }

    private async UniTaskVoid ScrollToBottomNextFrame()
    {
        await UniTask.Yield();
        if (chatScrollRect) chatScrollRect.verticalNormalizedPosition = 0f;
    }

    // ── Truth / Clues ─────────────────────────────────────────────────────────

    private void SetTruthProgress(float progress)
    {
        _truthProgress = progress;
        if (truthProgressBar) truthProgressBar.value = progress;
        RefreshStatusStrip();
    }

    private void AddClue(CluePayload clue)
    {
        if (_clues.Exists(c => c.Id == clue.Id)) return;
        _clues.Add(clue);
        AppendChat("System", $"🔑 Clue unlocked: {clue.Title}", ChatMsgType.System);

        cluesButton?.gameObject.SetActive(true);
        if (clueCountLabel) clueCountLabel.text = _clues.Count.ToString();

        if (clueItemPrefab != null && clueListContainer != null)
        {
            var go   = Instantiate(clueItemPrefab, clueListContainer);
            var lbl  = go.GetComponentInChildren<TMP_Text>();
            if (lbl) lbl.text = $"<b>{clue.Title}</b>\n{clue.Content}";
        }
    }

    private void Resolve(string truth)
    {
        _gameWon = true;
        _ = _gameWon;   // suppress CS0414
        winBanner?.SetActive(true);
        if (truthRevealText) truthRevealText.text = truth;
        inputField?.gameObject.SetActive(false);
        sendButton?.gameObject.SetActive(false);
        APIManager.Instance.CompleteRoom(_roomId, "success").Forget();
    }

    // ── Status strip / Turn banner ────────────────────────────────────────────

    private void RefreshStatusStrip()
    {
        bool show = !string.IsNullOrEmpty(_phase) || _truthProgress > 0;
        statusStrip?.SetActive(show);
        if (phaseLabel)    phaseLabel.text    = _phase.Replace('_', ' ');
        if (phaseDescLabel)phaseDescLabel.text = _phaseDesc;
    }

    private void RefreshTurnBanner()
    {
        if (!_turnMode || string.IsNullOrEmpty(_currentTurnPlayerId)) { turnBanner?.SetActive(false); return; }
        bool isMe = _currentTurnPlayerId == _myPlayerId;
        turnBanner?.SetActive(true);
        if (turnBannerText) turnBannerText.text = isMe ? "Your turn! Ask the DM a question" : $"{_currentTurnPlayerId}'s turn";
    }

    // ── Input ─────────────────────────────────────────────────────────────────

    private void OnSend()
    {
        if (_isSending || inputField == null) return;
        var text = (inputField.text ?? "").Trim();
        if (string.IsNullOrEmpty(text)) return;

        inputField.text = "";
        _isSending      = true;
        RefreshSendButton();
        WebSocketManager.Instance.Send(new ClientMessage("chat", text));
        _isSending = false;
        RefreshSendButton();
    }

    private void RefreshSendButton()
    {
        bool canSend = inputField != null && (inputField.text ?? "").Trim().Length > 0 && !_isSending;
        if (sendButton)   sendButton.interactable = canSend;
        if (sendButtonBg) sendButtonBg.color      = canSend ? ColorPalette.Gold : ColorPalette.Border;
    }

    private void OnBack()
    {
        SceneLoader.LoadScene("MainMenu");
    }

    // ── Utilities ─────────────────────────────────────────────────────────────

    private static bool IsEmote(string text)
    {
        if (string.IsNullOrEmpty(text)) return false;
        foreach (var c in text)
            if (!char.IsHighSurrogate(c) && !char.IsLowSurrogate(c) && c < 0x2600) return false;
        return true;
    }
}
