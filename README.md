# SSTV decoder (bash + CLI) — wav/mp3 → image

Simple SSTV **decoder** (called "encoder" in the original request, but per the
description "load a wav or mp3 file and save an image" this is **RX / decoding**).

- Input: `wav`, `mp3`, `ogg`, `flac`, `m4a`, ... (via `ffmpeg`)
- Output: `png`, `jpg`, `bmp`, ...
- Automatic mode detection from the VIS header (1900/1200/1900 + 8 bits)
- Manual mode via `--mode` (even without a header, with `--no-vis`)

## Supported modes

All requested families:

**Robot (8 modes):**
- `robot8` (BW 160×120, VIS 1,2,3)
- `robot12` (BW 160×120, VIS 5,6,7)
- `robot24bw` (BW 320×240, VIS 9,10,11)
- `robot36bw` (BW 320×240, VIS 13,14,15)
- `robot12c` (YCbCr 160×120, VIS 0)
- `robot24c` (YCbCr 320×120, VIS 4)
- `robot36` (YCbCr 320×240, VIS 8) — ISS
- `robot72` (YCbCr 320×240, VIS 12)

**Martin (4 modes):**
- `martin1` (RGB 320×256, VIS 44)
- `martin2` (RGB 320×256, VIS 40)
- `martin3` (RGB 320×128, VIS 36)
- `martin4` (RGB 320×128, VIS 32)

**Scottie (5 modes):**
- `scottie1` (RGB 320×256, VIS 60)
- `scottie2` (RGB 320×256, VIS 56)
- `scottie3` (RGB 320×128, VIS 52)
- `scottie4` (RGB 320×128, VIS 48)
- `scottiedx` (RGB 320×256, VIS 76)

**FAX:**
- `fax480` (BW 512×480, VIS 85)

**PD (7 modes):**
- `pd50` (320×256, VIS 93)
- `pd90` (320×256, VIS 99)
- `pd120` (640×496, VIS 95)
- `pd160` (512×400, VIS 98)
- `pd180` (640×496, VIS 96)
- `pd240` (640×496, VIS 97)
- `pd290` (800×616, VIS 94)

25 canonical modes in total. BW R/G/B variants (e.g. Robot BW8 VIS 1/2/3)
are mapped to a single mode — decoded as grayscale.

Timing follows `libsstv` (YO7JBP) + the Dayton Paper (Robot 1200C firmware).

## Installation

```bash
sudo apt install ffmpeg python3-pip
pip install -r requirements.txt
chmod +x sstv-decode.sh sstv_decode.py
```

## Usage — bash

```bash
./sstv-decode.sh input.wav output.png
./sstv-decode.sh input.mp3 output.png -v
./sstv-decode.sh input.mp3 output.png --mode pd120
./sstv-decode.sh --list-modes
./sstv-decode.sh --help
```

## Usage — CLI (python)

```bash
python3 sstv_decode.py input.wav output.png
python3 sstv_decode.py input.mp3 output.png --mode martin1
python3 sstv_decode.py input.wav output.png --skip 2.5 -v
python3 sstv_decode.py input.wav output.png --mode robot36 --no-sync
python3 sstv_decode.py --list-modes

# no header (raw image starting at --skip):
python3 sstv_decode.py recording.wav out.png --mode scottie1 --no-vis --skip 1.2
```

## How it works

1. `ffmpeg` converts the input to mono 48 kHz WAV (direct read for `wav`
   48k/mono/16-bit).
2. FM demodulation via the Hilbert transform (`scipy.signal.hilbert`)
   → instantaneous frequency 1500–2300 Hz → brightness 0–255.
3. Calibration header search `1900 Hz 300 ms / 1200 Hz 10 ms / 1900 Hz 300 ms`
   + VIS start bit, using a moving average (vectorized, fast).
4. VIS: 7 data bits (1100 = 1, 1300 = 0) + parity (even) + stop bit.
5. Image via free-run + fine sync-pulse (1200 Hz) tracking per line/block.
   - Martin: sync at line start
   - Scottie: sync in the middle of the line (+ starting sync)
   - Robot/FAX: sync at line start
   - PD: sync at the start of a 2-line block (Y + Cr + Cb + Y, shared chroma)
   - Robot-C-half (12C/36): Y every line + alternating chroma, filled from neighbor
   - YCbCr → RGB conversion BT.601 full-range
6. Saved via Pillow.

## Notes / limits

- "Simple" = free-run + sync tracking, no slant correction for noisy
  OTA recordings with clock drift. Enough for clean files (SDR recording,
  ISS, MMSSTV export). For heavy noise/slant use QSSTV/MMSSTV/Robot36.
- MP3 compression slightly degrades colors (verified: still decodes, VIS OK).
- PD290 (800×616, ~5 min) needs ~14 M samples → a few seconds for
  demodulation, tens of seconds for decoding — normal.
- Terminology: TX = encoder (image → audio), RX = decoder (audio → image).
  This project is an **RX decoder** per the task description.

## Layout

```
sstv_decode.py   - main CLI decoder (python3, numpy/scipy/Pillow)
sstv-decode.sh   - bash wrapper (dependency checks + python call)
requirements.txt - python dependencies
README.md        - this documentation
```

## Test

Quick smoke test (synthetic signal → decoding):

```bash
python3 sstv_decode.py --list-modes
./sstv-decode.sh test.wav test.png -v
```

Verified on synthetic signals of all 25 modes (100% VIS detection,
mean pixel error <1 for RGB/YUV, <1 for BW) + cross-checked with `PySSTV`
(MartinM1, ScottieS1, Robot36, PD90) and MP3 input.

## License

MIT — timing per Dayton Paper / libsstv (MIT), own implementation.

## About

This whole thing is vibecoded — just a for-fun project I made because I was bored.
