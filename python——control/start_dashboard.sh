#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${APP_DIR}/frontend"
JAKA_SDK_PATH="${JAKA_SDK_DIR:-${APP_DIR}/../../JAKA_Mini2_Python_Test/sdk}"
PYTHON_BIN="${APP_DIR}/.venv/bin/python"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Missing Python environment: ${PYTHON_BIN}" >&2
  echo "Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
if [[ ! -f "${JAKA_SDK_PATH}/jkrc.so" ]]; then
  echo "Missing JAKA SDK: ${JAKA_SDK_PATH}/jkrc.so" >&2
  exit 1
fi
if [[ ! -x "${FRONTEND_DIR}/node_modules/.bin/vite" ]]; then
  echo "Missing frontend dependencies. Run: cd frontend && npm ci" >&2
  exit 1
fi

export JAKA_SDK_DIR="${JAKA_SDK_PATH}"
export LD_LIBRARY_PATH="${JAKA_SDK_PATH}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
export ZERG_ROOT="${ZERG_ROOT:-${APP_DIR}/../../ZERG-SDK}"

if [[ -f /opt/ros/humble/setup.bash && -f "${ZERG_ROOT}/install/setup.bash" ]]; then
  # Keep a persistent ROS2 ActionClient in the backend to avoid CLI discovery latency.
  set +u
  source /opt/ros/humble/setup.bash
  source "${ZERG_ROOT}/install/setup.bash"
  set -u
fi
export PYTHONPATH="${JAKA_SDK_PATH}:${ZERG_ROOT}/zerg_sdk:/usr/lib/python3/dist-packages${PYTHONPATH:+:${PYTHONPATH}}"

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  [[ -n "${BACKEND_PID:-}" ]] && kill "${BACKEND_PID}" 2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "${FRONTEND_PID}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit "${status}"
}
trap cleanup EXIT INT TERM

cd "${APP_DIR}"
"${PYTHON_BIN}" server.py &
BACKEND_PID=$!

cd "${FRONTEND_DIR}"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!

echo "Dashboard: http://127.0.0.1:5173"
echo "API:       http://127.0.0.1:8000"
wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
