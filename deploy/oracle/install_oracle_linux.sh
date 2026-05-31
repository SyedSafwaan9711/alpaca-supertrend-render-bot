#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-opc}"
APP_DIR="${APP_DIR:-/opt/alpaca-supertrend-bot}"
REPO_URL="${REPO_URL:-https://github.com/SyedSafwaan9711/alpaca-supertrend-render-bot.git}"
BRANCH="${BRANCH:-main}"
ENV_FILE="${ENV_FILE:-/etc/alpaca-supertrend-bot.env}"
SERVICE_NAME="${SERVICE_NAME:-alpaca-supertrend-bot}"

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo -E bash "$0" "$@"
fi

if ! id "${APP_USER}" >/dev/null 2>&1; then
  echo "User ${APP_USER} does not exist" >&2
  exit 1
fi

dnf install -y git python3 python3-pip python3-setuptools curl

install -d -o "${APP_USER}" -g "${APP_USER}" "${APP_DIR}"

if [[ -d "${APP_DIR}/.git" ]]; then
  sudo -u "${APP_USER}" git -C "${APP_DIR}" fetch origin "${BRANCH}"
  sudo -u "${APP_USER}" git -C "${APP_DIR}" checkout "${BRANCH}"
  sudo -u "${APP_USER}" git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
else
  if [[ -n "$(find "${APP_DIR}" -mindepth 1 -print -quit)" ]]; then
    echo "${APP_DIR} is not empty and is not a Git checkout" >&2
    exit 1
  fi
  sudo -u "${APP_USER}" git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/python" -m pip install -r "${APP_DIR}/requirements.txt"

if [[ ! -f "${ENV_FILE}" ]]; then
  install -m 600 -o root -g root /dev/null "${ENV_FILE}"
  cat >"${ENV_FILE}" <<'ENV'
ALPACA_API_KEY=your-paper-key
ALPACA_SECRET_KEY=your-paper-secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
TRADING_MODE=paper
BOT_MODE=ASSIST
ADMIN_TOKEN=replace-with-a-long-random-token
SYMBOLS=BTC/USD
TIMEFRAME=1Min
POSITION_SIZE_PCT=1
MAX_DAILY_LOSS_PCT=5
COOLDOWN_MINUTES=10
MAX_OPEN_POSITIONS=1
ORDER_INTERVAL_SECONDS=60
LOG_LEVEL=INFO
DRY_RUN=true
HOST=127.0.0.1
PORT=8000
ALLOW_LIVE_TRADING=false
ENV
  echo "Created ${ENV_FILE}. Add real paper keys/admin token, then rerun this script." >&2
  exit 2
fi

chmod 600 "${ENV_FILE}"
chown root:root "${ENV_FILE}"

cat >"/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Alpaca Supertrend Crypto Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${APP_DIR}/.venv/bin/python app.py
Restart=always
RestartSec=10
KillSignal=SIGINT
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=${APP_DIR}

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

systemctl --no-pager --lines=30 status "${SERVICE_NAME}" || true

PORT="$(grep -E '^PORT=' "${ENV_FILE}" | tail -n 1 | cut -d= -f2-)"
curl -fsS "http://127.0.0.1:${PORT:-8000}/health" || true
echo
