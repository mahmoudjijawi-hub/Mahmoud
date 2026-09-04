#!/usr/bin/env bash
# مرادف لـ entrypoint.sh حتى يعمل Start Command: bash start.sh
set -euo pipefail
cd "$(dirname "$0")"
exec bash ./entrypoint.sh
