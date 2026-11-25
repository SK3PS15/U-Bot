#!/usr/bin/env bash
set -euo pipefail

AGENT_DIR="/opt/prosto-ubot-agent"
SHELL_USER="ubot-shell"
BIND_HOST="172.17.0.1"
BIND_PORT="8765"

log()  { echo -e "\033[1;36m[→]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[✓]\033[0m $*"; }
die()  { echo -e "\033[1;31m[✗]\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "Запусти от root: sudo bash install_agent.sh"

log "Проверяю python3..."
command -v python3 >/dev/null || (apt-get update -y && apt-get install -y python3 python3-pip python3-venv)
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || die "Нужен Python 3.8+"

log "Устанавливаю зависимости (aiohttp, psutil)..."
python3 -m pip install --break-system-packages --quiet aiohttp==3.10.5 psutil==6.0.0 2>/dev/null \
  || python3 -m pip install --quiet aiohttp==3.10.5 psutil==6.0.0

if ! id "$SHELL_USER" >/dev/null 2>&1; then
  log "Создаю пользователя $SHELL_USER..."
  useradd -r -m -s /bin/bash "$SHELL_USER"
  ok "Пользователь $SHELL_USER создан."
else
  ok "Пользователь $SHELL_USER уже существует."
fi

log "Копирую файлы в $AGENT_DIR..."
mkdir -p "$AGENT_DIR"
cp -f agent.py "$AGENT_DIR/agent.py"
chmod 644 "$AGENT_DIR/agent.py"

if [[ -f /etc/prosto-ubot-agent.token ]]; then
  TOKEN=$(cat /etc/prosto-ubot-agent.token)
  ok "Использую существующий токен."
else
  TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
  echo -n "$TOKEN" > /etc/prosto-ubot-agent.token
  chmod 600 /etc/prosto-ubot-agent.token
  ok "Токен сгенерирован."
fi

log "Создаю systemd unit..."
cat > /etc/systemd/system/prosto-ubot-agent.service <<UNIT
[Unit]
Description=U-Bot Host Agent
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=${AGENT_DIR}
Environment="AGENT_TOKEN=${TOKEN}"
Environment="SHELL_USER=${SHELL_USER}"
Environment="BIND_HOST=${BIND_HOST}"
Environment="BIND_PORT=${BIND_PORT}"
ExecStart=/usr/bin/python3 ${AGENT_DIR}/agent.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now prosto-ubot-agent

sleep 1
if ! systemctl is-active --quiet prosto-ubot-agent; then
  journalctl -u prosto-ubot-agent -n 20 --no-pager
  die "Host-agent не запустился. Проверь логи выше."
fi
ok "Host-agent запущен."

APP_ENV="/opt/prosto-ubot/data/.env"
if [[ -f "$APP_ENV" ]]; then
  log "Прописываю HOST_AGENT_URL и токен в $APP_ENV..."
  grep -q "^HOST_AGENT_URL=" "$APP_ENV" \
    && sed -i "s|^HOST_AGENT_URL=.*|HOST_AGENT_URL=http://${BIND_HOST}:${BIND_PORT}|" "$APP_ENV" \
    || echo "HOST_AGENT_URL=http://${BIND_HOST}:${BIND_PORT}" >> "$APP_ENV"
  grep -q "^HOST_AGENT_TOKEN=" "$APP_ENV" \
    && sed -i "s|^HOST_AGENT_TOKEN=.*|HOST_AGENT_TOKEN=${TOKEN}|" "$APP_ENV" \
    || echo "HOST_AGENT_TOKEN=${TOKEN}" >> "$APP_ENV"
  chmod 600 "$APP_ENV"
  ok "Настройки записаны."

  log "Перезапускаю контейнер..."
  (cd /opt/prosto-ubot && docker compose up -d)
else
  echo -e "\033[1;33m[!]\033[0m $APP_ENV не найден. Сначала запусти install.sh основного приложения."
fi

cat <<BANNER

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  Host-agent установлен и запущен.

  Адрес:   http://${BIND_HOST}:${BIND_PORT}
  Unit:    prosto-ubot-agent.service
  Пользователь для терминала: ${SHELL_USER}

  Управление:  systemctl status prosto-ubot-agent
  Логи:        journalctl -u prosto-ubot-agent -f

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BANNER
