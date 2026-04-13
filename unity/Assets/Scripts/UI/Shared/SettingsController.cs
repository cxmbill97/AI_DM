// Settings panel — language toggle + volume control.
// Attach to the SettingsPanel overlay GameObject.
// Wire openButton to the top-right "=" button; the panel starts hidden.
using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class SettingsController : MonoBehaviour
{
    [SerializeField] private Button  openButton;
    [SerializeField] private Button  closeButton;
    [SerializeField] private Button  langZhButton;
    [SerializeField] private Button  langEnButton;
    [SerializeField] private Slider  volumeSlider;
    [SerializeField] private TMP_Text currentLangLabel;

    private static readonly Color ActiveBtn  = new(0.95f, 0.76f, 0.20f);   // gold
    private static readonly Color InactiveBtn= new(0.13f, 0.20f, 0.35f);   // navy

    private void Start()
    {
        openButton?.onClick.AddListener(Open);
        closeButton?.onClick.AddListener(Close);
        langZhButton?.onClick.AddListener(() => SetLang("zh"));
        langEnButton?.onClick.AddListener(() => SetLang("en"));

        float savedVol = PlayerPrefs.GetFloat("volume", 1f);
        AudioListener.volume = savedVol;
        if (volumeSlider)
        {
            volumeSlider.value = savedVol;
            volumeSlider.onValueChanged.AddListener(OnVolumeChanged);
        }

        RefreshLangUI();
        gameObject.SetActive(false);
    }

    public void Open()  => gameObject.SetActive(true);
    public void Close() => gameObject.SetActive(false);

    private void SetLang(string lang)
    {
        PlayerPrefs.SetString("lang", lang);
        PlayerPrefs.Save();
        RefreshLangUI();
    }

    private void OnVolumeChanged(float v)
    {
        AudioListener.volume = v;
        PlayerPrefs.SetFloat("volume", v);
        PlayerPrefs.Save();
    }

    private void RefreshLangUI()
    {
        var lang = PlayerPrefs.GetString("lang", "zh");
        if (currentLangLabel) currentLangLabel.text = lang == "zh" ? "中文" : "English";
        if (langZhButton) langZhButton.GetComponent<Image>().color = lang == "zh" ? ActiveBtn : InactiveBtn;
        if (langEnButton) langEnButton.GetComponent<Image>().color = lang == "en" ? ActiveBtn : InactiveBtn;
    }
}
