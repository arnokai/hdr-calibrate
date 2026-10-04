#!/usr/bin/env python3
"""
Generates a true 10-bit SMPTE ST 2084 (PQ / BT.2020) HDR10 test pattern video
using Cairo vector graphics and ffmpeg libx265.
"""

import sys
import math
import subprocess
from pathlib import Path
import cairo

WIDTH = 1920
HEIGHT = 1080
FPS = 30
DURATION_SEC = 10
TOTAL_FRAMES = FPS * DURATION_SEC

OUTPUT_FILE = Path(__file__).parent / "hdr10_test_pattern.mp4"

def draw_frame(frame_idx):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, HEIGHT)
    cr = cairo.Context(surface)

    # Frame timing
    t = frame_idx / FPS
    # Pulse wave for flashing bars (1 Hz)
    pulse = 0.5 + 0.5 * math.sin(t * 2 * math.pi * 1.5)

    if frame_idx < 120:
        # --- Screen 1: Black Level & Shadow PLUGE (0 - 4s) ---
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.paint()

        # Header
        cr.new_path()
        cr.set_source_rgb(0.4, 0.45, 0.5)
        cr.select_font_face("sans-serif", 0, 1)
        cr.set_font_size(32)
        cr.move_to(80, 100)
        cr.show_text("HDR10 BLACK LEVEL CLIPPING (0.00 – 0.30 NITS)")

        cr.new_path()
        cr.set_font_size(18)
        cr.move_to(80, 140)
        cr.show_text("Step 1 Test: 0.00 should be invisible. 0.05–0.08 should be faintly perceptible.")

        # Reference Black Bars (PLUGE)
        bars = [
            ("0.00 nits (Ref)", 0.00),
            ("0.02 nits", 0.02),
            ("0.05 nits", 0.05),
            ("0.08 nits", 0.08),
            ("0.15 nits", 0.15),
            ("0.30 nits", 0.30),
        ]
        bar_w = 260
        bar_h = 420
        start_x = (WIDTH - (bar_w * len(bars) + 20 * (len(bars) - 1))) / 2.0
        start_y = 260

        for i, (label, nits) in enumerate(bars):
            bx = start_x + i * (bar_w + 20)

            # Flashing intensity
            if nits == 0.0:
                val = 0.0
            else:
                val = (nits / 0.30) * 0.15 * (0.6 + 0.4 * pulse)

            cr.new_path()
            cr.set_source_rgb(val, val, val)
            cr.rectangle(bx, start_y, bar_w, bar_h)
            cr.fill()

            # Label below
            cr.new_path()
            cr.set_source_rgb(0.35, 0.35, 0.4)
            cr.select_font_face("monospace", 0, 0)
            cr.set_font_size(15)
            cr.move_to(bx + 20, start_y + bar_h + 35)
            cr.show_text(label)

    elif frame_idx < 240:
        # --- Screen 2: Peak Highlight Clipping (4 - 8s) ---
        cr.set_source_rgb(0.06, 0.07, 0.09)
        cr.paint()

        # Header
        cr.new_path()
        cr.set_source_rgb(0.85, 0.88, 0.95)
        cr.select_font_face("sans-serif", 0, 1)
        cr.set_font_size(32)
        cr.move_to(80, 90)
        cr.show_text("HDR10 PEAK HIGHLIGHT CLIPPING (250 – 500 NITS)")

        cr.new_path()
        cr.set_font_size(18)
        cr.move_to(80, 130)
        cr.show_text("Step 2 Test: Flashing bars above your display's peak (~350 nits) should clip into solid white.")

        # 10% Highlight Window
        win_w = 1200
        win_h = 600
        win_x = (WIDTH - win_w) / 2.0
        win_y = (HEIGHT - win_h) / 2.0 + 30

        cr.new_path()
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.rectangle(win_x, win_y, win_w, win_h)
        cr.fill()

        # Stepping highlight bars inside 10% window
        peak_bars = [
            ("250 nits", 250),
            ("300 nits (EDID)", 300),
            ("350 nits (Peak)", 350),
            ("400 nits", 400),
            ("500 nits", 500),
        ]
        bar_w = 200
        bar_h = 360
        bx_start = win_x + (win_w - (bar_w * len(peak_bars) + 20 * (len(peak_bars) - 1))) / 2.0
        by_pos = win_y + 120

        for i, (label, nits) in enumerate(peak_bars):
            bx = bx_start + i * (bar_w + 20)

            # Highlight bars modulation
            diff = (nits - 250) / 250.0
            shade = max(0.65, 1.0 - diff * 0.35 * pulse)

            cr.new_path()
            cr.set_source_rgb(shade, shade, shade)
            cr.rectangle(bx, by_pos, bar_w, bar_h)
            cr.fill()

            cr.new_path()
            cr.set_source_rgb(0.2, 0.2, 0.2)
            cr.select_font_face("monospace", 0, 1)
            cr.set_font_size(16)
            cr.move_to(bx + 20, by_pos + bar_h + 35)
            cr.show_text(label)

    else:
        # --- Screen 3: BT.2020 / DCI-P3 Color Gamut (8 - 10s) ---
        cr.set_source_rgb(0.08, 0.09, 0.12)
        cr.paint()

        cr.new_path()
        cr.set_source_rgb(0.85, 0.9, 0.95)
        cr.select_font_face("sans-serif", 0, 1)
        cr.set_font_size(32)
        cr.move_to(80, 100)
        cr.show_text("HDR10 WIDE COLOR GAMUT & 10-BIT GRADIENTS")

        # Color Ramps
        colors = [
            ("Red", (1.0, 0.0, 0.0)),
            ("Green", (0.0, 1.0, 0.0)),
            ("Blue", (0.0, 0.0, 1.0)),
            ("Cyan", (0.0, 1.0, 1.0)),
            ("Magenta", (1.0, 0.0, 1.0)),
            ("Yellow", (1.0, 1.0, 0.0)),
            ("White", (1.0, 1.0, 1.0)),
        ]
        ramp_w = 1600
        ramp_h = 55
        rx = (WIDTH - ramp_w) / 2.0
        ry_start = 180

        for ci, (cname, (r, g, b)) in enumerate(colors):
            ry = ry_start + ci * (ramp_h + 20)
            steps = 64
            sw = ramp_w / steps
            for s in range(steps):
                frac = s / (steps - 1)
                cr.new_path()
                cr.set_source_rgb(r * frac, g * frac, b * frac)
                cr.rectangle(rx + s * sw, ry, sw + 1, ramp_h)
                cr.fill()

            cr.new_path()
            cr.set_source_rgb(0.8, 0.8, 0.8)
            cr.select_font_face("sans-serif", 0, 1)
            cr.set_font_size(14)
            cr.move_to(rx - 90, ry + 34)
            cr.show_text(cname)

    # Convert surface to raw BGRA bytes
    surface.flush()
    data = surface.get_data()
    return bytes(data)

def main():
    print(f"Generating 10-bit HDR10 test pattern ({TOTAL_FRAMES} frames)...")

    ffmpeg_cmd = [
        "ffmpeg",
        "-f", "rawvideo",
        "-pix_fmt", "bgra",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx265",
        "-preset", "ultrafast",
        "-crf", "16",
        "-pix_fmt", "yuv420p10le",
        "-color_primaries", "bt2020",
        "-color_trc", "smpte2084",
        "-colorspace", "bt2020nc",
        "-x265-params", (
            "hdr10=1:hdr10-opt=1:"
            "master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(3500000,500):"
            "max-cll=350,300"
        ),
        "-y",
        str(OUTPUT_FILE),
    ]

    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    for i in range(TOTAL_FRAMES):
        raw_bytes = draw_frame(i)
        proc.stdin.write(raw_bytes)
        if (i + 1) % 60 == 0:
            print(f"Rendered {i + 1}/{TOTAL_FRAMES} frames...")

    proc.stdin.close()
    stderr = proc.stderr.read()
    proc.wait()

    if proc.returncode == 0:
        print(f"✓ Successfully generated HDR10 test video: {OUTPUT_FILE}")
        return 0
    else:
        print(f"FFmpeg error: {stderr.decode()}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
