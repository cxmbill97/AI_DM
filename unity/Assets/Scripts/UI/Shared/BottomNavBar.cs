// Bottom navigation bar — mirrors ios/AIDungeonMaster/App/CustomTabBar.swift.
// Each tab can either load a scene (sceneName) or toggle a local panel (localPanel).
// Hides inside GameRoom; visible on all other scenes.
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class BottomNavBar : MonoBehaviour
{
    [System.Serializable]
    public struct TabEntry
    {
        public Button     button;
        public Image      icon;
        public TMP_Text   label;
        public string     sceneName;   // load this scene on tap (if non-empty)
        public GameObject localPanel;  // toggle this panel instead of scene load
    }

    [SerializeField] private TabEntry[] tabs;
    [SerializeField] private Color selectedColor   = new Color(0.945f, 0.659f, 0.298f); // gold
    [SerializeField] private Color unselectedColor = new Color(0.267f, 0.267f, 0.416f); // muted

    private int _selectedIndex = -1;

    private void Start()
    {
        for (int i = 0; i < tabs.Length; i++)
        {
            int idx = i;
            tabs[i].button?.onClick.AddListener(() => OnTabTapped(idx));
        }
        // Highlight the tab whose scene matches the current active scene
        string active = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
        for (int i = 0; i < tabs.Length; i++)
            if (tabs[i].sceneName == active) { _selectedIndex = i; break; }
        RefreshColors();
    }

    private void OnTabTapped(int idx)
    {
        var tab = tabs[idx];

        if (tab.localPanel != null)
        {
            // Toggle the panel — close all other local panels first
            bool wasActive = tab.localPanel.activeSelf;
            foreach (var t in tabs)
                if (t.localPanel != null) t.localPanel.SetActive(false);
            tab.localPanel.SetActive(!wasActive);
            _selectedIndex = !wasActive ? idx : -1;
            RefreshColors();
            return;
        }

        if (!string.IsNullOrEmpty(tab.sceneName))
        {
            _selectedIndex = idx;
            RefreshColors();
            SceneLoader.LoadScene(tab.sceneName);
        }
    }

    private void RefreshColors()
    {
        for (int i = 0; i < tabs.Length; i++)
        {
            bool sel = i == _selectedIndex;
            if (tabs[i].icon)  tabs[i].icon.color  = sel ? selectedColor : unselectedColor;
            if (tabs[i].label) tabs[i].label.color = sel ? selectedColor : unselectedColor;
        }
    }

    public void Show() => gameObject.SetActive(true);
    public void Hide() => gameObject.SetActive(false);
}
