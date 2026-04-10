// Mirrors ios/AIDungeonMaster/Models/Models.swift lines 89-265
// Discriminated union on the "type" JSON field — all 12+ server event types.
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

// ── Payload structs ──────────────────────────────────────────────────────────

[System.Serializable]
public class CluePayload
{
    [JsonProperty("id")]               public string Id;
    [JsonProperty("title")]            public string Title;
    [JsonProperty("content")]          public string Content;
    [JsonProperty("unlock_keywords")]  public List<string> UnlockKeywords = new();
}

[System.Serializable]
public class DmResponsePayload
{
    [JsonProperty("player_name")]    public string PlayerName;
    [JsonProperty("judgment")]       public string Judgment;
    [JsonProperty("response")]       public string Response;
    [JsonProperty("truth_progress")] public float TruthProgress;
    [JsonProperty("clue_unlocked")]  public CluePayload ClueUnlocked;
    [JsonProperty("hint")]           public string Hint;
    [JsonProperty("truth")]          public string Truth;
    [JsonProperty("timestamp")]      public double Timestamp;
}

[System.Serializable]
public class DmStreamStartPayload
{
    [JsonProperty("stream_id")]   public string StreamId;
    [JsonProperty("player_name")] public string PlayerName;
    [JsonProperty("timestamp")]   public double? Timestamp;
}

[System.Serializable]
public class DmStreamChunkPayload
{
    [JsonProperty("stream_id")] public string StreamId;
    [JsonProperty("text")]      public string Text;
}

[System.Serializable]
public class DmStreamEndPayload
{
    [JsonProperty("stream_id")]      public string StreamId;
    [JsonProperty("player_name")]    public string PlayerName;
    [JsonProperty("judgment")]       public string Judgment;
    [JsonProperty("response")]       public string Response;
    [JsonProperty("truth_progress")] public float? TruthProgress;
    [JsonProperty("clue_unlocked")]  public CluePayload ClueUnlocked;
    [JsonProperty("hint")]           public string Hint;
    [JsonProperty("truth")]          public string Truth;
    [JsonProperty("timestamp")]      public double? Timestamp;
}

[System.Serializable]
public class PlayerMessagePayload
{
    [JsonProperty("player_name")] public string PlayerName;
    [JsonProperty("text")]        public string Text;
    [JsonProperty("timestamp")]   public double Timestamp;
}

[System.Serializable]
public class SystemPayload
{
    [JsonProperty("text")] public string Text;
}

[System.Serializable]
public class PlayerInfo
{
    [JsonProperty("id")]        public string Id;
    [JsonProperty("name")]      public string Name;
    [JsonProperty("character")] public string Character;
    [JsonProperty("connected")] public bool? Connected;
    [JsonProperty("is_host")]   public bool? IsHost;
    [JsonProperty("is_ready")]  public bool? IsReady;
}

[System.Serializable]
public class RoomSnapshotPayload
{
    [JsonProperty("room_id")]                  public string RoomId;
    [JsonProperty("game_type")]                public string GameType;
    [JsonProperty("title")]                    public string Title;
    [JsonProperty("surface")]                  public string Surface;
    [JsonProperty("phase")]                    public string Phase;
    [JsonProperty("current_phase")]            public string CurrentPhase;
    [JsonProperty("phase_description")]        public string PhaseDescription;
    [JsonProperty("players")]                  public List<PlayerInfo> Players = new();
    [JsonProperty("clues")]                    public List<CluePayload> Clues;
    [JsonProperty("time_remaining")]           public int? TimeRemaining;
    [JsonProperty("started")]                  public bool? Started;
    [JsonProperty("max_players")]              public int? MaxPlayers;
    [JsonProperty("host_player_id")]           public string HostPlayerId;
    [JsonProperty("my_player_id")]             public string MyPlayerId;
    [JsonProperty("turn_mode")]                public bool? TurnMode;
    [JsonProperty("current_turn_player_id")]   public string CurrentTurnPlayerId;
    [JsonProperty("current_turn_player_name")] public string CurrentTurnPlayerName;
}

[System.Serializable]
public class TurnChangePayload
{
    [JsonProperty("player_id")]   public string PlayerId;
    [JsonProperty("player_name")] public string PlayerName;
    [JsonProperty("text")]        public string Text;
    [JsonProperty("timestamp")]   public double Timestamp;
}

[System.Serializable]
public class LobbyPlayerJoinedPayload
{
    [JsonProperty("player_id")]   public string PlayerId;
    [JsonProperty("player_name")] public string PlayerName;
    [JsonProperty("is_host")]     public bool? IsHost;
    [JsonProperty("timestamp")]   public double Timestamp;
}

[System.Serializable]
public class LobbyPlayerReadyPayload
{
    [JsonProperty("player_id")]   public string PlayerId;
    [JsonProperty("player_name")] public string PlayerName;
    [JsonProperty("timestamp")]   public double Timestamp;
}

[System.Serializable]
public class GameStartedPayload
{
    [JsonProperty("room_id")] public string RoomId;
}

[System.Serializable]
public class ErrorPayload
{
    // Backend sends either "text" or "message" — mirrors Swift's custom CodingKeys decoder
    public string Message;

    [JsonConstructor]
    public ErrorPayload() { }

    public static ErrorPayload FromJObject(JObject obj)
    {
        var ep = new ErrorPayload();
        ep.Message = obj["message"]?.ToString() ?? obj["text"]?.ToString() ?? "Unknown error";
        return ep;
    }
}

// ── Discriminated union ──────────────────────────────────────────────────────

public enum GameMessageType
{
    DmResponse, DmStreamStart, DmStreamChunk, DmStreamEnd,
    PlayerMessage, System, RoomSnapshot, Error,
    PlayerJoined, PlayerReady, GameStarted, TurnChange, Unknown
}

public class GameMessage
{
    public GameMessageType Type { get; private set; }

    // Only one payload field is non-null per message
    public DmResponsePayload         DmResponse    { get; private set; }
    public DmStreamStartPayload      DmStreamStart { get; private set; }
    public DmStreamChunkPayload      DmStreamChunk { get; private set; }
    public DmStreamEndPayload        DmStreamEnd   { get; private set; }
    public PlayerMessagePayload      PlayerMessage { get; private set; }
    public SystemPayload             System        { get; private set; }
    public RoomSnapshotPayload       RoomSnapshot  { get; private set; }
    public ErrorPayload              Error         { get; private set; }
    public LobbyPlayerJoinedPayload  PlayerJoined  { get; private set; }
    public LobbyPlayerReadyPayload   PlayerReady   { get; private set; }
    public GameStartedPayload        GameStarted   { get; private set; }
    public TurnChangePayload         TurnChange    { get; private set; }
    public string                    UnknownType   { get; private set; }

    /// Parse a raw JSON string from the WebSocket into the appropriate message type.
    public static GameMessage Parse(string json)
    {
        var obj = JObject.Parse(json);
        var type = obj["type"]?.ToString() ?? "";
        var msg = new GameMessage();

        switch (type)
        {
            case "dm_response":
                msg.Type = GameMessageType.DmResponse;
                msg.DmResponse = JsonConvert.DeserializeObject<DmResponsePayload>(json);
                break;
            case "dm_stream_start":
                msg.Type = GameMessageType.DmStreamStart;
                msg.DmStreamStart = JsonConvert.DeserializeObject<DmStreamStartPayload>(json);
                break;
            case "dm_stream_chunk":
                msg.Type = GameMessageType.DmStreamChunk;
                msg.DmStreamChunk = JsonConvert.DeserializeObject<DmStreamChunkPayload>(json);
                break;
            case "dm_stream_end":
                msg.Type = GameMessageType.DmStreamEnd;
                msg.DmStreamEnd = JsonConvert.DeserializeObject<DmStreamEndPayload>(json);
                break;
            case "player_message":
                msg.Type = GameMessageType.PlayerMessage;
                msg.PlayerMessage = JsonConvert.DeserializeObject<PlayerMessagePayload>(json);
                break;
            case "system":
                msg.Type = GameMessageType.System;
                msg.System = JsonConvert.DeserializeObject<SystemPayload>(json);
                break;
            case "room_snapshot":
                msg.Type = GameMessageType.RoomSnapshot;
                msg.RoomSnapshot = JsonConvert.DeserializeObject<RoomSnapshotPayload>(json);
                break;
            case "error":
                msg.Type = GameMessageType.Error;
                msg.Error = ErrorPayload.FromJObject(obj);
                break;
            case "player_joined":
                msg.Type = GameMessageType.PlayerJoined;
                msg.PlayerJoined = JsonConvert.DeserializeObject<LobbyPlayerJoinedPayload>(json);
                break;
            case "player_ready":
                msg.Type = GameMessageType.PlayerReady;
                msg.PlayerReady = JsonConvert.DeserializeObject<LobbyPlayerReadyPayload>(json);
                break;
            case "game_started":
                msg.Type = GameMessageType.GameStarted;
                msg.GameStarted = JsonConvert.DeserializeObject<GameStartedPayload>(json);
                break;
            case "turn_change":
                msg.Type = GameMessageType.TurnChange;
                msg.TurnChange = JsonConvert.DeserializeObject<TurnChangePayload>(json);
                break;
            default:
                msg.Type = GameMessageType.Unknown;
                msg.UnknownType = type;
                break;
        }
        return msg;
    }
}
