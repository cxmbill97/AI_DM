// Reusable avatar widget: coloured circle + initial letter.
// Mirrors the avatar pattern used across WaitingRoomView and RoomView in the iOS app.
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class PlayerAvatar : MonoBehaviour
{
    [SerializeField] private Image    background;
    [SerializeField] private TMP_Text initialLabel;

    public void SetPlayer(string name)
    {
        if (background)    background.color    = ColorPalette.AvatarColor(name);
        if (initialLabel)  initialLabel.text   = string.IsNullOrEmpty(name) ? "?" : name[0].ToString().ToUpper();
    }

    public void SetEmpty()
    {
        if (background)   background.color   = ColorPalette.TextDisabled;
        if (initialLabel) initialLabel.text  = "+";
    }
}
