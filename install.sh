#!/usr/bin/env bash
# ==============================================================================
# hdr-calibrate installer script for Linux (Arch, Fedora, Debian/Ubuntu)
# ==============================================================================
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
SHARE_DIR="${HOME}/.local/share/hdr-calibrate"
APP_DIR="${HOME}/.local/share/applications"

echo "=================================================="
echo "    Installing HDR Calibration Wizard for Linux   "
echo "=================================================="

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "❌ Error: python3 is not installed. Please install Python 3."
    exit 1
fi

# Check GTK 4 & PyGObject
echo "• Checking GTK 4 and PyGObject..."
if ! python3 -c "import gi; gi.require_version('Gtk', '4.0'); from gi.repository import Gtk" &>/dev/null; then
    echo "❌ Error: GTK 4 or PyGObject is missing."
    echo "   Arch Linux: sudo pacman -S gtk4 python-gobject"
    echo "   Fedora:     sudo dnf install gtk4 python3-gobject"
    echo "   Ubuntu:     sudo apt install libgtk-4-dev python3-gi"
    exit 1
fi

# Check edid-decode
if ! command -v edid-decode &>/dev/null; then
    echo "⚠️ Warning: edid-decode not found in PATH. Display telemetry may be limited."
    echo "   Install via: sudo pacman -S edid-decode"
fi

# Create directories
mkdir -p "${BIN_DIR}" "${SHARE_DIR}" "${APP_DIR}"

# Check or generate test pattern video
if [ ! -f "${REPO_DIR}/hdr10_test_pattern.mp4" ]; then
    echo "• Generating 10-bit HDR10 test pattern video via ffmpeg..."
    python3 "${REPO_DIR}/generate_pattern.py" || true
fi

if [ -f "${REPO_DIR}/hdr10_test_pattern.mp4" ]; then
    cp -f "${REPO_DIR}/hdr10_test_pattern.mp4" "${SHARE_DIR}/hdr10_test_pattern.mp4"
    echo "✓ Test pattern video installed to ${SHARE_DIR}"
fi

# Install executable
chmod +x "${REPO_DIR}/hdr_calibrate.py"
cp -f "${REPO_DIR}/hdr_calibrate.py" "${BIN_DIR}/hdr-calibrate"
chmod +x "${BIN_DIR}/hdr-calibrate"
echo "✓ Executable installed to ${BIN_DIR}/hdr-calibrate"

# Install Desktop Entry
cp -f "${REPO_DIR}/hdr-calibrate.desktop" "${APP_DIR}/hdr-calibrate.desktop"
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${APP_DIR}" 2>/dev/null || true
fi
echo "✓ Desktop launcher installed to ${APP_DIR}/hdr-calibrate.desktop"

echo ""
echo "🎉 Installation complete!"
echo "You can now run: hdr-calibrate"
echo "Or launch 'HDR Calibration' from your application menu."
