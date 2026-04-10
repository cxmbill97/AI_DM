// Bottom navigation bar — mirrors ios/AIDungeonMaster/App/CustomTabBar.swift.
// Hides inside GameRoom; visible on all other scenes.
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class BottomNavBar : MonoBehaviour
{
    [System.Serializable]
    public struct TabEntry
    {
        public Button  button;
        public Image   icon;
        public TMP_Text label;
        public string  sceneName;
    }

    [SerializeField] private TabEntry[] tabs;
    [SerializeField] private Color selectedColor   = new Color(0.945f, 0.659f, 0.298f); // #c9a84c
    [SerializeField] private Color unselectedColor = new Color(0.267f, 0.267f, 0.416f); // #44446a

    private string _currentScene = "MainMenu";

    private void Start()
    {
        for (int i = 0; i < tabs.Length; i++)
        {
            var entry = tabs[i];
            tabs[i].button?.onClick.AddListener(() => OnTabTapped(entry.sceneName));
        }
        RefreshColors();
    }

    private void OnTabTapped(string scene)
    {
        _currentScene = scene;
        RefreshColors();
        SceneLoader.LoadScene(scene);
    }

    private void RefreshColors()
    {
        foreach (var t in tabs)
        {
            bool sel = t.sceneName == _currentScene;
            if (t.icon)  t.icon.color  = sel ? selectedColor : unselectedColor;
            if (t.label) t.label.color = sel ? selectedColor : unselectedColor;
        }
    }

    public void Show() => gameObject.SetActive(true);
    public void Hide() => gameObject.SetActive(false);
}
