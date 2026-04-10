import AVFoundation

/// On-device TTS using AVSpeechSynthesizer.
/// No network calls — instant playback, works offline.
final class TTSService {
    private let synthesizer = AVSpeechSynthesizer()

    /// Persisted toggle (survives app restarts).
    var isEnabled: Bool {
        get { UserDefaults.standard.object(forKey: "tts_enabled") as? Bool ?? true }
        set { UserDefaults.standard.set(newValue, forKey: "tts_enabled") }
    }

    init() {
        // Allow TTS to play over silent-mode / alongside other audio
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio, options: .duckOthers)
        try? AVAudioSession.sharedInstance().setActive(true)
    }

    /// Speak *text* using the app-level language setting ("lang" in UserDefaults).
    func speak(_ text: String) {
        guard isEnabled, !text.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        synthesizer.stopSpeaking(at: .immediate)

        let appLang = UserDefaults.standard.string(forKey: "lang") ?? "zh"
        let bcp47 = appLang == "zh" ? "zh-CN" : "en-US"

        let utterance = AVSpeechUtterance(string: String(text.prefix(300)))
        utterance.voice = AVSpeechSynthesisVoice(language: bcp47)
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.9   // slightly slower — clearer for mystery text
        utterance.pitchMultiplier = 0.95                             // slightly deeper — suits the DM persona
        synthesizer.speak(utterance)
    }

    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
    }
}
