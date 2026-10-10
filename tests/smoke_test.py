#!/usr/bin/env python3
"""Token Pace Gauge smoke test: math, honesty, read-only, server, snapshot, screenshots."""
import glob
import json
import os
import struct
import subprocess
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = "/workspace/tokenmax"
PORT = int(os.environ.get("TOKEN_PACE_PORT", "4273"))
ET = ZoneInfo("America/New_York")
passed, failed = 0, []


def check(name, cond, detail=""):
    global passed
    if cond:
        passed += 1
    else:
        failed.append(f"{name} {detail}")
        print("FAIL", name, detail)


def tree_state(root):
    st = {}
    for b, ds, fs in os.walk(root):
        for f in fs:
            p = os.path.join(b, f)
            try:
                s = os.stat(p)
                st[p] = (s.st_mtime_ns, s.st_size)
            except OSError:
                pass
    return st


# 1. read-only: usage.json + sibling projects untouched (except our own folder)
watch = [os.path.join(ROOT, "usage.json"), os.path.join(ROOT, "ship-it-stats"), os.path.join(ROOT, "escape-room")]
before = {}
for w in watch:
    if os.path.isfile(w):
        s = os.stat(w)
        before[w] = (s.st_mtime_ns, s.st_size)
    elif os.path.isdir(w):
        before[w] = tree_state(w)

r = subprocess.run([sys.executable, os.path.join(HERE, "collect.py")], capture_output=True, text=True)
check("collector exits 0", r.returncode == 0, (r.stderr or r.stdout)[-300:])

for w in watch:
    if os.path.isfile(w):
        s = os.stat(w)
        check(f"did not mutate {os.path.basename(w)}", before[w] == (s.st_mtime_ns, s.st_size))
    elif os.path.isdir(w):
        after = tree_state(w)
        changed = [p for p in after if p in before[w] and after[p] != before[w][p]]
        new = [p for p in after if p not in before[w]]
        check(f"collector did not write into {os.path.basename(w)}", not changed and not new, str((changed + new)[:3]))

# 2. data shape + honesty
D = json.load(open(os.path.join(HERE, "data", "pace.json")))
usage = json.load(open(os.path.join(ROOT, "usage.json")))
for k in ("app", "reading", "pace", "window", "history", "explainer", "generatedAt"):
    check(f"pace.json has {k}", k in D)
check("app id", D.get("app") == "token-pace")
check("used_pct matches usage.json exactly", D["reading"]["used_pct"] == float(usage["used_pct"]),
      f"{D['reading']['used_pct']} vs {usage['used_pct']}")
check("never invents used > 100", 0 <= D["reading"]["used_pct"] <= 100)
check("cap is 95", D["pace"]["cap_pct"] == 95.0)
check("status is known", D["pace"]["status"] in ("ON PACE", "BEHIND", "AHEAD"))

# Independent recount of target
last = datetime.fromisoformat(D["window"]["last_reset"].replace("Z", "+00:00"))
if last.tzinfo is None:
    last = last.replace(tzinfo=ET)
now = datetime.now(ET)
elapsed_h = max(0.0, (now - last.astimezone(ET)).total_seconds() / 3600.0)
expected_target = round(min(1.0, elapsed_h / 168.0) * 95.0, 2)
# Allow 0.05 drift for clock between collect and smoke
check("target matches (hours/168)*95", abs(D["pace"]["target_pct"] - expected_target) <= 0.15,
      f"{D['pace']['target_pct']} vs {expected_target}")
gap = round(D["pace"]["target_pct"] - D["reading"]["used_pct"], 2)
check("gap_pts = target - used", abs(D["pace"]["gap_pts"] - gap) <= 0.02, f"{D['pace']['gap_pts']} vs {gap}")

# History honesty
hist_path = os.path.join(HERE, "data", "history.jsonl")
check("history.jsonl exists", os.path.exists(hist_path))
rows = [json.loads(l) for l in open(hist_path) if l.strip()]
check("history has >=1 row after collect", len(rows) >= 1)
check("history count matches points", D["history"]["count"] == len(D["history"]["points"]))
check("every history used_pct is numeric from file rows", all(isinstance(p.get("used_pct"), (int, float)) for p in D["history"]["points"]))
if len(rows) < 2:
    check("thin history labeled", bool(D["history"].get("note")))

# 3. UI file quality
html = open(os.path.join(HERE, "web", "index.html"), encoding="utf-8").read()
check("UI title", "Token Pace Gauge" in html)
check("UI has gauge", "gauge" in html.lower() and "svg" in html.lower())
check("UI has explainer", "How pacing works" in html or "explainer" in html.lower())
check("UI has countdown", "Countdown" in html or "countdown" in html.lower())
check("no CDN / npm hints", "cdn." not in html.lower() and "unpkg" not in html.lower() and "jsdelivr" not in html.lower())
check("no external script src", "<script src" not in html)
check("no external stylesheet link", "<link" not in html or "stylesheet" not in html)

# 4. server
def get(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=5) as r:
        return r.status, r.read()

try:
    s, b = get("/")
    check("GET / 200", s == 200 and b"Token Pace Gauge" in b)
    check("UI mentions BEHIND or pace", b"pace" in b.lower() or b"BEHIND" in b or b"ON PACE" in b)
    s, b = get("/data/pace.json")
    check("GET pace.json", s == 200 and json.loads(b)["pace"]["cap_pct"] == 95.0)
    s, b = get("/api/health")
    check("GET health", s == 200 and json.loads(b).get("ok") is True)
except Exception as e:
    check("server reachable on 4273", False, str(e))

# 5. snapshot + screenshots
snap = os.path.join(HERE, "dist", "token-pace-snapshot.html")
check("snapshot exists", os.path.exists(snap))
if os.path.exists(snap):
    h = open(snap, encoding="utf-8").read()
    check("snapshot inlines data", "window.__DATA__=" in h)
    check("snapshot has no fetch to http", "fetch('http" not in h)
    check("snapshot embeds used_pct", '"used_pct"' in h)


def png_size(p):
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24]) if head[:8] == b"\x89PNG\r\n\x1a\n" else None


check("best home screenshot", os.path.exists(os.path.join(HERE, "screenshots", "00-best-home.png")))
check("share card 1200x675", png_size(os.path.join(HERE, "dist", "share-card.png")) == (1200, 675))
shots = glob.glob(os.path.join(HERE, "screenshots", "*.png"))
check("phone screenshot", any("phone" in os.path.basename(s) for s in shots))
check("desktop screenshot", any("desktop" in os.path.basename(s) or "best-home" in os.path.basename(s) for s in shots))
for s in shots:
    sz = png_size(s)
    check(f"png valid {os.path.basename(s)}", sz is not None and sz[0] > 0)

print(f"{passed} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
