// Horizontal game card for the RoomBrowser scroll list.
// Layout: [Icon Panel] | [Title / Badges / Desc] | [PLAY button]
using UnityEngine;
using UnityEngine.UI;
using TMPro;
using System;

public class RoomCardItem : MonoBehaviour
{
    [SerializeField] private TMP_Text  titleLabel;
    [SerializeField] private TMP_Text  gameTypeLabel;
    [SerializeField] private TMP_Text  roomCodeLabel;
    [SerializeField] private TMP_Text  playerCountLabel;
    [SerializeField] private TMP_Text  difficultyBadge;
    [SerializeField] private TMP_Text  descriptionLabel;
    [SerializeField] private Image     difficultyPanel;   // badge background — colored by difficulty
    [SerializeField] private Image     iconPanel;         // left colored panel
    [SerializeField] private Button    playButton;

    // Difficulty palette
    static readonly Color Easy    = new(0.15f, 0.68f, 0.38f);  // #27AE60
    static readonly Color Medium  = new(0.16f, 0.50f, 0.73f);  // #2980B9
    static readonly Color Hard    = new(0.90f, 0.49f, 0.13f);  // #E67E22
    static readonly Color Classic = new(0.56f, 0.27f, 0.68f);  // #8E44AD

    private Action _onPlay;

    // ── Active Room ───────────────────────────────────────────────────────────

    public void SetData(ActiveRoom room, Action onPlay)
    {
        _onPlay = onPlay;
        var isTS = room.GameType == "turtle_soup";
        if (titleLabel)       titleLabel.text       = AsciiTitle(room.Title);
        if (gameTypeLabel)    gameTypeLabel.text     = isTS ? "Turtle Soup" : "Murder Mystery";
        if (roomCodeLabel)    roomCodeLabel.text     = room.RoomId;
        if (playerCountLabel) playerCountLabel.text  =
            $"{room.ConnectedCount}/{room.MaxPlayers ?? room.PlayerCount}P";
        if (descriptionLabel) descriptionLabel.text  = "Room is open — tap to join!";

        var col = isTS ? Medium : Hard;
        ApplyDifficultyColor(col);
        SetIconLabel("active_room");
        WireButton(onPlay);
    }

    // ── Puzzle (Turtle Soup) ──────────────────────────────────────────────────

    public void SetData(PuzzleSummary puzzle, Action onPlay)
    {
        _onPlay = onPlay;
        if (titleLabel)       titleLabel.text       = AsciiTitle(puzzle.Title);
        if (gameTypeLabel)    gameTypeLabel.text     = "Turtle Soup";
        if (roomCodeLabel)    roomCodeLabel.gameObject.SetActive(false);
        if (playerCountLabel) playerCountLabel.text  = "1P+";
        if (difficultyBadge)  difficultyBadge.text   = EnglishDifficulty(puzzle.Difficulty);
        if (descriptionLabel) descriptionLabel.text  =
            string.Join(", ", puzzle.Tags?.Count > 0 ? puzzle.Tags : new System.Collections.Generic.List<string>{"Mystery"});

        var col = DifficultyColor(puzzle.Difficulty);
        ApplyDifficultyColor(col);
        SetIconLabel("turtle_soup");
        WireButton(onPlay);
    }

    // ── Script (Murder Mystery) ───────────────────────────────────────────────

    public void SetData(ScriptSummary script, Action onPlay)
    {
        _onPlay = onPlay;
        if (titleLabel)       titleLabel.text       = AsciiTitle(script.Title);
        if (gameTypeLabel)    gameTypeLabel.text     = "Murder Mystery";
        if (roomCodeLabel)    roomCodeLabel.gameObject.SetActive(false);
        if (playerCountLabel) playerCountLabel.text  = $"{script.PlayerCount}P";
        if (difficultyBadge)  difficultyBadge.text   = EnglishDifficulty(script.Difficulty);
        if (descriptionLabel) descriptionLabel.text  = "Unravel the conspiracy. Find the killer.";

        var col = DifficultyColor(script.Difficulty);
        ApplyDifficultyColor(col);
        SetIconLabel("murder_mystery");
        WireButton(onPlay);
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private void ApplyDifficultyColor(Color col)
    {
        if (difficultyPanel) difficultyPanel.color = col;
        if (iconPanel)       iconPanel.color       = new Color(col.r * 0.6f, col.g * 0.6f, col.b * 0.6f);
    }

    private void SetIconLabel(string gameTypeKey)
    {
        // Try to load the extracted sprite from Resources/GameIcons/
        var spr = Resources.Load<Sprite>($"GameIcons/{gameTypeKey}");
        if (spr != null && iconPanel != null)
        {
            iconPanel.sprite = spr;
            iconPanel.type   = UnityEngine.UI.Image.Type.Simple;
            iconPanel.preserveAspect = true;
            // Hide the text label when we have a real icon
            var lbl = iconPanel.transform.Find("IconLabel")?.GetComponent<TMP_Text>();
            if (lbl) lbl.gameObject.SetActive(false);
        }
        else
        {
            // Fallback: show initial letter
            var lbl = iconPanel?.transform.Find("IconLabel")?.GetComponent<TMP_Text>();
            if (lbl) { lbl.gameObject.SetActive(true); lbl.text = gameTypeKey.Substring(0,1).ToUpper(); }
        }
    }

    private void WireButton(Action onPlay)
    {
        playButton?.onClick.RemoveAllListeners();
        playButton?.onClick.AddListener(() => onPlay?.Invoke());
    }

    private static string AsciiTitle(string s)
        => string.IsNullOrEmpty(s) ? "Untitled" : s.Trim();

    private static string EnglishDifficulty(string d) => (d?.ToLower()) switch
    {
        "简单" or "easy"    or "beginner" => "Easy",
        "困难" or "hard"    or "advanced" => "Hard",
        "中等" or "medium"  or "normal"   => "Medium",
        "经典" or "classic"               => "Classic",
        _ => AsciiTitle(d) is { Length: > 0 } a ? a : "Standard",
    };

    private static Color DifficultyColor(string d) => (d?.ToLower()) switch
    {
        "简单" or "easy"    or "beginner" => Easy,
        "困难" or "hard"    or "advanced" => Hard,
        "经典" or "classic"               => Classic,
        _                                 => Medium,
    };
}
