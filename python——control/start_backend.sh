#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZERG_ROOT="${ZERG_ROOT:-${APP_DIR}/../../ZERG-SDK}"
JAKA_SDK_PATH="${JAKA_SDK_DIR:-${APP_DIR}/../../JAKA_Mini2_Python_Test/sdk}"

set +u
source /opt/ros/humble/setup.bash
source "${ZERG_ROOT}/install/setup.bash"
set -u
export JAKA_SDK_DIR="${JAKA_SDK_PATH}"
export LD_LIBRARY_PATH="${JAKA_SDK_PATH}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export PYTHONPATH="${JAKA_SDK_PATH}:${ZERG_ROOT}/zerg_sdk:/usr/lib/python3/dist-packages${PYTHONPATH:+:${PYTHONPATH}}"

cd "${APP_DIR}"
exec .venv/bin/python server.py
