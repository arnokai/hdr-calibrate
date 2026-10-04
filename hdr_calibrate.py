#!/usr/bin/env python3
"""
Linux HDR Calibration Wizard (GTK 4 / Wayland)
Modeled after Windows HDR Calibration with display EDID auto-detection,
live clipping test patterns, and export options.
"""

import sys
import os
import json
import subprocess
import re
import math
from pathlib import Path

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango

# --- EDID & Display Detection ---

def detect_displays():
    """Detect all connected DRM displays and their HDR metadata."""
    displays = []
    drm_path = Path("/sys/class/drm")
    if not drm_path.exists():
        return displays

    for card in sorted(drm_path.glob("card*-*")):
        status_file = card / "status"
        if not status_file.exists():
            continue
        try:
            status = status_file.read_text().strip()
        except Exception:
            continue

        if status != "connected":
            continue

        connector = card.name.split("-", 1)[1] if "-" in card.name else card.name
        edid_file = card / "edid"
        disp_info = {
            "connector": connector,
            "card_path": str(card),
            "name": connector,
            "is_hdr": False,
            "max_nits": 350.0,
            "max_avg_nits": 300.0,
            "min_nits": 0.05,
            "raw_details": "",
            "resolution": "Unknown",
        }

        if edid_file.exists():
            try:
                edid_bytes = edid_file.read_bytes()
                if edid_bytes:
                    res = subprocess.run(
                        ["/usr/sbin/edid-decode"],
                        input=edid_bytes,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                    output = res.stdout.decode("utf-8", errors="replace")
                    disp_info["raw_details"] = output

                    # Name
                    name_match = re.search(r"Display Product Name: '([^']+)'", output)
                    if name_match:
                        disp_info["name"] = name_match.group(1).strip()

                    # Resolution
                    res_match = re.search(r"DTD \d+:\s+(\d+x\d+)\s+([\d.]+)\s*Hz", output)
                    if res_match:
                        disp_info["resolution"] = f"{res_match.group(1)} @ {float(res_match.group(2)):.0f}Hz"

                    # HDR Metadata
                    if "HDR Static Metadata Data Block" in output:
                        disp_info["is_hdr"] = True

                    max_match = re.search(r"Desired content max luminance: \d+ \(([\d.]+) cd/m\^2\)", output)
                    if max_match:
                        disp_info["max_nits"] = float(max_match.group(1))

                    max_avg_match = re.search(r"Desired content max frame-average luminance: \d+ \(([\d.]+) cd/m\^2\)", output)
                    if max_avg_match:
                        disp_info["max_avg_nits"] = float(max_avg_match.group(1))

                    min_match = re.search(r"Desired content min luminance: \d+ \(([\d.]+) cd/m\^2\)", output)
                    if min_match:
                        disp_info["min_nits"] = float(min_match.group(1))

            except Exception as e:
                disp_info["raw_details"] = f"Error reading EDID: {e}"

        displays.append(disp_info)

    # Sort so HDR displays (e.g. UltraGear) are preferred
    displays.sort(key=lambda d: (not d["is_hdr"], "eDP" in d["connector"]))
    return displays


# --- CSS Theme ---

CSS_DATA = """
window {
    background-color: #11141b;
    color: #e6edf3;
    font-family: system-ui, -apple-system, sans-serif;
}

headerbar {
    background-color: #171b24;
    border-bottom: 1px solid #232836;
    color: #ffffff;
}

.card {
    background-color: #191d28;
    border: 1px solid #282e40;
    border-radius: 12px;
    padding: 18px;
}

.card-title {
    font-size: 17px;
    font-weight: 700;
    color: #58a6ff;
}

.value-label {
    font-size: 26px;
    font-weight: 800;
    color: #38bdf8;
    font-family: monospace;
}

.step-indicator {
    font-size: 13px;
    font-weight: 600;
    color: #8b949e;
}

.pattern-container {
    background-color: #0b0d13;
    border: 1px solid #242938;
    border-radius: 12px;
}

.btn-primary {
    background: #2563eb;
    color: white;
    font-weight: 600;
    border-radius: 8px;
    padding: 8px 18px;
    border: none;
}
.btn-primary:hover {
    background: #1d4ed8;
}

.btn-secondary {
    background: #232938;
    color: #e6edf3;
    font-weight: 600;
    border-radius: 8px;
    padding: 8px 18px;
    border: 1px solid #323b50;
}
.btn-secondary:hover {
    background: #2f374a;
}

.preset-btn {
    background: #1c2230;
    color: #8bc0f8;
    border: 1px solid #2f384f;
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
}
.preset-btn:hover {
    background: #2b354c;
}
"""

# --- Main Application Window ---

class HDRCalibrateWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="HDR Calibration Wizard")
        self.set_default_size(1020, 720)

        # State
        self.displays = detect_displays()
        self.current_display = self.displays[0] if self.displays else {
            "name": "Default Display", "connector": "Unknown", "is_hdr": True,
            "min_nits": 0.08, "max_nits": 350.0, "max_avg_nits": 300.0, "resolution": "1920x1080"
        }

        # Calibrated values
        self.val_min = self.current_display["min_nits"]
        if self.val_min > 0.3:
            self.val_min = 0.08
        self.val_max = max(self.current_display["max_nits"], 300.0)
        self.val_max_avg = self.current_display["max_avg_nits"]
        self.val_sdr_brightness = 100
        self.val_sdr_saturation = 100

        self.current_step = 0
        self.total_steps = 6  # 0: Welcome, 1: Min, 2: Max, 3: Avg, 4: SDR, 5: Summary
        self.is_fullscreen = False

        self.setup_css()
        self.setup_ui()
        self.setup_shortcuts()

    def setup_css(self):
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS_DATA.encode("utf-8"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def setup_shortcuts(self):
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True
        elif keyval == Gdk.KEY_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
            return True
        return False

    def toggle_fullscreen(self, *args):
        if self.is_fullscreen:
            self.unfullscreen()
            self.is_fullscreen = False
            self.btn_fs.set_label("Fullscreen (F11)")
        else:
            self.fullscreen()
            self.is_fullscreen = True
            self.btn_fs.set_label("Exit Fullscreen (Esc)")

    def launch_mpv_verification(self, *args):
        search_paths = [
            Path(__file__).resolve().parent / "hdr10_test_pattern.mp4",
            Path.home() / ".local" / "share" / "hdr-calibrate" / "hdr10_test_pattern.mp4",
            Path("/usr/share/hdr-calibrate/hdr10_test_pattern.mp4"),
        ]
        video_path = next((p for p in search_paths if p.exists()), None)
        if not video_path:
            if hasattr(self, "lbl_status"):
                self.lbl_status.set_markup("<span color='#f43f5e'>Error: hdr10_test_pattern.mp4 not found. Please run generate_pattern.py first.</span>")
            return
        cmd = [
            "mpv",
            "--vo=gpu-next",
            "--target-colorspace-hint=yes",
            "--loop=inf",
            "--fullscreen",
            str(video_path),
        ]
        try:
            subprocess.Popen(cmd)
            if hasattr(self, "lbl_status"):
                self.lbl_status.set_markup(
                    "<span color='#10b981'>🎬 Launched MPV with true 10-bit HDR10 test pattern! (Press <b>q</b> or <b>Esc</b> in MPV to exit)</span>"
                )
        except Exception as e:
            if hasattr(self, "lbl_status"):
                self.lbl_status.set_markup(f"<span color='#f43f5e'>Error launching MPV: {e}</span>")

    def setup_ui(self):
        # Header Bar
        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        # Monitor selector dropdown
        disp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        disp_label = Gtk.Label(label="Display:")
        disp_label.add_css_class("dim-label")
        disp_box.append(disp_label)

        disp_names = [f"{d['name']} ({d['connector']})" for d in self.displays]
        if not disp_names:
            disp_names = ["Generic Display"]

        string_list = Gtk.StringList.new(disp_names)
        self.combo_disp = Gtk.DropDown.new(string_list, None)
        self.combo_disp.set_selected(0)
        self.combo_disp.connect("notify::selected", self.on_display_changed)
        disp_box.append(self.combo_disp)
        header.pack_start(disp_box)

        # MPV Test Pattern Button
        self.btn_mpv = Gtk.Button(label="🎬 Verify in MPV")
        self.btn_mpv.add_css_class("btn-secondary")
        self.btn_mpv.connect("clicked", self.launch_mpv_verification)
        header.pack_end(self.btn_mpv)

        # Fullscreen button
        self.btn_fs = Gtk.Button(label="Fullscreen (F11)")
        self.btn_fs.add_css_class("btn-secondary")
        self.btn_fs.connect("clicked", self.toggle_fullscreen)
        header.pack_end(self.btn_fs)

        # Main Layout
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_child(main_vbox)

        # Stack for wizard pages
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_vexpand(True)
        main_vbox.append(self.stack)

        # Build Pages
        self.build_page_welcome()
        self.build_page_min()
        self.build_page_max()
        self.build_page_avg()
        self.build_page_sdr()
        self.build_page_summary()

        # Bottom Navigation Bar
        nav_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        nav_bar.set_margin_top(12)
        nav_bar.set_margin_bottom(12)
        nav_bar.set_margin_start(24)
        nav_bar.set_margin_end(24)

        self.btn_back = Gtk.Button(label="Back")
        self.btn_back.add_css_class("btn-secondary")
        self.btn_back.connect("clicked", self.on_back_clicked)
        nav_bar.append(self.btn_back)

        self.lbl_step = Gtk.Label(label="Step 1 of 5")
        self.lbl_step.add_css_class("step-indicator")
        self.lbl_step.set_hexpand(True)
        self.lbl_step.set_halign(Gtk.Align.CENTER)
        nav_bar.append(self.lbl_step)

        self.btn_next = Gtk.Button(label="Next")
        self.btn_next.add_css_class("btn-primary")
        self.btn_next.connect("clicked", self.on_next_clicked)
        nav_bar.append(self.btn_next)

        main_vbox.append(nav_bar)
        self.update_nav()

    def on_display_changed(self, dropdown, param):
        idx = dropdown.get_selected()
        if 0 <= idx < len(self.displays):
            self.current_display = self.displays[idx]
            self.val_min = min(self.current_display["min_nits"], 0.2)
            self.val_max = max(self.current_display["max_nits"], 300.0)
            self.val_max_avg = self.current_display["max_avg_nits"]
            self.update_display_info_labels()
            self.slider_min.set_value(self.val_min)
            self.slider_max.set_value(self.val_max)
            self.slider_avg.set_value(self.val_max_avg)

    # --- Page 0: Welcome ---
    def build_page_welcome(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(30)
        box.set_margin_bottom(20)

        title = Gtk.Label(label="HDR Calibration Wizard for Linux")
        title.set_markup("<span size='xx-large' weight='bold'>HDR Calibration Wizard</span>")
        box.append(title)

        subtitle = Gtk.Label(label="Calibrate peak highlights, black floor, and tone mapping for accurate HDR gaming and video.")
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        # Hardware Info Card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")

        card_header = Gtk.Label()
        card_header.set_markup("<b>Target Display Telemetry</b>")
        card_header.set_halign(Gtk.Align.START)
        card.append(card_header)

        self.lbl_disp_name = Gtk.Label()
        self.lbl_disp_name.set_halign(Gtk.Align.START)
        card.append(self.lbl_disp_name)

        self.lbl_disp_specs = Gtk.Label()
        self.lbl_disp_specs.set_halign(Gtk.Align.START)
        card.append(self.lbl_disp_specs)

        box.append(card)

        # Steps Overview Card
        steps_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        steps_card.add_css_class("card")
        steps_header = Gtk.Label(label="Calibration Steps Ahead:")
        steps_header.set_halign(Gtk.Align.START)
        steps_header.set_markup("<b>What You Will Calibrate:</b>")
        steps_card.append(steps_header)

        steps_text = (
            "1. <b>Minimum Luminance:</b> Adjust black floor to avoid black crush and milky grays.\n"
            "2. <b>Maximum Luminance:</b> Tune peak white highlights to prevent highlight clipping.\n"
            "3. <b>Max Frame-Average:</b> Adjust sustained full-screen white brightness.\n"
            "4. <b>SDR Brightness & Saturation:</b> Balance desktop colors so SDR windows look natural."
        )
        lbl_steps_text = Gtk.Label()
        lbl_steps_text.set_markup(steps_text)
        lbl_steps_text.set_halign(Gtk.Align.START)
        steps_card.append(lbl_steps_text)
        box.append(steps_card)

        # F11 Hint
        hint = Gtk.Label()
        hint.set_markup("<i>Tip: Press <b>F11</b> at any time during calibration to view test patterns in full-screen.</i>")
        box.append(hint)

        self.stack.add_named(box, "step_welcome")
        self.update_display_info_labels()

    def update_display_info_labels(self):
        d = self.current_display
        hdr_badge = "<span background='#10b981' color='white' weight='bold'> HDR10 </span>" if d.get("is_hdr") else "SDR / Emulated"
        self.lbl_disp_name.set_markup(f"<b>Monitor:</b> {d['name']} ({d['connector']})  {hdr_badge}")
        self.lbl_disp_specs.set_markup(
            f"<b>Resolution:</b> {d['resolution']}  |  "
            f"<b>EDID Peak:</b> {d['max_nits']:.1f} cd/m²  |  "
            f"<b>EDID Full-Frame:</b> {d['max_avg_nits']:.1f} cd/m²  |  "
            f"<b>EDID Black Floor:</b> {d['min_nits']:.3f} cd/m²"
        )

    # --- Page 1: Min Luminance ---
    def build_page_min(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(30)
        box.set_margin_end(30)
        box.set_margin_top(16)
        box.set_margin_bottom(10)

        # Title & instructions
        lbl_title = Gtk.Label()
        lbl_title.set_markup("<span size='large' weight='bold'>Step 1: Minimum Luminance (Black Level Floor)</span>")
        lbl_title.set_halign(Gtk.Align.START)
        box.append(lbl_title)

        lbl_desc = Gtk.Label(label="Drag the slider until the center symbol and the dark patches just barely blend into the black background.")
        lbl_desc.set_halign(Gtk.Align.START)
        box.append(lbl_desc)

        # Drawing Canvas
        self.canvas_min = Gtk.DrawingArea()
        self.canvas_min.set_vexpand(True)
        self.canvas_min.add_css_class("pattern-container")
        self.canvas_min.set_draw_func(self.draw_min_pattern)
        box.append(self.canvas_min)

        # Controls Card
        ctrl_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ctrl_card.add_css_class("card")

        val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        lbl_txt = Gtk.Label(label="Black Level Floor:")
        lbl_txt.add_css_class("card-title")
        val_row.append(lbl_txt)

        self.lbl_min_val = Gtk.Label(label=f"{self.val_min:.3f} cd/m²")
        self.lbl_min_val.add_css_class("value-label")
        val_row.append(self.lbl_min_val)

        # Preset buttons
        presets_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        presets_box.set_hexpand(True)
        presets_box.set_halign(Gtk.Align.END)

        for label, pval in [("0.00 (OLED)", 0.0), ("0.05 (VA/IPS)", 0.05), ("0.08 (Sweet Spot)", 0.08), ("0.15 (Safe)", 0.15)]:
            b = Gtk.Button(label=label)
            b.add_css_class("preset-btn")
            b.connect("clicked", lambda btn, v=pval: self.slider_min.set_value(v))
            presets_box.append(b)

        val_row.append(presets_box)
        ctrl_card.append(val_row)

        self.slider_min = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 0.50, 0.005)
        self.slider_min.set_value(self.val_min)
        self.slider_min.connect("value-changed", self.on_min_slider_changed)
        ctrl_card.append(self.slider_min)

        box.append(ctrl_card)
        self.stack.add_named(box, "step_min")

    def on_min_slider_changed(self, scale):
        self.val_min = scale.get_value()
        self.lbl_min_val.set_label(f"{self.val_min:.3f} cd/m²")
        self.canvas_min.queue_draw()

    def draw_min_pattern(self, area, cr, width, height):
        # Pure Black Background
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.paint()

        cx = width / 2.0
        cy = height / 2.0

        # Pattern brightness scales strictly with slider value:
        # At 0.00 cd/m²: factor is 0.0, emblem is pure black and 100% blended into the background.
        factor = self.val_min * 0.45

        # Stepping comparison patches
        bar_w = 70
        bar_h = 36
        start_x = cx - (bar_w * 2.5 + 20)
        y_pos = cy + 85

        values = [0.00, 0.02, 0.05, 0.08, 0.15]
        labels = ["0.00", "0.02", "0.05", "0.08", "0.15"]
        for i, (v, lbl) in enumerate(zip(values, labels)):
            bx = start_x + i * (bar_w + 10)
            # Reference patch luminance matches the emblem scaling formula
            lum = v * 0.45
            cr.new_path()
            cr.set_source_rgb(lum, lum, lum)
            cr.rectangle(bx, y_pos, bar_w, bar_h)
            cr.fill()

            # text label
            cr.new_path()
            cr.set_source_rgb(0.4, 0.4, 0.4)
            cr.select_font_face("monospace", 0, 0)
            cr.set_font_size(11)
            cr.move_to(bx + 12, y_pos + bar_h + 16)
            cr.show_text(lbl)
            cr.new_path()

        # Center Test Symbol: A segmented calibration emblem
        cr.save()
        cr.translate(cx, cy - 40)

        # Outer ring
        cr.new_path()
        cr.set_source_rgb(factor * 0.7, factor * 0.7, factor * 0.7)
        cr.set_line_width(4)
        cr.arc(0, 0, 50, 0, 2 * math.pi)
        cr.stroke()

        # Inner cross
        cr.new_path()
        cr.set_source_rgb(factor * 1.0, factor * 1.0, factor * 1.0)
        cr.set_line_width(6)
        cr.move_to(-35, 0)
        cr.line_to(35, 0)
        cr.move_to(0, -35)
        cr.line_to(0, 35)
        cr.stroke()

        # Center diamond
        cr.new_path()
        cr.set_source_rgb(factor * 1.2, factor * 1.2, factor * 1.2)
        cr.move_to(0, -15)
        cr.line_to(15, 0)
        cr.line_to(0, 15)
        cr.line_to(-15, 0)
        cr.close_path()
        cr.fill()

        cr.restore()
        cr.new_path()

    # --- Page 2: Max Luminance ---
    def build_page_max(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(30)
        box.set_margin_end(30)
        box.set_margin_top(16)
        box.set_margin_bottom(10)

        lbl_title = Gtk.Label()
        lbl_title.set_markup("<span size='large' weight='bold'>Step 2: Maximum Luminance (Peak White Highlights)</span>")
        lbl_title.set_halign(Gtk.Align.START)
        box.append(lbl_title)

        lbl_desc = Gtk.Label(label="Drag the slider until the center symbol and bright test bars clip completely into solid white.")
        lbl_desc.set_halign(Gtk.Align.START)
        box.append(lbl_desc)

        # Drawing Canvas
        self.canvas_max = Gtk.DrawingArea()
        self.canvas_max.set_vexpand(True)
        self.canvas_max.add_css_class("pattern-container")
        self.canvas_max.set_draw_func(self.draw_max_pattern)
        box.append(self.canvas_max)

        # Controls Card
        ctrl_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ctrl_card.add_css_class("card")

        val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        lbl_txt = Gtk.Label(label="Peak Luminance:")
        lbl_txt.add_css_class("card-title")
        val_row.append(lbl_txt)

        self.lbl_max_val = Gtk.Label(label=f"{self.val_max:.1f} cd/m²")
        self.lbl_max_val.add_css_class("value-label")
        val_row.append(self.lbl_max_val)

        # Preset buttons
        presets_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        presets_box.set_hexpand(True)
        presets_box.set_halign(Gtk.Align.END)

        for label, pval in [("300 (EDID)", 301.8), ("350 (UltraGear)", 350.0), ("400 (HDR400)", 400.0), ("600", 600.0), ("1000", 1000.0)]:
            b = Gtk.Button(label=label)
            b.add_css_class("preset-btn")
            b.connect("clicked", lambda btn, v=pval: self.slider_max.set_value(v))
            presets_box.append(b)

        val_row.append(presets_box)
        ctrl_card.append(val_row)

        self.slider_max = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100.0, 1000.0, 5.0)
        self.slider_max.set_value(self.val_max)
        self.slider_max.connect("value-changed", self.on_max_slider_changed)
        ctrl_card.append(self.slider_max)

        box.append(ctrl_card)
        self.stack.add_named(box, "step_max")

    def on_max_slider_changed(self, scale):
        self.val_max = scale.get_value()
        self.lbl_max_val.set_label(f"{self.val_max:.1f} cd/m²")
        self.canvas_max.queue_draw()

    def draw_max_pattern(self, area, cr, width, height):
        # Neutral Dark Background
        cr.set_source_rgb(0.08, 0.09, 0.12)
        cr.paint()

        cx = width / 2.0
        cy = height / 2.0

        # 10% Highlight Window (Centered Box)
        win_w = min(width * 0.55, 460)
        win_h = min(height * 0.65, 340)
        win_x = cx - win_w / 2.0
        win_y = cy - win_h / 2.0

        # Solid Peak White background inside window
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.rectangle(win_x, win_y, win_w, win_h)
        cr.fill()

        # Stepping Bars inside peak window
        # When user's slider exceeds a threshold, the bar clips into pure white (1.0)
        threshold = self.val_max
        bar_w = 60
        bar_h = 28
        bar_y = win_y + win_h - 60
        bar_start_x = cx - (bar_w * 2.5 + 20)

        nits_steps = [280, 320, 350, 400, 450]
        for i, target_nits in enumerate(nits_steps):
            bx = bar_start_x + i * (bar_w + 10)
            if threshold >= target_nits:
                shade = 1.0  # Clipped into solid white!
            else:
                diff = (target_nits - threshold) / 200.0
                shade = max(0.85, 1.0 - diff)

            cr.set_source_rgb(shade, shade, shade)
            cr.rectangle(bx, bar_y, bar_w, bar_h)
            cr.fill()

            cr.set_source_rgb(0.2, 0.2, 0.2)
            cr.select_font_face("monospace", 0, 0)
            cr.set_font_size(10)
            cr.move_to(bx + 12, bar_y + bar_h + 14)
            cr.show_text(f"{target_nits}")
            cr.new_path()

        # Central Test Symbol (Sun / Shield)
        # Target: Clips at around 350 nits
        clip_level = 350.0
        if threshold >= clip_level:
            symbol_shade = 1.0  # Disappears into white!
        else:
            diff = (clip_level - threshold) / 300.0
            symbol_shade = max(0.70, 1.0 - diff)

        cr.save()
        cr.translate(cx, win_y + 110)

        # Draw Sun / Rays
        cr.new_path()
        cr.set_source_rgb(symbol_shade, symbol_shade, symbol_shade)
        cr.set_line_width(5)
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            cr.move_to(math.cos(rad) * 35, math.sin(rad) * 35)
            cr.line_to(math.cos(rad) * 52, math.sin(rad) * 52)
        cr.stroke()

        # Center circle
        cr.new_path()
        cr.arc(0, 0, 24, 0, 2 * math.pi)
        cr.fill()

        cr.restore()
        cr.new_path()

    # --- Page 3: Max Full-Frame (Average) Luminance ---
    def build_page_avg(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(30)
        box.set_margin_end(30)
        box.set_margin_top(16)
        box.set_margin_bottom(10)

        lbl_title = Gtk.Label()
        lbl_title.set_markup("<span size='large' weight='bold'>Step 3: Max Full-Frame Luminance (Average Luminance)</span>")
        lbl_title.set_halign(Gtk.Align.START)
        box.append(lbl_title)

        # In-app step guidance card
        guide_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        guide_card.add_css_class("card")
        
        lbl_what = Gtk.Label()
        lbl_what.set_markup("<b>• What to do:</b> Drag the slider until the <b>280 and 300</b> comparison bars and the center rings blend into the white screen.")
        lbl_what.set_halign(Gtk.Align.START)
        guide_card.append(lbl_what)

        lbl_rec = Gtk.Label()
        lbl_rec.set_markup("<b>• Recommended for LG UltraGear:</b> Click the <b>300 (EDID UltraGear)</b> preset button (hardware rating is 301.8 cd/m²).")
        lbl_rec.set_halign(Gtk.Align.START)
        guide_card.append(lbl_rec)

        box.append(guide_card)

        # Drawing Canvas
        self.canvas_avg = Gtk.DrawingArea()
        self.canvas_avg.set_vexpand(True)
        self.canvas_avg.add_css_class("pattern-container")
        self.canvas_avg.set_draw_func(self.draw_avg_pattern)
        box.append(self.canvas_avg)

        # Controls Card
        ctrl_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ctrl_card.add_css_class("card")

        val_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        lbl_txt = Gtk.Label(label="Full-Frame White Level:")
        lbl_txt.add_css_class("card-title")
        val_row.append(lbl_txt)

        self.lbl_avg_val = Gtk.Label(label=f"{self.val_max_avg:.1f} cd/m²")
        self.lbl_avg_val.add_css_class("value-label")
        val_row.append(self.lbl_avg_val)

        presets_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        presets_box.set_hexpand(True)
        presets_box.set_halign(Gtk.Align.END)

        for label, pval in [("200 (OLED ABL)", 200.0), ("300 (EDID UltraGear)", 301.8), ("350", 350.0), ("400", 400.0)]:
            b = Gtk.Button(label=label)
            b.add_css_class("preset-btn")
            b.connect("clicked", lambda btn, v=pval: self.slider_avg.set_value(v))
            presets_box.append(b)

        val_row.append(presets_box)
        ctrl_card.append(val_row)

        self.slider_avg = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 100.0, 600.0, 5.0)
        self.slider_avg.set_value(self.val_max_avg)
        self.slider_avg.connect("value-changed", self.on_avg_slider_changed)
        ctrl_card.append(self.slider_avg)

        box.append(ctrl_card)
        self.stack.add_named(box, "step_avg")

    def on_avg_slider_changed(self, scale):
        self.val_max_avg = scale.get_value()
        self.lbl_avg_val.set_label(f"{self.val_max_avg:.1f} cd/m²")
        self.canvas_avg.queue_draw()

    def draw_avg_pattern(self, area, cr, width, height):
        # 100% Full-Frame White canvas
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.paint()

        cx = width / 2.0
        cy = height / 2.0
        threshold = self.val_max_avg

        # Stepping comparison bars across full-frame white
        nits_steps = [180, 240, 280, 320, 360, 420]
        bar_w = 68
        bar_h = 32
        start_x = cx - (bar_w * len(nits_steps) + 12 * (len(nits_steps) - 1)) / 2.0
        y_bars = cy + 90

        for i, target_nits in enumerate(nits_steps):
            bx = start_x + i * (bar_w + 12)
            if threshold >= target_nits:
                shade = 1.0  # Clipped completely into full white!
            else:
                diff = (target_nits - threshold) / 250.0
                shade = max(0.55, 1.0 - diff * 0.45)

            cr.new_path()
            cr.set_source_rgb(shade, shade, shade)
            cr.rectangle(bx, y_bars, bar_w, bar_h)
            cr.fill()

            # Nits label below each bar
            cr.new_path()
            cr.set_source_rgb(0.25, 0.25, 0.25)
            cr.select_font_face("monospace", 0, 0)
            cr.set_font_size(11)
            cr.move_to(bx + 14, y_bars + bar_h + 16)
            cr.show_text(f"{target_nits}")
            cr.new_path()

        # Multi-Ring Central Calibration Emblem (Clips in stages)
        cr.save()
        cr.translate(cx, cy - 45)

        # Outer ring: targets 260 nits
        if threshold >= 260.0:
            outer_shade = 1.0
        else:
            diff = (260.0 - threshold) / 220.0
            outer_shade = max(0.60, 1.0 - diff * 0.45)

        cr.new_path()
        cr.set_source_rgb(outer_shade, outer_shade, outer_shade)
        cr.set_line_width(4)
        cr.arc(0, 0, 65, 0, 2 * math.pi)
        cr.stroke()

        # Middle ring: targets 300 nits (LG UltraGear reference)
        if threshold >= 300.0:
            mid_shade = 1.0
        else:
            diff = (300.0 - threshold) / 250.0
            mid_shade = max(0.55, 1.0 - diff * 0.50)

        cr.new_path()
        cr.set_source_rgb(mid_shade, mid_shade, mid_shade)
        cr.set_line_width(5)
        cr.arc(0, 0, 42, 0, 2 * math.pi)
        cr.stroke()

        # Center Star / Cross: targets 350 nits
        if threshold >= 350.0:
            center_shade = 1.0
        else:
            diff = (350.0 - threshold) / 280.0
            center_shade = max(0.50, 1.0 - diff * 0.55)

        cr.new_path()
        cr.set_source_rgb(center_shade, center_shade, center_shade)
        cr.set_line_width(6)
        cr.move_to(-25, 0)
        cr.line_to(25, 0)
        cr.move_to(0, -25)
        cr.line_to(0, 25)
        cr.stroke()

        # Center diamond
        cr.new_path()
        cr.move_to(0, -12)
        cr.line_to(12, 0)
        cr.line_to(0, 12)
        cr.line_to(-12, 0)
        cr.close_path()
        cr.fill()

        cr.restore()
        cr.new_path()

    # --- Page 4: SDR Brightness & Saturation ---
    def build_page_sdr(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(30)
        box.set_margin_end(30)
        box.set_margin_top(16)
        box.set_margin_bottom(10)

        lbl_title = Gtk.Label()
        lbl_title.set_markup("<span size='large' weight='bold'>Step 4: SDR Brightness & Color Saturation Multipliers</span>")
        lbl_title.set_halign(Gtk.Align.START)
        box.append(lbl_title)

        lbl_desc = Gtk.Label(label="Adjust SDR desktop brightness and color vibrancy so standard windows and browsers look natural.")
        lbl_desc.set_halign(Gtk.Align.START)
        box.append(lbl_desc)

        # Color reference patches canvas
        self.canvas_sdr = Gtk.DrawingArea()
        self.canvas_sdr.set_vexpand(True)
        self.canvas_sdr.add_css_class("pattern-container")
        self.canvas_sdr.set_draw_func(self.draw_sdr_pattern)
        box.append(self.canvas_sdr)

        # Controls Card
        ctrl_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        ctrl_card.add_css_class("card")

        # Row 1: Brightness
        r1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        lbl_b = Gtk.Label(label="SDR Brightness Multiplier:")
        lbl_b.add_css_class("card-title")
        r1.append(lbl_b)

        self.lbl_sdr_b_val = Gtk.Label(label=f"{self.val_sdr_brightness}%")
        self.lbl_sdr_b_val.add_css_class("value-label")
        r1.append(self.lbl_sdr_b_val)

        # Brightness Presets
        b_presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        b_presets.set_hexpand(True)
        b_presets.set_halign(Gtk.Align.END)
        for label, bval in [("60% (Dim)", 60), ("80% (Night)", 80), ("100% (Ref)", 100), ("120% (Day)", 120), ("140%", 140)]:
            btn = Gtk.Button(label=label)
            btn.add_css_class("preset-btn")
            btn.connect("clicked", lambda b, v=bval: self.slider_sdr_b.set_value(v))
            b_presets.append(btn)
        r1.append(b_presets)
        ctrl_card.append(r1)

        self.slider_sdr_b = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 40, 160, 2)
        self.slider_sdr_b.set_value(self.val_sdr_brightness)
        self.slider_sdr_b.connect("value-changed", self.on_sdr_b_changed)
        ctrl_card.append(self.slider_sdr_b)

        # Row 2: Saturation
        r2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        lbl_s = Gtk.Label(label="SDR Saturation Multiplier:")
        lbl_s.add_css_class("card-title")
        r2.append(lbl_s)

        self.lbl_sdr_s_val = Gtk.Label(label=f"{self.val_sdr_saturation}%")
        self.lbl_sdr_s_val.add_css_class("value-label")
        r2.append(self.lbl_sdr_s_val)

        # Saturation Presets
        s_presets = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        s_presets.set_hexpand(True)
        s_presets.set_halign(Gtk.Align.END)
        for label, sval in [("0% (Mono)", 0), ("75% (Muted)", 75), ("100% (sRGB)", 100), ("130% (Vivid)", 130), ("160% (Punchy)", 160)]:
            btn = Gtk.Button(label=label)
            btn.add_css_class("preset-btn")
            btn.connect("clicked", lambda b, v=sval: self.slider_sdr_s.set_value(v))
            s_presets.append(btn)
        r2.append(s_presets)
        ctrl_card.append(r2)

        self.slider_sdr_s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 200, 2)
        self.slider_sdr_s.set_value(self.val_sdr_saturation)
        self.slider_sdr_s.connect("value-changed", self.on_sdr_s_changed)
        ctrl_card.append(self.slider_sdr_s)

        box.append(ctrl_card)
        self.stack.add_named(box, "step_sdr")

    def on_sdr_b_changed(self, scale):
        self.val_sdr_brightness = int(scale.get_value())
        self.lbl_sdr_b_val.set_label(f"{self.val_sdr_brightness}%")
        self.canvas_sdr.queue_draw()

    def on_sdr_s_changed(self, scale):
        self.val_sdr_saturation = int(scale.get_value())
        self.lbl_sdr_s_val.set_label(f"{self.val_sdr_saturation}%")
        self.canvas_sdr.queue_draw()

    def draw_sdr_pattern(self, area, cr, width, height):
        # Neutral Dark Canvas Background
        cr.set_source_rgb(0.09, 0.10, 0.14)
        cr.paint()

        cx = width / 2.0
        cy = height / 2.0

        b_scale = self.val_sdr_brightness / 100.0
        s_scale = self.val_sdr_saturation / 100.0

        # --- Section 1: Simulated SDR Application Window ---
        # Demonstrates SDR reference paper white scaling with brightness
        win_w = min(width * 0.70, 560)
        win_h = 130
        win_x = cx - win_w / 2.0
        win_y = cy - 135

        # Window Frame Border & Header
        cr.new_path()
        cr.set_source_rgb(0.18, 0.20, 0.26)
        cr.rectangle(win_x, win_y, win_w, 28)
        cr.fill()

        # Window Dots (Red, Yellow, Green)
        for i, dot_color in enumerate([(0.9, 0.3, 0.3), (0.9, 0.7, 0.2), (0.3, 0.8, 0.3)]):
            cr.new_path()
            cr.set_source_rgb(*dot_color)
            cr.arc(win_x + 16 + i * 14, win_y + 14, 5, 0, 2 * math.pi)
            cr.fill()

        # Window Title
        cr.new_path()
        cr.set_source_rgb(0.8, 0.85, 0.9)
        cr.select_font_face("sans-serif", 0, 1)
        cr.set_font_size(11)
        cr.move_to(win_x + 65, win_y + 18)
        cr.show_text("SDR Application Preview (White Level Simulation)")
        cr.new_path()

        # Window Body: Background reacts directly to SDR Brightness Multiplier
        paper_lum = min(1.0, max(0.25, 0.96 * b_scale))
        cr.new_path()
        cr.set_source_rgb(paper_lum, paper_lum, paper_lum)
        cr.rectangle(win_x, win_y + 28, win_w, win_h - 28)
        cr.fill()

        # Text inside window (scales with paper contrast)
        text_lum = max(0.05, 0.15 * b_scale)
        cr.new_path()
        cr.set_source_rgb(text_lum, text_lum, text_lum)
        cr.select_font_face("sans-serif", 0, 1)
        cr.set_font_size(14)
        cr.move_to(win_x + 20, win_y + 58)
        cr.show_text("SDR Reference Desktop Document")

        cr.new_path()
        cr.select_font_face("sans-serif", 0, 0)
        cr.set_font_size(11)
        cr.move_to(win_x + 20, win_y + 80)
        cr.show_text(f"Current White Level: {self.val_sdr_brightness}%  |  Color Saturation: {self.val_sdr_saturation}%")

        # Mock UI Buttons inside document (React to Saturation + Brightness)
        btn_colors = [
            ("Blue Action", 0.15, 0.45, 0.95),
            ("Green Save", 0.15, 0.75, 0.35),
            ("Orange Tag", 0.95, 0.55, 0.15),
        ]
        btn_w = 100
        btn_h = 24
        for bi, (btn_name, br, bg, bb) in enumerate(btn_colors):
            bx = win_x + 20 + bi * (btn_w + 12)
            by = win_y + 92

            # Apply saturation & brightness to button
            gray = 0.299 * br + 0.587 * bg + 0.114 * bb
            adj_r = min(1.0, max(0.0, gray + (br - gray) * s_scale)) * min(1.0, b_scale)
            adj_g = min(1.0, max(0.0, gray + (bg - gray) * s_scale)) * min(1.0, b_scale)
            adj_b = min(1.0, max(0.0, gray + (bb - gray) * s_scale)) * min(1.0, b_scale)

            cr.new_path()
            cr.set_source_rgb(adj_r, adj_g, adj_b)
            cr.rectangle(bx, by, btn_w, btn_h)
            cr.fill()

            cr.new_path()
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.select_font_face("sans-serif", 0, 1)
            cr.set_font_size(10)
            ext = cr.text_extents(btn_name)
            cr.move_to(bx + (btn_w - ext.width) / 2.0, by + 16)
            cr.show_text(btn_name)
            cr.new_path()

        # --- Section 2: Large Vibrant Color Swatches & Grayscale Ramp ---
        colors = [
            ("Crimson", 0.95, 0.10, 0.15),
            ("Emerald", 0.10, 0.88, 0.30),
            ("Cobalt", 0.15, 0.40, 0.98),
            ("Amber", 0.98, 0.85, 0.10),
            ("Cyan", 0.10, 0.88, 0.95),
            ("Magenta", 0.92, 0.15, 0.88),
            ("Skin Tone", 0.92, 0.68, 0.52),
        ]

        patch_w = 68
        patch_h = 52
        start_x = cx - (patch_w * len(colors) + 10 * (len(colors) - 1)) / 2.0
        start_y = cy + 20

        for i, (name, r, g, b) in enumerate(colors):
            px = start_x + i * (patch_w + 10)

            # Apply saturation adjustment
            gray = 0.299 * r + 0.587 * g + 0.114 * b
            adj_r = min(1.0, max(0.0, gray + (r - gray) * s_scale)) * min(1.0, b_scale)
            adj_g = min(1.0, max(0.0, gray + (g - gray) * s_scale)) * min(1.0, b_scale)
            adj_b = min(1.0, max(0.0, gray + (b - gray) * s_scale)) * min(1.0, b_scale)

            cr.new_path()
            cr.set_source_rgb(adj_r, adj_g, adj_b)
            cr.rectangle(px, start_y, patch_w, patch_h)
            cr.fill()

            cr.new_path()
            cr.set_source_rgb(0.85, 0.88, 0.92)
            cr.select_font_face("sans-serif", 0, 0)
            cr.set_font_size(10)
            ext = cr.text_extents(name)
            cr.move_to(px + (patch_w - ext.width) / 2.0, start_y + patch_h + 14)
            cr.show_text(name)
            cr.new_path()

        # 16-Step Grayscale Ramp
        ramp_y = cy + 98
        steps = 16
        ramp_total_w = patch_w * len(colors) + 10 * (len(colors) - 1)
        step_w = ramp_total_w / steps
        for s in range(steps):
            sx = start_x + s * step_w
            level = min(1.0, (s / (steps - 1)) * b_scale)
            cr.new_path()
            cr.set_source_rgb(level, level, level)
            cr.rectangle(sx, ramp_y, step_w, 24)
            cr.fill()
            cr.new_path()

    # --- Page 5: Summary & Export ---
    def build_page_summary(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_start(40)
        box.set_margin_end(40)
        box.set_margin_top(20)
        box.set_margin_bottom(20)

        title = Gtk.Label()
        title.set_markup("<span size='xx-large' weight='bold'>Calibration Complete!</span>")
        box.append(title)

        subtitle = Gtk.Label(label="Here are your final calibrated values. Copy them into your HDR settings menu.")
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        # Values Card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("card")

        self.rows_data = [
            ("SDR Brightness Multiplier", lambda: f"{self.val_sdr_brightness}%"),
            ("SDR Saturation Multiplier", lambda: f"{self.val_sdr_saturation}%"),
            ("Min Luminance (HDR)", lambda: f"{self.val_min:.3f}"),
            ("Max Luminance (HDR)", lambda: f"{self.val_max:.1f}"),
            ("Max Average Luminance", lambda: f"{self.val_max_avg:.1f}"),
        ]

        self.summary_labels = {}

        for title_str, val_fn in self.rows_data:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

            t_lbl = Gtk.Label(label=title_str)
            t_lbl.set_halign(Gtk.Align.START)
            t_lbl.set_hexpand(True)
            row.append(t_lbl)

            v_lbl = Gtk.Label()
            v_lbl.add_css_class("value-label")
            self.summary_labels[title_str] = (v_lbl, val_fn)
            row.append(v_lbl)

            copy_btn = Gtk.Button(label="Copy")
            copy_btn.add_css_class("btn-secondary")
            copy_btn.connect("clicked", lambda b, fn=val_fn: self.copy_to_clipboard(fn()))
            row.append(copy_btn)

            card.append(row)

        box.append(card)

        # --- Hyprland Configuration Card ---
        hypr_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hypr_card.add_css_class("card")

        hypr_hdr = Gtk.Label()
        hypr_hdr.set_markup("<b>Hyprland Configuration Snippet (~/.config/hypr/hyprland.conf)</b>")
        hypr_hdr.set_halign(Gtk.Align.START)
        hypr_card.append(hypr_hdr)

        conn = self.current_display["connector"]
        res_match = re.search(r"(\d+x\d+)\s*@\s*(\d+)Hz", self.current_display.get("resolution", ""))
        mode_str = f"{res_match.group(1)}@{res_match.group(2)}" if res_match else "1920x1080@144"

        self.hypr_code_str = (
            f"# Monitor directive with 10-bit color, HDR & VRR:\n"
            f"monitor = {conn}, {mode_str}, 0x0, 1, bitdepth, 10, vrr, 1\n\n"
            f"# Experimental HDR color management flags:\n"
            f"experimental {{\n"
            f"    hdr = true\n"
            f"    wide_color_gamut = true\n"
            f"}}"
        )

        lbl_code = Gtk.Label()
        lbl_code.set_markup(f"<tt><span color='#7dd3fc'>{GLib.markup_escape_text(self.hypr_code_str)}</span></tt>")
        lbl_code.set_halign(Gtk.Align.START)
        hypr_card.append(lbl_code)

        btn_copy_hypr = Gtk.Button(label="Copy Hyprland Config Snippet")
        btn_copy_hypr.add_css_class("btn-secondary")
        btn_copy_hypr.connect("clicked", lambda b: self.copy_to_clipboard(self.hypr_code_str))
        hypr_card.append(btn_copy_hypr)

        box.append(hypr_card)

        # Actions Row
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions_box.set_halign(Gtk.Align.CENTER)

        btn_apply_fd = Gtk.Button(label="🚀 Apply Directly to FlightDeck")
        btn_apply_fd.add_css_class("btn-primary")
        btn_apply_fd.connect("clicked", self.apply_to_flightdeck)
        actions_box.append(btn_apply_fd)

        btn_copy_all = Gtk.Button(label="Copy All Values")
        btn_copy_all.add_css_class("btn-secondary")
        btn_copy_all.connect("clicked", self.on_copy_all_clicked)
        actions_box.append(btn_copy_all)

        btn_save = Gtk.Button(label="Save JSON Profile")
        btn_save.add_css_class("btn-secondary")
        btn_save.connect("clicked", self.on_save_profile_clicked)
        actions_box.append(btn_save)

        btn_mpv_sum = Gtk.Button(label="🎬 Launch MPV 10-Bit Test Video")
        btn_mpv_sum.add_css_class("btn-secondary")
        btn_mpv_sum.connect("clicked", self.launch_mpv_verification)
        actions_box.append(btn_mpv_sum)

        box.append(actions_box)

        # Status Banner
        self.lbl_status = Gtk.Label()
        self.lbl_status.set_markup("")
        box.append(self.lbl_status)

        self.stack.add_named(box, "step_summary")

    def apply_to_flightdeck(self, *args):
        cfg_path = Path.home() / ".config" / "caelestia" / "astra-flightdeck.lua"
        if not cfg_path.exists():
            self.lbl_status.set_markup(f"<span color='#f43f5e'>FlightDeck config not found at: {cfg_path}</span>")
            return
        try:
            content = cfg_path.read_text()
            b_val = self.val_sdr_brightness / 100.0
            s_val = self.val_sdr_saturation / 100.0
            content = re.sub(r'sdrbrightness\s*=\s*[\d.]+', f'sdrbrightness = {b_val}', content)
            content = re.sub(r'sdrsaturation\s*=\s*[\d.]+', f'sdrsaturation = {s_val}', content)
            content = re.sub(r'sdr_min_luminance\s*=\s*[\d.]+', f'sdr_min_luminance = {self.val_min:.3f}', content)
            content = re.sub(r'sdr_max_luminance\s*=\s*[\d.]+', f'sdr_max_luminance = {self.val_max:.1f}', content)
            content = re.sub(r'min_luminance\s*=\s*[\d.]+', f'min_luminance = {self.val_min:.3f}', content)
            content = re.sub(r'max_luminance\s*=\s*[\d.]+', f'max_luminance = {self.val_max:.1f}', content)
            content = re.sub(r'max_avg_luminance\s*=\s*[\d.]+', f'max_avg_luminance = {self.val_max_avg:.1f}', content)
            cfg_path.write_text(content)
            self.lbl_status.set_markup(
                "<span color='#10b981' weight='bold'>✓ Applied directly to FlightDeck (~/.config/caelestia/astra-flightdeck.lua)! Your settings are now live!</span>"
            )
        except Exception as e:
            self.lbl_status.set_markup(f"<span color='#f43f5e'>Error writing to FlightDeck: {e}</span>")

    def refresh_summary(self):
        for title_str, (lbl, val_fn) in self.summary_labels.items():
            lbl.set_label(val_fn())

    def copy_to_clipboard(self, text):
        clipboard = self.get_display().get_clipboard()
        clipboard.set(text)
        self.lbl_status.set_markup(f"<span color='#38bdf8'>✓ Copied <b>{text}</b> to clipboard!</span>")

    def on_copy_all_clicked(self, *args):
        text = (
            f"SDR Brightness Multiplier: {self.val_sdr_brightness}%\n"
            f"SDR Saturation Multiplier: {self.val_sdr_saturation}%\n"
            f"Min Luminance (HDR): {self.val_min:.3f}\n"
            f"Max Luminance (HDR): {self.val_max:.1f}\n"
            f"Max Average Luminance: {self.val_max_avg:.1f}"
        )
        self.copy_to_clipboard(text)
        self.lbl_status.set_markup("<span color='#10b981'>✓ All calibration values copied to clipboard!</span>")

    def on_save_profile_clicked(self, *args):
        config_path = Path.home() / ".config" / "hdr-calibration.json"
        data = {
            "display": self.current_display["name"],
            "connector": self.current_display["connector"],
            "sdr_brightness_multiplier": self.val_sdr_brightness,
            "sdr_saturation_multiplier": self.val_sdr_saturation,
            "min_luminance_nits": round(self.val_min, 4),
            "max_luminance_nits": round(self.val_max, 1),
            "max_average_luminance_nits": round(self.val_max_avg, 1),
        }
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps(data, indent=2))
            self.lbl_status.set_markup(f"<span color='#10b981'>✓ Saved profile to <b>{config_path}</b>!</span>")
        except Exception as e:
            self.lbl_status.set_markup(f"<span color='#f43f5e'>Error saving profile: {e}</span>")

    # --- Navigation Logic ---
    def on_next_clicked(self, *args):
        if self.current_step < self.total_steps - 1:
            self.current_step += 1
            self.update_nav()

    def on_back_clicked(self, *args):
        if self.current_step > 0:
            self.current_step -= 1
            self.update_nav()

    def update_nav(self):
        page_names = ["step_welcome", "step_min", "step_max", "step_avg", "step_sdr", "step_summary"]
        self.stack.set_visible_child_name(page_names[self.current_step])

        self.btn_back.set_sensitive(self.current_step > 0)

        if self.current_step == 0:
            self.btn_next.set_label("Start Calibration →")
            self.lbl_step.set_label("Introduction")
        elif self.current_step == self.total_steps - 1:
            self.btn_next.set_label("Done")
            self.btn_next.set_sensitive(False)
            self.lbl_step.set_label("Results & Export")
            self.refresh_summary()
        else:
            self.btn_next.set_sensitive(True)
            self.btn_next.set_label("Next →")
            self.lbl_step.set_label(f"Step {self.current_step} of {self.total_steps - 2}")


class HDRCalibrateApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.hdr_calibrate",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = HDRCalibrateWindow(self)
        win.present()


def main():
    app = HDRCalibrateApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
