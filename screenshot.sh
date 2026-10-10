#!/usr/bin/env bash
# Desktop + phone screenshots and share card (headless Chrome, live server on :4273).
set -euo pipefail
cd "$(dirname "$0")"
PORT="${TOKEN_PACE_PORT:-4273}"
CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser)"
mkdir -p screenshots dist
shot() {
  local url="$1" out="$2" size="$3"; shift 3 || true
  local prof; prof="$(mktemp -d /tmp/tpaceshot.XXXX)"
  "$CHROME" --headless=new --no-sandbox --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --run-all-compositor-stages-before-draw --virtual-time-budget=12000 \
    --window-size="$size" --user-data-dir="$prof" --screenshot="$out" "$@" "$url" >/dev/null 2>&1
  rm -rf "$prof"; echo "  $out"
}
U="http://127.0.0.1:$PORT"
shot "file://$PWD/dist/token-pace-snapshot.html" screenshots/00-best-home.png 1440,1100
shot "$U/" screenshots/00-best-desktop-top.png 1440,1000
shot "$U/" screenshots/01-desktop-full.png 1440,4200
shot "$U/" screenshots/03-phone-top.png 390,844 --user-agent="Mozilla/5.0 (iPhone)"
shot "$U/" screenshots/04-phone-full.png 390,7000 --user-agent="Mozilla/5.0 (iPhone)"
shot "file://$PWD/dist/token-pace-snapshot.html" screenshots/05-offline-snapshot.png 1440,1100
shot "$U/?view=card" dist/share-card.png 1200,675
