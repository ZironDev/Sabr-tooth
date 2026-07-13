# 🦷 sabr‑tooth  
### *YouTube audio extraction that exploits SABR (Server‑Aided Bandwidth Regulation) – and will get patched soon ™*

[![Warning](https://img.shields.io/badge/status-experimental-red)](https://github.com/yourusername/sabr-tooth)
[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)

` sabr‑tooth` is a Python script that extracts **direct audio URLs** from YouTube videos by mimicking official clients (WEB and ANDROID) and handling the newer **SABR** streaming endpoints. It prefers the highest quality Opus and M4A formats, and optionally converts the stream to MP3, M4A, or HLS using `ffmpeg`.

> ⚠️ **This is a cat‑and‑mouse game** – YouTube changes its API and signature logic frequently. This script works **today**, but may break tomorrow without warning. Use it for personal/educational purposes.

---

## ✨ Features

- **Multi‑client spoofing** – tries `WEB` and `ANDROID` to get a working player response.
- **Intelligent format selection** – prefers lossy Opus / M4A with the best bitrate (see `AUDIO_PRIORITY`).
- **SABR support** – falls back to `serverAbrStreamingUrl` when direct formats are unavailable.
- **Automatic signature decryption** – handles `signatureCipher` fields (basic reverse + `&sig` injection).
- **Optional conversion** – uses `ffmpeg` to convert to:
  - **MP3** (128 kbps)
  - **M4A** (AAC, 128 kbps)
  - **HLS** (adaptive stream with `.m3u8` and `.ts` segments)
- **Rich console output** – shows title, artist, duration, format, bitrate, and the extracted URL.

---

## 📦 Requirements

- **Python 3.6+**
- [`requests`](https://pypi.org/project/requests/)
- **ffmpeg** – *optional*, only needed for `--convert` (place `ffmpeg.exe` in the script folder or in your `PATH`).

Install the Python dependency:
```bash
pip install requests
