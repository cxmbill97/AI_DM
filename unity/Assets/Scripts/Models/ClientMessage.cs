// Mirrors ios/AIDungeonMaster/Models/Models.swift lines 269-272
using Newtonsoft.Json;

[System.Serializable]
public class ClientMessage
{
    [JsonProperty("type")] public string Type;
    [JsonProperty("text")] public string Text;

    public ClientMessage(string type, string text = "")
    {
        Type = type;
        Text = text;
    }

    public string ToJson() => JsonConvert.SerializeObject(this);
}
