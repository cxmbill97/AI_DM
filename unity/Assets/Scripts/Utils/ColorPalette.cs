// Hex constants extracted from ios/AIDungeonMaster — mirrors Color(hex:) extension
using UnityEngine;

public static class ColorPalette
{
    // Backgrounds
    public static readonly Color Background  = Hex("#0a0a0f");
    public static readonly Color Surface     = Hex("#16151f");
    public static readonly Color SurfaceAlt  = Hex("#0d0c17");
    public static readonly Color Elevated    = Hex("#1e1c2e");

    // Borders
    public static readonly Color Border      = Hex("#2a2840");
    public static readonly Color BorderDim   = Hex("#1a1a2e");

    // Text
    public static readonly Color TextPrimary = Hex("#e2e2f0");
    public static readonly Color TextMuted   = Hex("#5555a0");
    public static readonly Color TextDisabled= Hex("#44446a");

    // Accent / Gold gradient ends
    public static readonly Color GoldBright  = Hex("#f0d878");
    public static readonly Color Gold        = Hex("#c9a84c");
    public static readonly Color GoldSoft    = Hex("#e8c96a");

    // Status
    public static readonly Color Success     = Hex("#34d399");
    public static readonly Color Warning     = Hex("#fbbf24");
    public static readonly Color Danger      = Hex("#f87171");
    public static readonly Color Info        = Hex("#60a5fa");
    public static readonly Color Purple      = Hex("#818cf8");
    public static readonly Color PurpleMid   = Hex("#5555a0");

    // Chat sender colours
    public static readonly Color SenderDm     = Hex("#34d399");
    public static readonly Color SenderPlayer = Hex("#818cf8");
    public static readonly Color SenderSystem = Hex("#c9a84c");
    public static readonly Color SenderError  = Hex("#f87171");

    // Player avatar palette (matches RoomView.swift avatarColor)
    public static readonly Color[] AvatarColors =
    {
        Hex("#6366f1"), Hex("#8b5cf6"), Hex("#06b6d4"),
        Hex("#10b981"), Hex("#f59e0b"), Hex("#ef4444"),
    };

    public static Color AvatarColor(string name)
    {
        int hash = 0;
        foreach (var c in name) hash += c;
        return AvatarColors[Mathf.Abs(hash) % AvatarColors.Length];
    }

    /// Parse a 6-digit hex colour string (with or without leading #).
    public static Color Hex(string hex)
    {
        hex = hex.TrimStart('#');
        if (hex.Length != 6) return Color.magenta; // invalid → bright pink for debugging
        float r = System.Convert.ToInt32(hex.Substring(0, 2), 16) / 255f;
        float g = System.Convert.ToInt32(hex.Substring(2, 2), 16) / 255f;
        float b = System.Convert.ToInt32(hex.Substring(4, 2), 16) / 255f;
        return new Color(r, g, b, 1f);
    }
}
