#!/usr/bin/env python3
"""Token Pace Gauge collector.

Reads /workspace/tokenmax/usage.json (and only that for live %), appends a history
row to data/history.jsonl, recomputes straight-line 95%-by-reset pace, and writes
data/pace.json for the UI. Never invents usage percentages.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = "/workspace/tokenmax"
USAGE_PATH = os.path.join(ROOT, "usage.json")
HISTORY_PATH = os.path.join(HERE, "data", "history.jsonl")
OUT_PATH = os.path.join(HERE, "data", "pace.json")
ET = ZoneInfo("America/New_York")

# Canonical weekly pool window: Thu 7:42 PM ET → next Thu 7:42 PM ET (168h).
DEFAULT_RESET_HOUR = 19
DEFAULT_RESET_MINUTE = 42
PACE_CAP_PCT = 95.0  # burn target by reset (not 100%)
WEEK_HOURS = 168.0


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def to_et(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ET)
    return dt.astimezone(ET)


def fmt_et(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(ET).strftime("%Y-%m-%dT%H:%M:%S%z")


def infer_window(usage: dict, now: datetime) -> tuple[datetime, datetime]:
    """Derive last_reset and next_reset from usage.json fields, falling back to Thu 7:42 ET math."""
    reset_at = to_et(parse_iso(usage.get("reset_at")))
    reset_date = usage.get("reset_date")
    if reset_at is None and reset_date:
        try:
            d = datetime.strptime(str(reset_date)[:10], "%Y-%m-%d").date()
            reset_at = datetime(d.year, d.month, d.day, DEFAULT_RESET_HOUR, DEFAULT_RESET_MINUTE, tzinfo=ET)
        except Exception:
            reset_at = None

    if reset_at is not None:
        next_reset = reset_at
        last_reset = next_reset - timedelta(hours=WEEK_HOURS)
        return last_reset, next_reset

    # Fallback: nearest past Thu 7:42 ET and +168h
    # weekday: Mon=0 … Thu=3
    cur = now.astimezone(ET)
    days_since_thu = (cur.weekday() - 3) % 7
    candidate = cur.replace(hour=DEFAULT_RESET_HOUR, minute=DEFAULT_RESET_MINUTE, second=0, microsecond=0) - timedelta(days=days_since_thu)
    if candidate > cur:
        candidate -= timedelta(days=7)
    return candidate, candidate + timedelta(hours=WEEK_HOURS)


def load_history() -> list[dict]:
    rows = []
    if not os.path.exists(HISTORY_PATH):
        return rows
    with open(HISTORY_PATH, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def append_history(row: dict) -> None:
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    # Dedup: skip if last row has same checked_at + used_pct
    prev = load_history()
    if prev:
        last = prev[-1]
        if last.get("checked_at") == row.get("checked_at") and last.get("used_pct") == row.get("used_pct"):
            return
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def status_for(used: float, target: float) -> tuple[str, float]:
    gap = round(target - used, 2)  # positive = behind (need more burn)
    if abs(gap) < 1.0:
        return "ON PACE", gap
    if gap > 0:
        return "BEHIND", gap
    return "AHEAD", gap  # gap negative when ahead of pace


def build() -> dict:
    if not os.path.exists(USAGE_PATH):
        raise SystemExit(f"missing usage file: {USAGE_PATH}")

    with open(USAGE_PATH, encoding="utf-8") as f:
        usage = json.load(f)

    if "used_pct" not in usage:
        raise SystemExit("usage.json missing used_pct — refusing to invent")

    used_pct = float(usage["used_pct"])
    now = datetime.now(ET)
    checked_at = to_et(parse_iso(usage.get("checked_at"))) or now
    last_reset, next_reset = infer_window(usage, now)

    # Prefer live "now" for elapsed / countdown; checked_at for labeling the reading.
    elapsed_h = max(0.0, (now - last_reset).total_seconds() / 3600.0)
    remaining_h = max(0.0, (next_reset - now).total_seconds() / 3600.0)
    week_frac = min(1.0, elapsed_h / WEEK_HOURS)
    week_elapsed_pct = round(week_frac * 100.0, 2)
    target_pct = round(week_frac * PACE_CAP_PCT, 2)
    status, gap_pts = status_for(used_pct, target_pct)

    # Projected end-of-week % if current burn rate continues (hours since reset).
    # If elapsed is tiny, avoid divide-by-zero; label as insufficient.
    if elapsed_h >= 0.25:
        rate_per_hour = used_pct / elapsed_h
        projected_eow = round(min(100.0, rate_per_hour * WEEK_HOURS), 2)
        projection_note = "linear from used_pct / hours-since-last-reset × 168h"
    else:
        projected_eow = None
        projection_note = "insufficient elapsed time for projection (<15 min since reset)"

    # Required burn rate to hit 95% by reset (pts per hour from now)
    remain_to_target = max(0.0, PACE_CAP_PCT - used_pct)
    required_pts_per_hour = round(remain_to_target / remaining_h, 3) if remaining_h > 0 else None
    required_pts_per_day = round(required_pts_per_hour * 24, 2) if required_pts_per_hour is not None else None

    hist_row = {
        "checked_at": usage.get("checked_at") or fmt_et(checked_at),
        "recorded_at": fmt_et(now),
        "used_pct": used_pct,
        "target_pct": target_pct,
        "gap_pts": gap_pts,
        "status": status,
        "week_elapsed_pct": week_elapsed_pct,
        "cursor_models_pct": usage.get("cursor_models_pct"),
        "other_models_pct": usage.get("other_models_pct"),
        "on_demand": usage.get("on_demand"),
        "source": usage.get("source"),
        "last_reset": fmt_et(last_reset),
        "next_reset": fmt_et(next_reset),
    }
    append_history(hist_row)
    history = load_history()

    # Sparkline points: only real history rows (never invented).
    spark = []
    for h in history:
        ts = h.get("checked_at") or h.get("recorded_at")
        if h.get("used_pct") is None:
            continue
        spark.append({
            "t": ts,
            "used_pct": h["used_pct"],
            "target_pct": h.get("target_pct"),
            "status": h.get("status"),
        })

    history_note = None
    if len(spark) < 2:
        history_note = (
            "Burn history is thin — only readings appended by this collector exist on disk. "
            "Earlier TokenMax daily checks are not reconstructed; the sparkline will fill as "
            "collect.py runs against fresh usage.json snapshots."
        )

    # Timeline markers (Thu → Thu)
    markers = [
        {"id": "last_reset", "label": "Last reset", "at": fmt_et(last_reset), "kind": "reset"},
        {"id": "now", "label": "Now", "at": fmt_et(now), "kind": "now"},
        {"id": "next_reset", "label": "Next reset", "at": fmt_et(next_reset), "kind": "reset"},
    ]

    # Day ticks for week timeline (local ET calendar days spanning the window)
    day_ticks = []
    d0 = last_reset.astimezone(ET).replace(hour=0, minute=0, second=0, microsecond=0)
    d1 = next_reset.astimezone(ET).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    cur = d0
    while cur <= d1:
        frac = (cur - last_reset).total_seconds() / (WEEK_HOURS * 3600.0)
        day_ticks.append({
            "date": cur.strftime("%Y-%m-%d"),
            "label": cur.strftime("%a %-d"),
            "frac": round(max(0.0, min(1.0, frac)), 4),
        })
        cur += timedelta(days=1)

    payload = {
        "app": "token-pace",
        "title": "Token Pace Gauge",
        "generatedAt": fmt_et(now),
        "timezone": "America/New_York",
        "sourceFile": USAGE_PATH,
        "reading": {
            "used_pct": used_pct,
            "checked_at": usage.get("checked_at"),
            "label": usage.get("label") or "Grok Bot weekly included usage",
            "cursor_models_pct": usage.get("cursor_models_pct"),
            "other_models_pct": usage.get("other_models_pct"),
            "monthly_reset": usage.get("monthly_reset"),
            "on_demand": usage.get("on_demand"),
            "account": usage.get("account"),
            "source": usage.get("source"),
            "reset_note": usage.get("reset_note"),
        },
        "pace": {
            "cap_pct": PACE_CAP_PCT,
            "target_pct": target_pct,
            "gap_pts": gap_pts,
            "status": status,
            "week_elapsed_pct": week_elapsed_pct,
            "elapsed_hours": round(elapsed_h, 2),
            "remaining_hours": round(remaining_h, 2),
            "week_hours": WEEK_HOURS,
            "projected_eow_pct": projected_eow,
            "projection_note": projection_note,
            "required_pts_per_hour": required_pts_per_hour,
            "required_pts_per_day": required_pts_per_day,
            "formula": "target = (hours_since_last_reset / 168) × 95",
        },
        "window": {
            "last_reset": fmt_et(last_reset),
            "next_reset": fmt_et(next_reset),
            "reset_clock": f"{DEFAULT_RESET_HOUR}:{DEFAULT_RESET_MINUTE:02d} ET Thursdays",
            "now_frac": round(week_frac, 4),
            "day_ticks": day_ticks,
            "markers": markers,
        },
        "history": {
            "count": len(spark),
            "points": spark,
            "note": history_note,
            "path": "data/history.jsonl",
        },
        "explainer": {
            "title": "How pacing works",
            "bullets": [
                "Grok Bot weekly included pool resets every Thursday ~7:42 PM ET (168-hour window).",
                "Straight-line target burns toward 95% by reset — leaving a small buffer, not racing to 100%.",
                "target% = (hours since last reset ÷ 168) × 95.",
                "Status: BEHIND if used% is more than ~1 pt under target; AHEAD if more than ~1 pt over; else ON PACE.",
                "gap_pts = target% − used% (positive means behind — need more burn).",
                "Projected end-of-week % assumes today's average burn rate continues to next reset.",
                "Numbers come only from /workspace/tokenmax/usage.json + this app's history.jsonl — never invented.",
                "On-demand is never enabled by this tool; it only reports the dashboard value.",
            ],
        },
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(
        f"wrote {OUT_PATH} used={used_pct}% target={target_pct}% "
        f"status={status} gap={gap_pts} history={len(spark)}"
    )
    return payload


if __name__ == "__main__":
    try:
        build()
    except SystemExit:
        raise
    except Exception as e:
        print(f"collect failed: {e}", file=sys.stderr)
        sys.exit(1)
