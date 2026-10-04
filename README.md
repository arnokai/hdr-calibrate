# HDR Calibration Wizard for Linux (`hdr-calibrate`)

[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Wayland-blue.svg)](#)
[![Toolkit](https://img.shields.io/badge/Toolkit-GTK%204%20%2B%20Cairo-brightgreen.svg)](#)
[![Language](https://img.shields.io/badge/Language-Python%203-yellow.svg)](#)
[![Standards](https://img.shields.io/badge/Standards-HDR10%20%7C%20BT.2020%20%7C%20ST2084-purple.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A lightweight, native **GTK 4 / Wayland** HDR calibration wizard for Linux, modeled directly after the **Windows HDR Calibration** app.

Designed for gaming, video, and 24/7 HDR desktop workflows on compositors such as **Hyprland**, **Gamescope**, **KDE KWin**, and companions like **FlightDeck (Caelestia)**.

---

## 🌟 Why This Exists

When running HDR on Linux, displays can easily look **washed out, artificially dim, or blown out in highlights** if the operating system and tone-mapper do not know the physical luminance boundaries of your panel:
* **Peak White Set Too Low:** Highlights clip early and look like flat, blinding white blobs with zero cloud/sun texture.
* **Peak White Set Too High:** Tone-mapping over-compresses the image, dimming the entire screen.
* **Black Level Misconfigured:** Dark scenes in games suffer from **Black Crush** (shadows turning into flat black ink) or foggy gray haze.

**`hdr-calibrate`** bridges the gap on Linux by giving you a step-by-step visual calibration wizard with real-time vector clipping patterns, hardware EDID auto-detection, and broadcast-grade 10-bit HDR10 video validation.

---

## ✨ Features

* **🔍 Automatic Hardware EDID Telemetry:**
  Reads `/sys/class/drm/*/edid` via `edid-decode` on startup to detect connected displays, CTA-861 Static Metadata blocks, and pre-populates your monitor's native hardware ratings (e.g. LG UltraGear, Samsung Odyssey, Alienware OLED).
* **🎯 4-Step Interactive Calibration Wizard:**
  1. **Minimum Luminance (Black Level Floor):** Pitch-black canvas (`#000000`) with proportional scaling to eliminate black crush while preserving deep contrast.
  2. **Maximum Luminance (Peak Highlights):** 10% centered peak highlight area with real-time clipping bars to find your monitor's hard clipping ceiling.
  3. **Max Full-Frame Average Luminance:** Full-screen white canvas with multi-stage concentric clipping rings and stepping bars to dial in sustained full-frame white.
  4. **SDR Brightness & Saturation Engine:** Interactive desktop application window preview simulating paper-white document brightness alongside a 0%–200% color saturation engine.
* **🎬 Native 10-Bit HDR10 MPV Verification:**
  Includes a built-in generator (`ffmpeg` + `libx265`) creating a 10-bit SMPTE ST 2084 (PQ / BT.2020) test video pattern that can be launched directly via `mpv --vo=gpu-next` in true 10-bit fullscreen.
* **⚡ 1-Click Compositor & Companion Integration:**
  * **FlightDeck (Caelestia):** One-click **"Apply to FlightDeck"** button that automatically writes calibrated values to `~/.config/caelestia/astra-flightdeck.lua`.
  * **Hyprland:** Auto-generated `hyprland.conf` monitor directive with 10-bit color, VRR, and HDR flags.
  * **Export:** Saves structured profiles to `~/.config/hdr-calibration.json`.
* **🖥️ Windowed + Fullscreen (F11):**
  Windowed by default with an instant `F11` shortcut for distraction-free fullscreen test viewing on Wayland.

---

## 📦 Requirements

### Arch Linux / Manjaro / CachyOS
```bash
sudo pacman -S gtk4 python-gobject cairo edid-decode mpv ffmpeg
```

### Fedora
```bash
sudo dnf install gtk4 python3-gobject python3-cairo edid-decode mpv ffmpeg
```

### Ubuntu / Debian (24.04+)
```bash
sudo apt install libgtk-4-dev python3-gi python3-cairo edid-decode mpv ffmpeg
```

---

## 🚀 Quickstart Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/arnokai/hdr-calibrate.git
   cd hdr-calibrate
   ```

2. **Run the installer:**
   ```bash
   ./install.sh
   ```

3. **Launch the wizard:**
   ```bash
   hdr-calibrate
   ```
   *Or search for **"HDR Calibration"** in your application launcher (Rofi, Wofi, etc.).*

---

## 📖 How to Calibrate

| Step | What to Look For | Goal / Sweet Spot |
| :--- | :--- | :--- |
| **Step 1: Min Luminance** | Drag slider until the center emblem just blends into black. | • **OLED:** `0.00 cd/m²`<br>• **IPS / VA LCD:** `0.05`–`0.08 cd/m²` |
| **Step 2: Peak Luminance** | Drag slider until test bars and center emblem clip into white. | Set to display's rated peak nits (e.g. `350` for UltraGear, `600`, `1000`). |
| **Step 3: Average Luminance** | Drag slider until 280–300 bars and middle ring blend into full white. | Match full-frame EDID rating (`~300 cd/m²` for standard LCDs). |
| **Step 4: SDR Desktop** | Adjust paper-white background and color saturation. | • **SDR Brightness:** `80%–100%`<br>• **SDR Saturation:** `100%` (natural) |
| **Summary & Apply** | Click **"Apply to FlightDeck"** or copy your Hyprland snippet. | All tone-mapping values live and applied! |

---

## ⚙️ Uninstallation

To remove `hdr-calibrate` from your system:
```bash
./uninstall.sh
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
Contributions, pull requests, and feedback are welcome!
