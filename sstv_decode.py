#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Jednoduchý SSTV dekodér (wav/mp3 -> obrázok).
Podpora: všetky Robot, všetky Martin, všetky Scottie, FAX480, všetky PD.

Použitie:
    python3 sstv_decode.py vstup.wav vystup.png
    python3 sstv_decode.py vstup.mp3 vystup.png --mode martin1
    python3 sstv_decode.py --list-modes

Závislosi: numpy, scipy, Pillow, ffmpeg (na mp3/ogg/flac, voliteľné pre wav)
"""

import argparse
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np
from PIL import Image

TARGET_SR = 48000

# ---------------------------------------------------------------------------
# Definície módov
# Časy v ms, rozmery width x height, colorspace: RGB / YUV / BW
# VIS = 7-bitová hodnota (bez parity). Parita sa kontroluje, ale mapuje sa data.
# Časovanie prevzaté z libsstv (YO7JBP) + Dayton Paper (BarberDSP).
# ---------------------------------------------------------------------------

MODES = {}

def _add(m):
    MODES[m["id"]] = m
    for a in m.get("aliases", []):
        MODES[a] = m

# --- Robot BW ---
_add({"id": "robot8", "aliases": ["r8", "robot8bw", "robot-bw8"],
      "label": "Robot 8 (BW 160x120, 8s)", "family": "robot",
      "vis": [1, 2, 3], "width": 160, "height": 120, "ctype": "BW",
      "sync": 10.0, "porch": 0.0, "pixel": 0.35})
_add({"id": "robot12", "aliases": ["r12", "robot12bw", "robot-bw12"],
      "label": "Robot 12 (BW 160x120, 12s)", "family": "robot",
      "vis": [5, 6, 7], "width": 160, "height": 120, "ctype": "BW",
      "sync": 7.0, "porch": 0.0, "pixel": 0.58125})
_add({"id": "robot24bw", "aliases": ["r24bw", "robot24-bw", "robot-bw24"],
      "label": "Robot 24 (BW 320x240, 24s)", "family": "robot",
      "vis": [9, 10, 11], "width": 320, "height": 240, "ctype": "BW",
      "sync": 12.0, "porch": 0.0, "pixel": 0.290625})
_add({"id": "robot36bw", "aliases": ["r36bw", "robot36-bw", "robot-bw36"],
      "label": "Robot 36 (BW 320x240, 36s)", "family": "robot",
      "vis": [13, 14, 15], "width": 320, "height": 240, "ctype": "BW",
      "sync": 12.0, "porch": 0.0, "pixel": 0.43125})

# --- Robot Color ---
_add({"id": "robot12c", "aliases": ["r12c", "robot-c12", "robot12color"],
      "label": "Robot 12C (YCbCr 160x120, ~13s)", "family": "robot",
      "vis": [0], "width": 160, "height": 120, "ctype": "YUV-HALF",
      "sync": 9.0, "porch": 3.0, "porch2": 1.5, "sep": 4.5, "sep2": 4.5,
      "pixel": 0.375, "pixel2": 0.1875})
_add({"id": "robot24c", "aliases": ["r24c", "robot-c24", "robot24color"],
      "label": "Robot 24C (YCbCr 320x120, 24s)", "family": "robot",
      "vis": [4], "width": 320, "height": 120, "ctype": "YUV-FULL",
      "sync": 9.0, "porch": 3.0, "porch2": 1.5, "sep": 4.5, "sep2": 4.5,
      "pixel": 0.275, "pixel2": 0.1375})
_add({"id": "robot36", "aliases": ["r36", "robot-c36", "robot36color"],
      "label": "Robot 36 (YCbCr 320x240, 36s) - ISS", "family": "robot",
      "vis": [8], "width": 320, "height": 240, "ctype": "YUV-HALF",
      "sync": 9.0, "porch": 3.0, "porch2": 1.5, "sep": 4.5, "sep2": 4.5,
      "pixel": 0.28125, "pixel2": 0.140625})
_add({"id": "robot72", "aliases": ["r72", "robot-c72", "robot72color"],
      "label": "Robot 72 (YCbCr 320x240, 72s)", "family": "robot",
      "vis": [12], "width": 320, "height": 240, "ctype": "YUV-FULL",
      "sync": 9.0, "porch": 3.0, "porch2": 1.5, "sep": 4.5, "sep2": 4.5,
      "pixel": 0.43125, "pixel2": 0.215625})

# --- Martin ---
_add({"id": "martin1", "aliases": ["m1"],
      "label": "Martin M1 (RGB 320x256, 114s)", "family": "martin",
      "vis": [44], "width": 320, "height": 256, "ctype": "RGB",
      "sync": 4.862, "porch": 0.572, "pixel": 0.4576})
_add({"id": "martin2", "aliases": ["m2"],
      "label": "Martin M2 (RGB 320x256, 58s)", "family": "martin",
      "vis": [40], "width": 320, "height": 256, "ctype": "RGB",
      "sync": 4.862, "porch": 0.572, "pixel": 0.2288})
_add({"id": "martin3", "aliases": ["m3"],
      "label": "Martin M3 (RGB 320x128, 57s)", "family": "martin",
      "vis": [36], "width": 320, "height": 128, "ctype": "RGB",
      "sync": 4.862, "porch": 0.572, "pixel": 0.4576})
_add({"id": "martin4", "aliases": ["m4"],
      "label": "Martin M4 (RGB 320x128, 29s)", "family": "martin",
      "vis": [32], "width": 320, "height": 128, "ctype": "RGB",
      "sync": 4.862, "porch": 0.572, "pixel": 0.2288})

# --- Scottie ---
_add({"id": "scottie1", "aliases": ["s1"],
      "label": "Scottie S1 (RGB 320x256, 110s)", "family": "scottie",
      "vis": [60], "width": 320, "height": 256, "ctype": "RGB",
      "sync": 9.0, "porch": 1.5, "pixel": 0.432})
_add({"id": "scottie2", "aliases": ["s2"],
      "label": "Scottie S2 (RGB 320x256, 71s)", "family": "scottie",
      "vis": [56], "width": 320, "height": 256, "ctype": "RGB",
      "sync": 9.0, "porch": 1.5, "pixel": 0.2752})
_add({"id": "scottie3", "aliases": ["s3"],
      "label": "Scottie S3 (RGB 320x128, 55s)", "family": "scottie",
      "vis": [52], "width": 320, "height": 128, "ctype": "RGB",
      "sync": 9.0, "porch": 1.5, "pixel": 0.432})
_add({"id": "scottie4", "aliases": ["s4"],
      "label": "Scottie S4 (RGB 320x128, 36s)", "family": "scottie",
      "vis": [48], "width": 320, "height": 128, "ctype": "RGB",
      "sync": 9.0, "porch": 1.5, "pixel": 0.2752})
_add({"id": "scottiedx", "aliases": ["sdx", "scottie-dx", "dx"],
      "label": "Scottie DX (RGB 320x256, 269s)", "family": "scottie",
      "vis": [76], "width": 320, "height": 256, "ctype": "RGB",
      "sync": 9.0, "porch": 1.5, "pixel": 1.08})

# --- FAX480 ---
_add({"id": "fax480", "aliases": ["fax", "fax-480"],
      "label": "FAX480 (BW 512x480, ~129s)", "family": "fax",
      "vis": [85], "width": 512, "height": 480, "ctype": "BW",
      "sync": 5.12, "porch": 0.0, "pixel": 0.512})

# --- PD ---
_add({"id": "pd50", "aliases": ["pd-50"],
      "label": "PD50 (YCbCr 320x256, 50s)", "family": "pd",
      "vis": [93], "width": 320, "height": 256, "ctype": "YUV-PD",
      "sync": 20.0, "porch": 2.08, "pixel": 0.286})
_add({"id": "pd90", "aliases": ["pd-90"],
      "label": "PD90 (YCbCr 320x256, 90s)", "family": "pd",
      "vis": [99], "width": 320, "height": 256, "ctype": "YUV-PD",
      "sync": 20.0, "porch": 2.08, "pixel": 0.532})
_add({"id": "pd120", "aliases": ["pd-120"],
      "label": "PD120 (YCbCr 640x496, 126s)", "family": "pd",
      "vis": [95], "width": 640, "height": 496, "ctype": "YUV-PD",
      "sync": 20.0, "porch": 2.08, "pixel": 0.19})
_add({"id": "pd160", "aliases": ["pd-160"],
      "label": "PD160 (YCbCr 512x400, 161s)", "family": "pd",
      "vis": [98], "width": 512, "height": 400, "ctype": "YUV-PD",
      "sync": 20.0, "porch": 2.08, "pixel": 0.382})
_add({"id": "pd180", "aliases": ["pd-180"],
      "label": "PD180 (YCbCr 640x496, 187s)", "family": "pd",
      "vis": [96], "width": 640, "height": 496, "ctype": "YUV-PD",
      "sync": 20.0, "porch": 2.08, "pixel": 0.286})
_add({"id": "pd240", "aliases": ["pd-240"],
      "label": "PD240 (YCbCr 640x496, 248s)", "family": "pd",
      "vis": [97], "width": 640, "height": 496, "ctype": "YUV-PD",
      "sync": 20.0, "porch": 2.08, "pixel": 0.382})
_add({"id": "pd290", "aliases": ["pd-290"],
      "label": "PD290 (YCbCr 800x616, 289s)", "family": "pd",
      "vis": [94], "width": 800, "height": 616, "ctype": "YUV-PD",
      "sync": 20.0, "porch": 2.08, "pixel": 0.286})

# VIS data -> mode id (kanonické id)
VIS_MAP = {}
for _mid, _m in list(MODES.items()):
    # len() hack: MODES obsahuje aj aliasy, berieme len kanonické
    pass
_CANON = ["robot8", "robot12", "robot24bw", "robot36bw",
          "robot12c", "robot24c", "robot36", "robot72",
          "martin1", "martin2", "martin3", "martin4",
          "scottie1", "scottie2", "scottie3", "scottie4", "scottiedx",
          "fax480",
          "pd50", "pd90", "pd120", "pd160", "pd180", "pd240", "pd290"]
for _cid in _CANON:
    _m = MODES[_cid]
    for _v in _m["vis"]:
        VIS_MAP[_v] = _cid


def freq_to_lum(freq):
    v = (freq - 1500.0) / 800.0 * 255.0
    return np.clip(v, 0, 255)


def load_audio(path, target_sr=TARGET_SR, verbose=False):
    """Načíta wav/mp3/ogg/flac cez ffmpeg do mono float32 @ target_sr."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Vstupný súbor neexistuje: {path}")
    # Skús priamo wav bez ffmpeg (rýchlejšie), inak ffmpeg
    ext = os.path.splitext(path)[1].lower()
    tmp = None
    wav_path = path
    need_conv = True
    if ext == ".wav":
        try:
            with wave.open(path, "rb") as w:
                sr = w.getframerate()
                ch = w.getnchannels()
                sw = w.getsampwidth()
                if sr == target_sr and ch == 1 and sw == 2:
                    need_conv = False
        except Exception:
            need_conv = True
    if need_conv:
        # potrebujeme ffmpeg
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        wav_path = tmp
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", path,
               "-ac", "1", "-ar", str(target_sr),
               "-acodec", "pcm_s16le", wav_path]
        if verbose:
            print(f"[sstv] konverzia cez ffmpeg: {' '.join(cmd)}", file=sys.stderr)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)
            raise RuntimeError(f"ffmpeg zlyhal: {r.stderr.strip()}")
    try:
        with wave.open(wav_path, "rb") as w:
            sr = w.getframerate()
            ch = w.getnchannels()
            sw = w.getsampwidth()
            n = w.getnframes()
            raw = w.readframes(n)
        if sw == 1:
            a = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            a = (a - 128.0) / 128.0
            if ch == 2:
                a = a.reshape(-1, 2).mean(axis=1)
        elif sw == 2:
            a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if ch == 2:
                a = a.reshape(-1, 2).mean(axis=1)
            elif ch > 2:
                a = a.reshape(-1, ch).mean(axis=1)
        else:
            raise RuntimeError(f"Nepodporovaná bitová hĺbka WAV: {sw*8} bit")
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    if verbose:
        print(f"[sstv] načítané: {len(a)} vzoriek @ {sr} Hz ({len(a)/sr:.1f} s)", file=sys.stderr)
    return a, sr


def fm_demod(samples, fs, verbose=False):
    """FM demodulácia cez Hilbertovu transformáciu -> okamžitá frekvencia [Hz]."""
    from scipy.signal import hilbert
    if verbose:
        print("[sstv] FM demodulácia (Hilbert)...", file=sys.stderr)
    x = samples.astype(np.float64)
    # odstráň DC
    x = x - np.mean(x)
    analytic = hilbert(x)
    phase = np.unwrap(np.angle(analytic))
    freq = np.diff(phase) / (2.0 * np.pi) * fs
    freq = np.append(freq, freq[-1])
    # orez nezmysly
    freq = np.clip(freq, 500, 3000)
    return freq.astype(np.float32)


def moving_avg(arr, w):
    """Kĺzavý priemer oknom w (kausálny, výstup len(arr)-w+1)."""
    c = np.cumsum(np.insert(arr, 0, 0.0))
    return (c[w:] - c[:-w]) / w


def find_header(freq, fs, verbose=False):
    """Nájde kalibračnú hlavičku 1900/1200/1900 + VIS start. Vráti index začiatku."""
    w10 = int(round(0.010 * fs))
    step = int(round(0.002 * fs))
    o_break = int(round(0.300 * fs))
    o_lead2 = int(round(0.310 * fs))
    o_vis = int(round(0.610 * fs))
    need = o_vis + w10 + 5 * fs  # aspoň hlavička + kúsok VIS
    if len(freq) < need:
        return None
    avg = moving_avg(freq, w10)  # avg[i] = priemer [i, i+w10)
    n = len(avg) - (o_vis + w10)
    if n <= 0:
        return None
    idx = np.arange(0, n, step)
    l1 = avg[idx]
    br = avg[idx + o_break]
    l2 = avg[idx + o_lead2]
    vs = avg[idx + o_vis]
    ok = (np.abs(l1 - 1900) < 100) & (np.abs(br - 1200) < 100) & \
         (np.abs(l2 - 1900) < 100) & (np.abs(vs - 1200) < 100)
    hits = np.where(ok)[0]
    if len(hits) == 0:
        # skús voľnejšiu toleranciu
        ok2 = (np.abs(l1 - 1900) < 150) & (np.abs(br - 1200) < 150) & \
              (np.abs(l2 - 1900) < 150) & (np.abs(vs - 1200) < 150)
        hits = np.where(ok2)[0]
        if len(hits) == 0:
            return None
    # zober prvý výskyt, ale over že je to naozaj začiatok (refine ±10ms)
    best = idx[hits[0]]
    # jemné doladenie: hľadaj najlepšiu zhodu v okolí ±10ms
    lo = max(0, best - int(0.010 * fs))
    hi = min(n, best + int(0.010 * fs))
    cand = np.arange(lo, hi, int(0.001 * fs) or 1)
    if len(cand) > 1:
        s = 0
        for c in cand:
            if c + o_vis + w10 > len(avg):
                continue
            e = abs(float(avg[c]) - 1900) + abs(float(avg[c + o_break]) - 1200) + \
                abs(float(avg[c + o_lead2]) - 1900) + abs(float(avg[c + o_vis]) - 1200)
            if s == 0 or e < best_e:
                best_e = e
                best = c
            s += 1
    if verbose:
        print(f"[sstv] hlavička nájdená na {best/fs:.3f} s "
              f"(L1={avg[best]:.0f} Br={avg[best+o_break]:.0f} "
              f"L2={avg[best+o_lead2]:.0f} VIS={avg[best+o_vis]:.0f})", file=sys.stderr)
    return int(best)


def decode_vis(freq, fs, header_start, verbose=False):
    """Dekóduje VIS (8 bitov po 30ms od header+640ms). Vráti (vis_data, parity_ok)."""
    bit_len = int(round(0.030 * fs))
    margin = int(round(0.005 * fs))
    base = header_start + int(round(0.640 * fs))
    bits = []
    for k in range(8):
        s = base + k * bit_len
        e = s + bit_len
        if e > len(freq):
            raise RuntimeError("Súbor je príliš krátky na VIS.")
        seg = freq[s + margin:e - margin]
        m = float(np.mean(seg))
        bits.append(1 if m <= 1200 else 0)
        if verbose:
            print(f"[sstv] VIS bit{k} = {bits[-1]} ({m:.0f} Hz)", file=sys.stderr)
    data = sum(b << i for i, b in enumerate(bits[:7]))
    parity = bits[7]
    parity_ok = ((sum(bits[:7]) + parity) % 2 == 0)
    return data, parity_ok, bits


def refine_sync(freq, expected, sync_len, radius, verbose=False):
    """Jemne dohľadá sync pulz (1200 Hz) okolo expected. Vráti opravený začiatok."""
    lo = max(0, int(expected - radius))
    hi = min(len(freq) - sync_len, int(expected + radius))
    if hi <= lo:
        return int(expected)
    win = freq[lo:hi + sync_len]
    c = np.cumsum(np.insert(win, 0, 0.0))
    avgs = (c[sync_len:] - c[:-sync_len]) / sync_len
    diffs = np.abs(avgs - 1200.0)
    best = int(np.argmin(diffs))
    best_avg = float(avgs[best])
    if best_avg > 1400:
        return int(expected)  # sync sa nenašiel, drž očakávanú polohu
    return int(lo + best)


def sample_pixels(freq, fs, start_sec, pixel_sec, count, frac=0.7):
    """Navzorkuje `count` pixelov od start_sec, každý pixel_sec dlhý.
    Priemeruje stredných frac (0.7) pixela, vráti pole 0..255."""
    out = np.empty(count, dtype=np.float32)
    px = pixel_sec * fs
    margin = px * (1.0 - frac) / 2.0
    for i in range(count):
        s = start_sec * fs + i * px
        a = int(round(s + margin))
        b = int(round(s + px - margin))
        a = max(0, a)
        b = min(len(freq), b)
        if b <= a:
            out[i] = 0
        else:
            m = float(np.mean(freq[a:b]))
            v = (m - 1500.0) / 800.0 * 255.0
            out[i] = 0 if v < 0 else (255 if v > 255 else v)
    return out


def ycbcr_to_rgb(y, cb, cr):
    """BT.601 full-range YCbCr -> RGB, vstupy 0..255."""
    y = y.astype(np.float32)
    cb = cb.astype(np.float32) - 128.0
    cr = cr.astype(np.float32) - 128.0
    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb
    rgb = np.stack([r, g, b], axis=-1)
    return np.clip(rgb, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Dekódovanie jednotlivých rodín
# ---------------------------------------------------------------------------

def decode_martin(freq, fs, vis_end, m, use_sync=True, verbose=False):
    W, H = m["width"], m["height"]
    sync, porch, px = m["sync"] / 1000.0, m["porch"] / 1000.0, m["pixel"] / 1000.0
    scan = W * px
    line_dur = sync + 4 * porch + 3 * scan
    sync_n = int(round(sync * fs))
    img = np.zeros((H, W, 3), dtype=np.uint8)
    line_start = float(vis_end) / fs
    radius = int(round(0.005 * fs))
    for ln in range(H):
        if use_sync and ln > 0:
            exp = int(round(line_start * fs))
            line_start = refine_sync(freq, exp, sync_n, radius) / fs
        g0 = line_start + sync + porch
        b0 = g0 + scan + porch
        r0 = b0 + scan + porch
        g = sample_pixels(freq, fs, g0, px, W)
        b = sample_pixels(freq, fs, b0, px, W)
        r = sample_pixels(freq, fs, r0, px, W)
        img[ln, :, 0] = r.astype(np.uint8)
        img[ln, :, 1] = g.astype(np.uint8)
        img[ln, :, 2] = b.astype(np.uint8)
        if verbose and (ln % 32 == 0 or ln == H - 1):
            print(f"[sstv] {m['id']} riadok {ln+1}/{H}", file=sys.stderr)
        line_start += line_dur
    return Image.fromarray(img, "RGB")


def decode_scottie(freq, fs, vis_end, m, use_sync=True, verbose=False):
    W, H = m["width"], m["height"]
    sync, porch, px = m["sync"] / 1000.0, m["porch"] / 1000.0, m["pixel"] / 1000.0
    scan = W * px
    line_dur = 3 * porch + 3 * scan + sync
    # prvý starting sync 9ms sa preskočí
    line_start = float(vis_end) / fs + sync
    sync_n = int(round(sync * fs))
    radius = int(round(0.004 * fs))
    img = np.zeros((H, W, 3), dtype=np.uint8)
    for ln in range(H):
        if use_sync and ln > 0:
            # sync je v strede riadka: porch+G+porch+B |SYNC| porch+R
            # očakávaný začiatok mid-syncu:
            exp_mid = int(round((line_start + 2 * porch + 2 * scan) * fs))
            best_mid = refine_sync(freq, exp_mid, sync_n, radius)
            line_start = best_mid / fs - (2 * porch + 2 * scan)
        g0 = line_start + porch
        b0 = line_start + 2 * porch + scan
        r0 = line_start + 3 * porch + 2 * scan + sync
        g = sample_pixels(freq, fs, g0, px, W)
        b = sample_pixels(freq, fs, b0, px, W)
        r = sample_pixels(freq, fs, r0, px, W)
        img[ln, :, 0] = r.astype(np.uint8)
        img[ln, :, 1] = g.astype(np.uint8)
        img[ln, :, 2] = b.astype(np.uint8)
        if verbose and (ln % 32 == 0 or ln == H - 1):
            print(f"[sstv] {m['id']} riadok {ln+1}/{H}", file=sys.stderr)
        line_start += line_dur
    return Image.fromarray(img, "RGB")


def decode_bw(freq, fs, vis_end, m, use_sync=True, verbose=False):
    W, H = m["width"], m["height"]
    sync, px = m["sync"] / 1000.0, m["pixel"] / 1000.0
    scan = W * px
    line_dur = sync + scan
    sync_n = int(round(sync * fs))
    img = np.zeros((H, W), dtype=np.uint8)
    line_start = float(vis_end) / fs
    radius = int(round(0.005 * fs))
    for ln in range(H):
        if use_sync and ln > 0:
            exp = int(round(line_start * fs))
            line_start = refine_sync(freq, exp, sync_n, radius) / fs
        s0 = line_start + sync
        v = sample_pixels(freq, fs, s0, px, W)
        img[ln, :] = v.astype(np.uint8)
        if verbose and (ln % 64 == 0 or ln == H - 1):
            print(f"[sstv] {m['id']} riadok {ln+1}/{H}", file=sys.stderr)
        line_start += line_dur
    return Image.fromarray(img, "L").convert("RGB")


def decode_robot_full(freq, fs, vis_end, m, use_sync=True, verbose=False):
    # C24, C72: každý riadok Y + RY + BY
    W, H = m["width"], m["height"]
    sync = m["sync"] / 1000.0
    porch = m["porch"] / 1000.0
    porch2 = m["porch2"] / 1000.0
    sep = m["sep"] / 1000.0
    sep2 = m["sep2"] / 1000.0
    px, px2 = m["pixel"] / 1000.0, m["pixel2"] / 1000.0
    ysc = W * px
    rsc = W * px2
    bsc = W * px2
    line_dur = sync + porch + ysc + sep + porch2 + rsc + sep2 + porch2 + bsc
    sync_n = int(round(sync * fs))
    Y = np.zeros((H, W), dtype=np.float32)
    Cb = np.zeros((H, W), dtype=np.float32)
    Cr = np.zeros((H, W), dtype=np.float32)
    line_start = float(vis_end) / fs
    radius = int(round(0.005 * fs))
    for ln in range(H):
        if use_sync and ln > 0:
            exp = int(round(line_start * fs))
            line_start = refine_sync(freq, exp, sync_n, radius) / fs
        y0 = line_start + sync + porch
        r0 = y0 + ysc + sep + porch2
        b0 = r0 + rsc + sep2 + porch2
        Y[ln] = sample_pixels(freq, fs, y0, px, W)
        Cr[ln] = sample_pixels(freq, fs, r0, px2, W)
        Cb[ln] = sample_pixels(freq, fs, b0, px2, W)
        if verbose and (ln % 48 == 0 or ln == H - 1):
            print(f"[sstv] {m['id']} riadok {ln+1}/{H}", file=sys.stderr)
        line_start += line_dur
    rgb = ycbcr_to_rgb(Y, Cb, Cr)
    return Image.fromarray(rgb, "RGB")


def decode_robot_half(freq, fs, vis_end, m, use_sync=True, verbose=False):
    # C12, C36: Y každý riadok + striedavo Cr/Cb (priemer 2 riadkov pri vysielaní)
    W, H = m["width"], m["height"]
    sync = m["sync"] / 1000.0
    porch = m["porch"] / 1000.0
    porch2 = m["porch2"] / 1000.0
    sep = m["sep"] / 1000.0
    px, px2 = m["pixel"] / 1000.0, m["pixel2"] / 1000.0
    ysc = W * px
    csc = W * px2
    line_dur = sync + porch + ysc + sep + porch2 + csc
    sync_n = int(round(sync * fs))
    Y = np.zeros((H, W), dtype=np.float32)
    Cb = np.zeros((H, W), dtype=np.float32)
    Cr = np.zeros((H, W), dtype=np.float32)
    line_start = float(vis_end) / fs
    radius = int(round(0.005 * fs))
    for ln in range(H):
        if use_sync and ln > 0:
            exp = int(round(line_start * fs))
            line_start = refine_sync(freq, exp, sync_n, radius) / fs
        y0 = line_start + sync + porch
        c0 = y0 + ysc + sep + porch2
        Y[ln] = sample_pixels(freq, fs, y0, px, W)
        c = sample_pixels(freq, fs, c0, px2, W)
        if ln % 2 == 0:
            Cr[ln] = c
        else:
            Cb[ln] = c
        if verbose and (ln % 48 == 0 or ln == H - 1):
            print(f"[sstv] {m['id']} riadok {ln+1}/{H}", file=sys.stderr)
        line_start += line_dur
    # doplň chýbajúcu chromu z vedľajšieho riadka ( Interpolácia )
    for ln in range(H):
        if ln % 2 == 0:
            # párny: Cr vlastná, Cb zo suseda
            if ln + 1 < H and np.max(Cb[ln + 1]) > 0:
                Cb[ln] = Cb[ln + 1]
            elif ln - 1 >= 0:
                Cb[ln] = Cb[ln - 1]
            else:
                Cb[ln] = 128
        else:
            if ln - 1 >= 0:
                Cr[ln] = Cr[ln - 1]
            else:
                Cr[ln] = 128
    rgb = ycbcr_to_rgb(Y, Cb, Cr)
    return Image.fromarray(rgb, "RGB")


def decode_pd(freq, fs, vis_end, m, use_sync=True, verbose=False):
    W, H = m["width"], m["height"]
    assert H % 2 == 0
    sync = m["sync"] / 1000.0
    porch = m["porch"] / 1000.0
    px = m["pixel"] / 1000.0
    sc = W * px
    block_dur = sync + porch + 4 * sc
    sync_n = int(round(sync * fs))
    Y = np.zeros((H, W), dtype=np.float32)
    Cb = np.zeros((H, W), dtype=np.float32)
    Cr = np.zeros((H, W), dtype=np.float32)
    block_start = float(vis_end) / fs
    radius = int(round(0.006 * fs))
    nb = H // 2
    for k in range(nb):
        if use_sync and k > 0:
            exp = int(round(block_start * fs))
            block_start = refine_sync(freq, exp, sync_n, radius) / fs
        y0 = block_start + sync + porch
        r0 = y0 + sc
        b0 = r0 + sc
        y1 = b0 + sc
        l0, l1 = 2 * k, 2 * k + 1
        Y[l0] = sample_pixels(freq, fs, y0, px, W)
        Cr[l0] = Cr[l1] = sample_pixels(freq, fs, r0, px, W)
        Cb[l0] = Cb[l1] = sample_pixels(freq, fs, b0, px, W)
        Y[l1] = sample_pixels(freq, fs, y1, px, W)
        if verbose and (k % 32 == 0 or k == nb - 1):
            print(f"[sstv] {m['id']} blok {k+1}/{nb} (riadky {l0+1}-{l1+1})", file=sys.stderr)
        block_start += block_dur
    rgb = ycbcr_to_rgb(Y, Cb, Cr)
    return Image.fromarray(rgb, "RGB")


def decode_image(freq, fs, vis_end, m, use_sync=True, verbose=False):
    ct = m["ctype"]
    if m["family"] == "martin":
        return decode_martin(freq, fs, vis_end, m, use_sync, verbose)
    if m["family"] == "scottie":
        return decode_scottie(freq, fs, vis_end, m, use_sync, verbose)
    if ct == "BW":
        return decode_bw(freq, fs, vis_end, m, use_sync, verbose)
    if ct == "YUV-FULL":
        return decode_robot_full(freq, fs, vis_end, m, use_sync, verbose)
    if ct == "YUV-HALF":
        return decode_robot_half(freq, fs, vis_end, m, use_sync, verbose)
    if ct == "YUV-PD":
        return decode_pd(freq, fs, vis_end, m, use_sync, verbose)
    if ct == "RGB":
        # fallback
        return decode_martin(freq, fs, vis_end, m, use_sync, verbose)
    raise RuntimeError(f"Neznámy typ farieb: {ct}")


def resolve_mode(name):
    if name is None or name.lower() in ("auto", "any"):
        return None
    k = name.strip().lower()
    if k in MODES:
        # vráť kanonický záznam
        m = MODES[k]
        # nájdi kanonické id
        for cid in _CANON:
            if MODES[cid] is m:
                return cid, m
        return k, m
    raise ValueError(f"Neznámy mód '{name}'. Použi --list-modes.")


def list_modes():
    print("Podporované SSTV módy (dekodér):\n")
    for cid in _CANON:
        m = MODES[cid]
        viss = ",".join(str(v) for v in m["vis"])
        print(f"  {cid:10s}  VIS {viss:12s}  {m['width']:3d}x{m['height']:<3d}  {m['label']}")
    print("\nAliasy: m1,m2,m3,m4, s1,s2,s3,s4,sdx/dx, r8,r12,r36,r72, pd50..pd290, fax480, ...")


def main():
    ap = argparse.ArgumentParser(
        description="Jednoduchý SSTV dekodér: wav/mp3 -> obrázok. "
                    "Podpora Robot, Martin, Scottie, FAX480, PD. Auto-detekcia cez VIS.",
        formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("vstup", nargs="?", help="vstupný audio súbor (wav, mp3, ogg, flac, ...)")
    ap.add_argument("vystup", nargs="?", help="výstupný obrázok (png, jpg, ...)")
    ap.add_argument("-m", "--mode", default="auto",
                    help="mód dekódovania (default auto = detekcia z VIS).\n"
                         "Príklady: robot36, robot72, robot8, robot12,\n"
                         "martin1..martin4, scottie1..scottie4, scottiedx,\n"
                         "fax480, pd50,pd90,pd120,pd160,pd180,pd240,pd290")
    ap.add_argument("--list-modes", action="store_true", help="vypíš podporované módy a skonči")
    ap.add_argument("--skip", type=float, default=0.0, help="preskoč N sekúnd od začiatku (default 0)")
    ap.add_argument("--no-sync", action="store_true", help="vypni sledovanie sync pulzov (čistý free-run)")
    ap.add_argument("-v", "--verbose", action="store_true", help="podrobný výpis")
    ap.add_argument("--no-vis", action="store_true",
                    help="nevyžaduj hlavičku/VIS, dekóduj od --skip s daným --mode\n"
                         "(vhodné pre nahrávky bez hlavičky)")
    args = ap.parse_args()

    if args.list_modes:
        list_modes()
        return 0
    if not args.vstup or not args.vystup:
        ap.print_help()
        print("\nPríklad: python3 sstv_decode.py nahravka.mp3 obrazok.png", file=sys.stderr)
        print("         python3 sstv_decode.py nahravka.wav obrazok.png --mode pd120", file=sys.stderr)
        return 2

    try:
        forced = resolve_mode(args.mode) if args.mode.lower() != "auto" else (None, None)
    except ValueError as e:
        print(f"Chyba: {e}", file=sys.stderr)
        return 2
    use_sync = not args.no_sync

    try:
        samples, fs = load_audio(args.vstup, TARGET_SR, verbose=args.verbose)
    except FileNotFoundError as e:
        print(f"Chyba: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Chyba: {e}", file=sys.stderr)
        print("TIP: nainštaluj ffmpeg (sudo apt install ffmpeg) pre mp3/ogg podporu.", file=sys.stderr)
        return 1

    if args.skip > 0:
        samples = samples[int(args.skip * fs):]

    if len(samples) < fs * 5:
        print("Chyba: audio je príliš krátke (<5 s).", file=sys.stderr)
        return 1

    freq = fm_demod(samples, fs, verbose=args.verbose)

    header = None
    vis_data = None
    mode_id, mode = forced[0], forced[1]

    if not args.no_vis:
        header = find_header(freq, fs, verbose=args.verbose)
        if header is None:
            if forced[0] is None:
                print("Chyba: nenašla sa kalibračná hlavička (1900/1200/1900).", file=sys.stderr)
                print("TIP: skús --mode <meno> --no-vis --skip <sekundy> pre manuálne dekódovanie,", file=sys.stderr)
                print("     alebo skontroluj že súbor naozaj obsahuje SSTV signál.", file=sys.stderr)
                return 1
            else:
                print("[sstv] hlavička sa nenašla, používam manuálny mód bez VIS.", file=sys.stderr)
                vis_end = int(0)
        else:
            try:
                vis_data, parity_ok, bits = decode_vis(freq, fs, header, verbose=args.verbose)
            except RuntimeError as e:
                print(f"Chyba VIS: {e}", file=sys.stderr)
                return 1
            if not parity_ok and args.verbose:
                print("[sstv] VAROVANIE: chybná parita VIS (ignorujem).", file=sys.stderr)
            print(f"[sstv] VIS data = {vis_data} (parita {'OK' if parity_ok else 'CHYBA'})", file=sys.stderr)
            if forced[0] is None:
                if vis_data not in VIS_MAP:
                    print(f"Chyba: nepodporovaný VIS kód {vis_data}.", file=sys.stderr)
                    print("Použi --list-modes a skús --mode manuálne.", file=sys.stderr)
                    return 1
                mode_id = VIS_MAP[vis_data]
                mode = MODES[mode_id]
                print(f"[sstv] detegovaný mód: {mode_id} - {mode['label']}", file=sys.stderr)
            else:
                # porovnaj
                auto_id = VIS_MAP.get(vis_data)
                if auto_id and auto_id != forced[0]:
                    print(f"[sstv] VAROVANIE: VIS hovorí {auto_id}, ale nútiš {forced[0]}. "
                          f"Používam {forced[0]}.", file=sys.stderr)
                mode_id, mode = forced[0], forced[1]
            vis_end = header + int(round(0.910 * fs))
    else:
        if forced[0] is None:
            print("Chyba: s --no-vis musíš zadať --mode.", file=sys.stderr)
            return 1
        mode_id, mode = forced[0], forced[1]
        # bez hlavičky: obraz začína hneď (alebo po skipe)
        vis_end = 0
        print(f"[sstv] manuálny mód bez VIS: {mode_id}", file=sys.stderr)

    print(f"[sstv] dekódujem {mode_id} ({mode['width']}x{mode['height']}) "
          f"sync={'on' if use_sync else 'off'} ...", file=sys.stderr)
    try:
        img = decode_image(freq, fs, vis_end, mode, use_sync=use_sync, verbose=args.verbose)
    except Exception as e:
        print(f"Chyba pri dekódovaní obrazu: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

    try:
        img.save(args.vystup)
    except Exception as e:
        print(f"Chyba pri ukladaní {args.vystup}: {e}", file=sys.stderr)
        return 1
    print(f"[sstv] HOTOVO: {args.vystup} ({img.size[0]}x{img.size[1]}, mód {mode_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
