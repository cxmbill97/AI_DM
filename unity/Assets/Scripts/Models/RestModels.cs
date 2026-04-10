// Mirrors ios/AIDungeonMaster/Models/Models.swift lines 5-88
using System.Collections.Generic;
using Newtonsoft.Json;

[System.Serializable]
public class User
{
    [JsonProperty("id")]          public string Id;
    [JsonProperty("name")]        public string Name;
    [JsonProperty("email")]       public string Email;
    [JsonProperty("avatar_url")]  public string AvatarUrl;
    [JsonProperty("created_at")] public string CreatedAt;
}

[System.Serializable]
public class PuzzleSummary
{
    [JsonProperty("id")]         public string Id;
    [JsonProperty("title")]      public string Title;
    [JsonProperty("difficulty")] public string Difficulty;
    [JsonProperty("tags")]       public List<string> Tags = new();
}

[System.Serializable]
public class ScriptSummary
{
    [JsonProperty("id")]           public string Id;
    [JsonProperty("title")]        public string Title;
    [JsonProperty("difficulty")]   public string Difficulty;
    [JsonProperty("player_count")] public int PlayerCount;
}

[System.Serializable]
public class FavoriteItem
{
    [JsonProperty("item_id")]   public string ItemId;
    [JsonProperty("item_type")] public string ItemType;
    [JsonProperty("saved_at")]  public string SavedAt;
    public string Id => $"{ItemType}:{ItemId}";
}

[System.Serializable]
public class HistoryItem
{
    [JsonProperty("id")]           public string Id;
    [JsonProperty("room_id")]      public string RoomId;
    [JsonProperty("game_type")]    public string GameType;
    [JsonProperty("title")]        public string Title;
    [JsonProperty("player_count")] public int PlayerCount;
    [JsonProperty("played_at")]    public string PlayedAt;
    [JsonProperty("outcome")]      public string Outcome;
}

[System.Serializable]
public class ActiveRoom
{
    [JsonProperty("room_id")]        public string RoomId;
    [JsonProperty("game_type")]      public string GameType;
    [JsonProperty("title")]          public string Title;
    [JsonProperty("player_count")]   public int PlayerCount;
    [JsonProperty("connected_count")]public int ConnectedCount;
    [JsonProperty("max_players")]    public int? MaxPlayers;
    [JsonProperty("language")]       public string Language;
}

[System.Serializable]
public class CommunityScript
{
    [JsonProperty("script_id")]    public string ScriptId;
    [JsonProperty("title")]        public string Title;
    [JsonProperty("author")]       public string Author;
    [JsonProperty("difficulty")]   public string Difficulty;
    [JsonProperty("player_count")] public int PlayerCount;
    [JsonProperty("game_mode")]    public string GameMode;
    [JsonProperty("lang")]         public string Lang;
    [JsonProperty("likes")]        public int Likes;
    [JsonProperty("created_at")]   public string CreatedAt;
}

[System.Serializable]
public class CreateRoomResponse
{
    [JsonProperty("room_id")]   public string RoomId;
    [JsonProperty("game_type")] public string GameType;
}
