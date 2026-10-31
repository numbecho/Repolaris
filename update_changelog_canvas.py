with open('CHANGELOG.md', 'r') as f:
    text = f.read()

canvas_bullets = """  - Added independent Waveform Canvas Scheme dropdown with 5 high-contrast palettes (Clinical Dark, Paper White, Classic Pink ECG Grid, Color Blind Safe, Emerald Phosphor), guaranteeing sharp visual separation between the lead plot, calipers, and background.
  - Added Clinical ECG Grid dropdown (Lines, Dots, None) highlighting international calibration standards ($25\\text{ mm/s}$ and $10\\text{ mm/mV}$).
  - Added persistent clinical scale badge (`📐 Scale: 25 mm/s | 10 mm/mV`) in the top-right corner of the waveform canvas.
  - Formally labeled axes with clinical units: Y-axis labeled `Voltage (mV)` and X-axis labeled `Time (hh:mm:ss)` with dynamic timestamp tick formatting (`TimeAxisItem`)."""

target = "  - Enabled live real-time theme and locale propagation across PyQtGraph canvases, curves, calipers, KPI cards, tables, and dialogs without restarting."

if target in text and canvas_bullets not in text:
    text = text.replace(target, target + "\n" + canvas_bullets)

with open('CHANGELOG.md', 'w') as f:
    f.write(text)

print("Updated CHANGELOG.md with canvas & grid features")
