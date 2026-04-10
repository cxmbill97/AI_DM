// Prefab controller for a single card in the RoomBrowser scroll list.
// Mirrors ios/AIDungeonMaster/Explore/ExploreView.swift — RoomRow struct.
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
    [SerializeField] private Image     gameTypeIcon;     // background gradient image
    [SerializeField] private Button    playButton;

    private Action _onPlay;

    public void SetData(ActiveRoom room, Action onPlay)
    {
        _onPlay = onPlay;
        if (titleLabel)    titleLabel.text    = room.Title;
        if (gameTypeLabel) gameTypeLabel.text  = room.GameType == "turtle_soup" ? "🐢 Turtle Soup" : "🔍 Murder Mystery";
        if (roomCodeLabel) roomCodeLabel.text  = room.RoomId;
        if (playerCountLabel) playerCountLabel.text = $"{room.ConnectedCount}/{room.MaxPlayers ?? room.PlayerCount}";
        playButton?.onClick.RemoveAllListeners();
        playButton?.onClick.AddListener(() => _onPlay?.Invoke());
    }

    public void SetData(PuzzleSummary puzzle, Action onPlay)
    {
        _onPlay = onPlay;
        if (titleLabel)    titleLabel.text    = puzzle.Title;
        if (gameTypeLabel) gameTypeLabel.text  = "🐢 Turtle Soup";
        if (difficultyBadge) difficultyBadge.text = LocalisedDifficulty(puzzle.Difficulty);
        playButton?.onClick.RemoveAllListeners();
        playButton?.onClick.AddListener(() => _onPlay?.Invoke());
    }

    public void SetData(ScriptSummary script, Action onPlay)
    {
        _onPlay = onPlay;
        if (titleLabel)    titleLabel.text    = script.Title;
        if (gameTypeLabel) gameTypeLabel.text  = "🔍 Murder Mystery";
        if (difficultyBadge) difficultyBadge.text = LocalisedDifficulty(script.Difficulty);
        if (playerCountLabel) playerCountLabel.text = $"{script.PlayerCount} players";
        playButton?.onClick.RemoveAllListeners();
        playButton?.onClick.AddListener(() => _onPlay?.Invoke());
    }

    private static string LocalisedDifficulty(string d)
    {
        var lang = PlayerPrefs.GetString("lang", "zh");
        return (d?.ToLower()) switch
        {
            "简单" or "easy" or "beginner"    => lang == "zh" ? "简单" : "Easy",
            "困难" or "hard" or "advanced"    => lang == "zh" ? "困难" : "Hard",
            _                                 => lang == "zh" ? "中等" : "Medium",
        };
    }
}
