#!/usr/bin/env bash
# ==============================================================================
# hdr-calibrate uninstaller script
# ==============================================================================
set -e

BIN_FILE="${HOME}/.local/bin/hdr-calibrate"
SHARE_DIR="${HOME}/.local/share/hdr-calibrate"
APP_FILE="${HOME}/.local/share/applications/hdr-calibrate.desktop"

echo "Uninstalling HDR Calibration Wizard..."

rm -f "${BIN_FILE}"
rm -rf "${SHARE_DIR}"
rm -f "${APP_FILE}"

if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
fi

echo "✓ Successfully removed hdr-calibrate."
