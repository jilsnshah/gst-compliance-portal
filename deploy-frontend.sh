#!/usr/bin/env bash
# Deploys the frontend to Vercel against the tunnel that is actually live.
#
# Quick-tunnel hostnames change on every restart and the logs keep every one
# they have ever had, so reading "the last URL in the logs" is unreliable --
# it has silently shipped a dead hostname more than once. This asks each
# candidate whether it answers before building anything.

set -euo pipefail
cd "$(dirname "$0")"

echo "Looking for a live tunnel..."
LIVE=""
# Newest first: reverse the URLs the tunnel container has announced.
for host in $(docker compose logs tunnel 2>&1 \
    | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' \
    | awk '!seen[$0]++' | tail -r 2>/dev/null || true); do
  printf '  %s ... ' "$host"
  code=$(curl -s --max-time 20 -o /dev/null -w '%{http_code}' "$host/health" || echo 000)
  echo "$code"
  if [ "$code" = "200" ]; then LIVE="$host"; break; fi
done

if [ -z "$LIVE" ]; then
  echo
  echo "No live tunnel. Check that cloudflared connected:"
  echo "  docker compose logs --tail 40 tunnel"
  echo "A 'dial tcp ...:7844' error means the network is blocking cloudflared."
  exit 1
fi

echo
echo "Deploying against $LIVE"
cd frontend
npx --yes vercel@latest deploy --prod --yes --archive=tgz -b VITE_API_URL="$LIVE"
