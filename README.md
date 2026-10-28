# Kids TV - HDHomeRun TV Player for Raspberry Pi

A lightweight, child-friendly Live TV player designed for Raspberry Pi (and Linux desktops) that streams directly from a local **SiliconDust HDHomeRun** networked TV tuner.

Built with **Python 3**, **PyQt5**, and an embedded **mpv** playback engine with hardware acceleration.

---

## Features

- **Kid-Friendly Interface**: Extra-large buttons, clean typography, and bright visual feedback designed for young children who aren't accustomed to complex desktop menus.
- **One-Click Channel Tuning**: Scroll through channels and tap/click once to tune and start playback instantly.
- **Auto-Discovery**: Automatically discovers HDHomeRun tuners on the local network (with local caching for instant launch).
- **Signal Quality Awareness**:
  - **`⚡ Live Signal` Tab**: Filters automatically to channels with verified live antenna broadcast signal.
  - **`⭐ Starred` Tab**: Easy one-click channel favoriting.
  - **`📺 All` Tab**: Browse full 70+ channel lineup.
  - Real-time status indicators alert when a channel has no antenna signal.
- **Child-Safe Controls**:
  - High-visibility **Mute** button (bright red when muted, green when unmuted).
  - Discrete `🔉 -` and `🔊 +` volume buttons alongside a smooth slider.
  - Big `◀ Prev Channel` and `Next Channel ▶` surfing buttons.
- **Fullscreen Mode**: Double-click the video or tap `⛶ Fullscreen` (press `Esc` or `F` to return).
- **Single-Instance Protection**: Clicking the desktop icon multiple times won't spawn conflicting player processes or lock up multiple tuners.
- **VNC & Remote Desktop Friendly**: Works seamlessly on local monitors and over VNC (`wayvnc`).

---

## Requirements

- **Raspberry Pi 4 or 5** (or any Linux PC running Raspberry Pi OS, Debian, or Ubuntu).
- **SiliconDust HDHomeRun** on the local network with an OTA antenna connected.
- Installed packages:
  - `python3`
  - `python3-pyqt5`
  - `mpv`

---

## Installation

Clone the repository to your Raspberry Pi:

```bash
git clone https://github.com/<your-username>/kids-tv.git ~/apps/kids-tv
cd ~/apps/kids-tv
./install.sh
```

The installer will:
1. Install required system packages (`mpv`, `python3-pyqt5`).
2. Add a **Watch TV** icon to your Raspberry Pi Desktop.
3. Register the app in the system Applications menu under **Audio & Video**.
4. Create a system command `watch-tv` in `/usr/local/bin`.

---

## Keyboard Shortcuts

| Key | Action |
| --- | --- |
| `Space` or `M` | Toggle Mute |
| `Up` / `Left` | Previous Channel |
| `Down` / `Right` | Next Channel |
| `F` or `Esc` | Toggle Fullscreen |
| `Double Click` | Toggle Fullscreen |

---

## Configuration & State

Settings, last-watched channel, cached channel lineups, and starred favorites are automatically persisted in:
```
~/.config/kids-tv/
├── channels.json    # Cached HDHomeRun lineup
├── favorites.json   # Starred channel list
└── state.json       # Last channel, volume, and mute state
```

---

## License

MIT License. Feel free to modify and share!
