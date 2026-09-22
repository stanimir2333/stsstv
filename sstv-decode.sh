#!/usr/bin/env bash
# Jednoduchý SSTV dekodér (bash wrapper) — wav/mp3 -> obrázok
# Podpora: všetky Robot, všetky Martin, všetky Scottie, FAX480, všetky PD
# Použitie:
#   ./sstv-decode.sh vstup.wav vystup.png
#   ./sstv-decode.sh vstup.mp3 vystup.png --mode pd120
#   ./sstv-decode.sh --list-modes
#   ./sstv-decode.sh --help
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DECODER="$SCRIPT_DIR/sstv_decode.py"

usage() {
cat <<'EOF'
SSTV dekodér (bash + cli) — wav/mp3 -> obrázok

Použitie:
  ./sstv-decode.sh VSTUP VYSTUP [VOĽBY]
  ./sstv-decode.sh --list-modes
  ./sstv-decode.sh --help

Argumenty:
  VSTUP    vstupný audio súbor (wav, mp3, ogg, flac, m4a, ...)
  VYSTUP   výstupný obrázok (png, jpg, bmp, ...)

Voľby (posielajú sa do python dekodéra):
  -m, --mode MÓD    vynúť mód (default: auto = detekcia z VIS)
                    robot8, robot12, robot24bw, robot36bw,
                    robot12c, robot24c, robot36, robot72,
                    martin1, martin2, martin3, martin4,
                    scottie1, scottie2, scottie3, scottie4, scottiedx,
                    fax480,
                    pd50, pd90, pd120, pd160, pd180, pd240, pd290
  --skip SEKUNDY     preskoč N sekúnd od začiatku
  --no-sync          vypni sledovanie sync pulzov
  --no-vis           dekóduj bez hlavičky (vyžaduje --mode + --skip)
  -v, --verbose      podrobný výpis
  --list-modes       vypíš módy
  -h, --help         táto nápoveda

Príklady:
  ./sstv-decode.sh nahravka.wav obrazok.png
  ./sstv-decode.sh nahravka.mp3 obrazok.png -v
  ./sstv-decode.sh nahravka.mp3 obrazok.png --mode martin1
  ./sstv-decode.sh nahravka.wav obrazok.png --mode pd120 --no-sync

Závislosti: python3, numpy, scipy, Pillow, ffmpeg (pre mp3/ogg).
  pip install -r requirements.txt
  sudo apt install ffmpeg   # Debian/Ubuntu
EOF
}

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Chyba: chýba '$1'." >&2
    case "$1" in
      ffmpeg) echo "  Inštalácia: sudo apt install ffmpeg" >&2 ;;
      python3) echo "  Inštalácia: sudo apt install python3" >&2 ;;
    esac
    exit 1
  }
}

need python3

if [[ ! -f "$DECODER" ]]; then
  echo "Chyba: nenašiel sa $DECODER" >&2
  exit 1
fi

# python závislosti — rýchla kontrola
if ! python3 -c "import numpy, scipy, PIL" 2>/dev/null; then
  echo "Chyba: chýbajú python balíky (numpy, scipy, Pillow)." >&2
  echo "  Spusti: pip install -r \"$SCRIPT_DIR/requirements.txt\"" >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  usage
  exit 2
fi

case "${1:-}" in
  -h|--help|help)
    usage
    exit 0
    ;;
  --list-modes)
    exec python3 "$DECODER" --list-modes
    ;;
esac

if [[ $# -lt 2 ]]; then
  echo "Chyba: zadaj VSTUP a VYSTUP. Pozri --help." >&2
  exit 2
fi

IN="$1"; shift
OUT="$1"; shift

if [[ ! -f "$IN" ]]; then
  echo "Chyba: vstupný súbor neexistuje: $IN" >&2
  exit 1
fi

# ffmpeg je povinný pre mp3/ogg, pre wav len ak treba konverzia — skontroluj podľa prípony
EXT="${IN##*.}"
EXT="$(echo "$EXT" | tr '[:upper:]' '[:lower:]')"
if [[ "$EXT" != "wav" ]]; then
  need ffmpeg
fi

OUTDIR="$(dirname "$OUT")"
if [[ "$OUTDIR" != "." && "$OUTDIR" != "" ]]; then
  mkdir -p "$OUTDIR"
fi

exec python3 "$DECODER" "$IN" "$OUT" "$@"
