#!/usr/bin/env bash
# Start Token Pace Gauge in the background (idempotent): collect, then serve on :4273.
cd "$(dirname "$0")"
PORT=${TOKEN_PACE_PORT:-4273}
PIDFILE=data/server.pid
mkdir -p data
python3 collect.py
if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
  echo "Token Pace Gauge already running: http://127.0.0.1:$PORT"; exit 0
fi
# Clear stale pid
rm -f "$PIDFILE"
setsid nohup python3 server.py > data/server.log 2>&1 &
echo $! > "$PIDFILE"
for i in $(seq 1 30); do
  if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo "Token Pace Gauge started (pid $(cat "$PIDFILE")): http://127.0.0.1:$PORT"
    exit 0
  fi
  sleep 0.2
done
echo "Token Pace Gauge failed to start on :$PORT" >&2
tail -20 data/server.log >&2 || true
exit 1
