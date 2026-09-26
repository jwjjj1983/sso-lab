#!/usr/bin/env bash
# Run the whole lab locally:
#   backend (all actors, one process)  http://{idp,app-a,app-b}.localhost:8000
#   SPA with hot reload                http://app-a.localhost:5173   <- open this
set -euo pipefail
cd "$(dirname "$0")/.."

export SSO_LAB_ROLE=all
export SSO_LAB_IDP_URL=http://idp.localhost:8000
export SSO_LAB_APP_A_URL=http://app-a.localhost:5173   # App A is reached through Vite in dev
export SSO_LAB_APP_B_URL=http://app-b.localhost:8000
export SSO_LAB_BACKCHANNEL_LOOPBACK=127.0.0.1:8000

trap 'kill 0' EXIT INT TERM
(cd backend && uv run uvicorn sso_lab.main:create_app --factory --reload \
  --host 127.0.0.1 --port 8000) &
(cd frontend && pnpm dev) &
wait
