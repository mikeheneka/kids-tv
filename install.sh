#!/usr/bin/env bash
set -e

echo "=== Installing Kids TV ==="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Install dependencies if not present
echo "--> Installing system packages (mpv, python3-pyqt5)..."
sudo apt-get update
sudo apt-get install -y mpv python3-pyqt5

# Make python script executable
chmod +x "$SCRIPT_DIR/kids_tv.py"

# Symlink to /usr/local/bin
echo "--> Creating /usr/local/bin/watch-tv symlink..."
sudo ln -sf "$SCRIPT_DIR/kids_tv.py" /usr/local/bin/watch-tv

# Install application icon into standard icon directories
echo "--> Installing application icon..."
sudo mkdir -p /usr/local/share/pixmaps
sudo cp "$SCRIPT_DIR/icon.png" /usr/local/share/pixmaps/kids-tv.png
mkdir -p "$HOME/.local/share/icons/hicolor/128x128/apps"
cp "$SCRIPT_DIR/icon.png" "$HOME/.local/share/icons/hicolor/128x128/apps/kids-tv.png"

# Setup Desktop shortcut if ~/Desktop exists
if [ -d "$HOME/Desktop" ]; then
    echo "--> Installing Desktop shortcut..."
    cp "$SCRIPT_DIR/kids-tv.desktop" "$HOME/Desktop/Watch_TV.desktop"
    chmod +x "$HOME/Desktop/Watch_TV.desktop"
    gio set "$HOME/Desktop/Watch_TV.desktop" metadata::trusted true 2>/dev/null || true
fi

# Setup Applications menu shortcut
mkdir -p "$HOME/.local/share/applications"
cp "$SCRIPT_DIR/kids-tv.desktop" "$HOME/.local/share/applications/kids-tv.desktop"
chmod +x "$HOME/.local/share/applications/kids-tv.desktop"

echo "=== Installation Complete! ==="
echo "You can launch the player by clicking 'Watch TV' on your desktop"
echo "or typing 'watch-tv' in any terminal."
