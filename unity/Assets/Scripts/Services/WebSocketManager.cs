// Mirrors ios/AIDungeonMaster/Services/WebSocketService.swift exactly.
// Key behaviours replicated:
//   - Connection ID rotation prevents stale receive callbacks
//   - Ping every 20 seconds (keep-alive)
//   - Up to 3 reconnect retries with 1.5s * retry delay
//   - Double-connect guard (same room)
//   - DispatchMessageQueue() called in Update() (NativeWebSocket requirement)
using System;
using System.Collections;
using System.Text;
using UnityEngine;
using NativeWebSocket;
using Cysharp.Threading.Tasks;

public class WebSocketManager : MonoBehaviour
{
    public static WebSocketManager Instance { get; private set; }

    public bool IsConnected   { get; private set; }
    public bool IsReconnecting{ get; private set; }

    // C# events replace Swift's AsyncStream<GameMessage>
    public event Action<GameMessage> OnMessage;
    public event Action              OnConnected;
    public event Action              OnDisconnected;

    private WebSocket  _ws;
    private string     _roomId  = "";
    private string     _token   = "";
    private int        _retryCount;
    private const int  MaxRetries = 3;
    private Coroutine  _pingCoroutine;
    private int        _connId;          // Rotation ID — stale listeners ignore mismatched IDs

    private void Awake()
    {
        if (Instance != null && Instance != this) { Destroy(gameObject); return; }
        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    // NativeWebSocket requires DispatchMessageQueue() on every Update frame
    private void Update()
    {
        #if !UNITY_WEBGL || UNITY_EDITOR
        _ws?.DispatchMessageQueue();
        #endif
    }

    // ── Public API ──────────────────────────────────────────────────────────

    /// Connect to a room. No-op if already connected to the same room.
    public async void Connect(string roomId, string token)
    {
        if ((IsConnected || IsReconnecting) && _roomId == roomId) return;

        _roomId     = roomId;
        _token      = string.IsNullOrEmpty(token)
                      ? TokenStore.Instance.StableGuestToken()
                      : token;
        _retryCount = 0;
        await OpenConnection();
    }

    public async void Send(ClientMessage msg)
    {
        if (_ws == null || _ws.State != WebSocketState.Open) return;
        await _ws.SendText(msg.ToJson());
    }

    public async void SendText(string text)
        => await _ws?.SendText(text);

    public void Disconnect()
    {
        StopPing();
        _ws?.Close();
        _ws           = null;
        IsConnected   = false;
        IsReconnecting= false;
        OnDisconnected?.Invoke();
    }

    // ── Internal ────────────────────────────────────────────────────────────

    private async Cysharp.Threading.Tasks.UniTask OpenConnection()
    {
        _connId++;          // Rotate ID so stale handlers self-discard
        int myConnId = _connId;

        StopPing();
        _ws?.Close();

        var encodedToken = Uri.EscapeDataString(_token);
        var url = $"{AppConfig.WsBaseURL}/ws/{_roomId}?token={encodedToken}";

        _ws = new WebSocket(url);

        _ws.OnOpen += () =>
        {
            if (myConnId != _connId) return;
            IsConnected    = true;
            IsReconnecting = false;
            _retryCount    = 0;
            OnConnected?.Invoke();
            StartPing();
        };

        _ws.OnMessage += (bytes) =>
        {
            if (myConnId != _connId) return;
            var text = Encoding.UTF8.GetString(bytes);
            try
            {
                var msg = GameMessage.Parse(text);
                OnMessage?.Invoke(msg);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[WS] decode FAILED: {ex.Message}\nraw: {text[..Mathf.Min(300, text.Length)]}");
            }
        };

        _ws.OnError += (e) =>
        {
            if (myConnId != _connId) return;
            Debug.LogWarning($"[WS] error: {e}");
        };

        _ws.OnClose += (code) =>
        {
            if (myConnId != _connId) return;
            IsConnected = false;
            HandleDisconnect();
        };

        await _ws.Connect();
    }

    private void HandleDisconnect()
    {
        IsConnected = false;
        if (_retryCount >= MaxRetries)
        {
            IsReconnecting = false;
            OnDisconnected?.Invoke();
            return;
        }
        _retryCount++;
        IsReconnecting = true;
        float delay = _retryCount * 1.5f;
        StartCoroutine(RetryAfterDelay(delay));
    }

    private IEnumerator RetryAfterDelay(float delay)
    {
        yield return new WaitForSeconds(delay);
        OpenConnection().Forget();
    }

    private void StartPing()
    {
        StopPing();
        _pingCoroutine = StartCoroutine(PingLoop());
    }

    private void StopPing()
    {
        if (_pingCoroutine != null) StopCoroutine(_pingCoroutine);
        _pingCoroutine = null;
    }

    private IEnumerator PingLoop()
    {
        while (true)
        {
            yield return new WaitForSeconds(20f);
            if (_ws != null && _ws.State == WebSocketState.Open)
                _ws.SendText("{}");    // keep-alive ping (backend ignores unknown type)
        }
    }
}
