# Token Pace Gauge

Wall-worthy pacing dial for Boyd’s **Grok Bot weekly included pool**. Shows live burn vs the straight-line **95%-by-reset** target, week timeline (Thu→Thu), burn history, and countdown to the next Thursday ~7:42 PM ET reset.

## Quick start

```bash
cd /workspace/tokenmax/token-pace
./run.sh          # collect + serve http://127.0.0.1:4273
python3 export_static.py
./screenshot.sh
python3 tests/smoke_test.py
```

Offline snapshot: `dist/token-pace-snapshot.html` (file:// safe, data inlined).

## Pace math (honest)

- Window: last Thursday 7:42 PM ET → next Thursday 7:42 PM ET (168 hours).
- `target% = (hours_since_last_reset / 168) × 95`
- `gap_pts = target% − used%` (positive ⇒ **BEHIND**)
- `used%` comes **only** from `/workspace/tokenmax/usage.json` — never invented.
- Each `collect.py` run appends the current reading to `data/history.jsonl` (deduped on checked_at + used_pct). Thin history is labeled in the UI.

## Layout

| Path | Role |
|------|------|
| `collect.py` | Read usage.json → append history → write `data/pace.json` |
| `web/index.html` | Embedded CSS/JS mission UI (gauge, timeline, sparkline, explainer) |
| `server.py` | Stdlib HTTP on `127.0.0.1:${TOKEN_PACE_PORT:-4273}` |
| `export_static.py` | Inline snapshot to `dist/` |
| `screenshot.sh` | Headless Chrome shots + 1200×675 share card |
| `tests/smoke_test.py` | Math, honesty, read-only, server, assets |

## Port

`TOKEN_PACE_PORT` default **4273**.

## Rules

Python 3 stdlib only. No npm, no CDN, no network at runtime. Does not enable on-demand. Writes only inside this folder.


---
## Repo notes
- **Built:** Oct 2026 (TokenMax build week; see SHORTLIST/ledger), by TokenMax (Boyd's Grok Bot) on the Grok Bot box.
- **Run:** `./run.sh` (then open the localhost URL it prints).
- Imported from `/workspace/tokenmax/token-pace` on Oct 23, 2026. node_modules, virtualenvs, logs and files over 20 MB were left out.
