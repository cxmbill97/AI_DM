// Entry scene — validates session then routes to MainMenu or Login.
// Mirrors the startup logic in ios/AIDungeonMaster/App/AIDungeonMasterApp.swift
// and AuthViewModel.validateSession().
using UnityEngine;
using Cysharp.Threading.Tasks;

public class BootController : MonoBehaviour
{
    private async void Start()
    {
        // Give singletons one frame to Awake
        await UniTask.Yield();

        var valid = await AuthManager.Instance.ValidateSession();
        SceneLoader.LoadScene(valid ? "MainMenu" : "Login");
    }
}
