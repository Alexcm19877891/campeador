# Campeador

**Campeador** is a lightweight Windows push-to-talk dictation and translation app powered by [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper).

Hold a mouse button or hotkey, speak, and Campeador will transcribe or translate your speech, then copy it to your clipboard or automatically paste it into the active app.

---

## Features

- Push-to-talk voice recording
- Local Whisper transcription using `faster-whisper`
- CUDA GPU acceleration when available
- Spanish → English translation
- Spanish → Spanish transcription
- English → English transcription
- Auto language detection
- Copy-to-clipboard mode
- Auto-paste mode
- System tray support
- Tray icon changes color by status:
  - Red = idle
  - Green = recording
  - Orange = transcribing
- Configurable trigger key/button
- Persistent settings saved locally

---

## Requirements

- Windows 10 or Windows 11
- Python 3.11 recommended
- NVIDIA GPU recommended for CUDA acceleration
- Microphone

Campeador can fall back to CPU, but GPU mode is strongly recommended for lower latency.

---

## Installation

1. Clone the repository:git clone https://github.com/YOUR_USERNAME/campeador.git
cd campeador
2. Run Install_first.bat so it will install your .venv and dependancies.
3. Launch run_campeador.bat
