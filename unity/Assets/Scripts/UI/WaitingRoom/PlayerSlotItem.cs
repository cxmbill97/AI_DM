// Mirrors ios/AIDungeonMaster/Lobby/WaitingRoomView.swift — PlayerSlotRow / EmptySlotRow.
// Attach to PlayerSlot.prefab and EmptySlot.prefab.
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class PlayerSlotItem : MonoBehaviour
{
    [Header("Filled")]
    [SerializeField] private TMP_Text  nameLabel;
    [SerializeField] private TMP_Text  initialLabel;     // Avatar letter
    [SerializeField] private Image     avatarBg;
    [SerializeField] private GameObject hostBadge;
    [SerializeField] private Image     readyIcon;         // checkmark or clock
    [SerializeField] private Sprite    readySprite;
    [SerializeField] private Sprite    waitingSprite;

    [Header("Empty Slot")]
    [SerializeField] private GameObject emptySlotRoot;
    [SerializeField] private GameObject filledSlotRoot;

    public void SetPlayer(PlayerInfo player, bool isReady)
    {
        emptySlotRoot?.SetActive(false);
        filledSlotRoot?.SetActive(true);

        if (nameLabel)    nameLabel.text    = player.Name;
        if (initialLabel) initialLabel.text = player.Name.Length > 0 ? player.Name[0].ToString().ToUpper() : "?";
        if (avatarBg)     avatarBg.color    = ColorPalette.AvatarColor(player.Name);
        hostBadge?.SetActive(player.IsHost == true);

        if (readyIcon)
        {
            readyIcon.sprite = isReady ? readySprite : waitingSprite;
            readyIcon.color  = isReady ? ColorPalette.Success : ColorPalette.TextDisabled;
        }
    }

    public void SetEmpty()
    {
        emptySlotRoot?.SetActive(true);
        filledSlotRoot?.SetActive(false);
    }
}
