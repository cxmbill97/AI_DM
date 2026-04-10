// Mirrors ios/AIDungeonMaster/Lobby/WaitingRoomViewModel.swift — playerIdFromToken()
using System;
using System.Text;
using Newtonsoft.Json.Linq;

public static class JwtDecoder
{
    /// Decode the JWT "sub" claim without verifying the signature.
    /// Returns null if the token is missing, malformed, or has no sub.
    public static string GetSubject(string jwt)
    {
        if (string.IsNullOrEmpty(jwt)) return null;
        var parts = jwt.Split('.');
        if (parts.Length != 3) return null;
        try
        {
            var payload = Base64UrlDecode(parts[1]);
            var json    = JObject.Parse(payload);
            return json["sub"]?.ToString();
        }
        catch { return null; }
    }

    private static string Base64UrlDecode(string input)
    {
        // Pad to multiple of 4
        input = input.Replace('-', '+').Replace('_', '/');
        switch (input.Length % 4)
        {
            case 2: input += "=="; break;
            case 3: input += "=";  break;
        }
        return Encoding.UTF8.GetString(Convert.FromBase64String(input));
    }
}
