// Prefab controller for a single chat bubble in the GameRoom scroll list.
// Mirrors ios/AIDungeonMaster/Room/RoomView.swift — MessageBubble struct.
// Attach to each of: PlayerMessage.prefab, DmMessage.prefab, SystemMessage.prefab
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public enum ChatMsgType { Player, Dm, System, Error, Emote }

public class ChatMessageItem : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private TMP_Text  senderLabel;
    [SerializeField] private TMP_Text  bodyText;
    [SerializeField] private TMP_Text  judgmentBadge;
    [SerializeField] private Image     leftAccent;    // DM correct-answer accent bar
    [SerializeField] private Image     background;

    // Set by GameRoomController when instantiating
    [HideInInspector] public string StreamId;
    [HideInInspector] public bool   IsStreaming;

    public void SetData(string sender, string text, ChatMsgType type, string judgment = null)
    {
        if (senderLabel) { senderLabel.text  = sender; senderLabel.color = SenderColor(type); }
        if (bodyText)    { bodyText.text      = text;   bodyText.color    = BodyColor(type); }

        // Judgment badge (Yes/No/Partial/N/A)
        if (judgmentBadge)
        {
            if (!string.IsNullOrEmpty(judgment))
            {
                judgmentBadge.text             = JudgmentLabel(judgment);
                judgmentBadge.color            = JudgmentColor(judgment);
                judgmentBadge.gameObject.SetActive(true);
            }
            else
            {
                judgmentBadge.gameObject.SetActive(false);
            }
        }

        // Left accent on DM "Yes" answers — mirrors Swift overlay on .dm && isPositiveJudgment
        if (leftAccent)
            leftAccent.gameObject.SetActive(type == ChatMsgType.Dm && IsPositive(judgment));

        if (background)
            background.color = type == ChatMsgType.Dm
                ? new Color(0.086f, 0.082f, 0.118f, 0.5f)   // #16151f 50%
                : Color.clear;
    }

    /// Append a streaming chunk — called by GameRoomController on dm_stream_chunk
    public void AppendChunk(string chunk)
    {
        if (bodyText) bodyText.text += chunk;
    }

    /// Finalise a streaming message — called on dm_stream_end
    public void FinaliseStream(string finalText, string judgment)
    {
        if (bodyText && !string.IsNullOrEmpty(finalText)) bodyText.text = finalText;
        if (!string.IsNullOrEmpty(judgment))
        {
            if (judgmentBadge) { judgmentBadge.text = JudgmentLabel(judgment); judgmentBadge.color = JudgmentColor(judgment); judgmentBadge.gameObject.SetActive(true); }
            if (leftAccent)      leftAccent.gameObject.SetActive(IsPositive(judgment));
        }
        IsStreaming = false;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static Color SenderColor(ChatMsgType t) => t switch
    {
        ChatMsgType.Dm     => ColorPalette.SenderDm,
        ChatMsgType.System => ColorPalette.SenderSystem,
        ChatMsgType.Error  => ColorPalette.SenderError,
        _                  => ColorPalette.SenderPlayer,
    };

    private static Color BodyColor(ChatMsgType t) => t switch
    {
        ChatMsgType.Error  => ColorPalette.Danger,
        ChatMsgType.System => ColorPalette.GoldSoft,
        _                  => ColorPalette.TextPrimary,
    };

    private static string JudgmentLabel(string j) => j switch
    {
        "是" or "Yes"              => "✓ YES",
        "部分正确" or "Partially correct" => "~ PARTIAL",
        "不是" or "No"             => "✗ NO",
        _                          => "— N/A",
    };

    private static Color JudgmentColor(string j) => j switch
    {
        "是" or "Yes"              => ColorPalette.Success,
        "部分正确" or "Partially correct" => ColorPalette.Warning,
        "不是" or "No"             => ColorPalette.Danger,
        _                          => ColorPalette.TextMuted,
    };

    private static bool IsPositive(string j)
        => j == "是" || j == "Yes";
}
