#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/prosto-ubot"

log()  { echo -e "\033[1;36m[→]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[✓]\033[0m $*"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*"; }
die()  { echo -e "\033[1;31m[✗]\033[0m $*" >&2; exit 1; }

if [[ $EUID -ne 0 ]]; then
  die "Запусти от root: sudo bash install.sh"
fi

if ! command -v apt-get >/dev/null 2>&1; then
  die "Поддерживаются только Debian/Ubuntu (apt)."
fi
. /etc/os-release
if [[ "${ID}" != "ubuntu" && "${ID}" != "debian" ]]; then
  warn "ОС ${PRETTY_NAME} не проверялась. Продолжаю."
fi

if ! command -v docker >/dev/null 2>&1; then
  log "Устанавливаю Docker..."
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/${ID}/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  ok "Docker установлен."
else
  ok "Docker уже установлен."
fi

if ! docker compose version >/dev/null 2>&1; then
  die "Плагин docker compose не найден."
fi

if [[ ! -d "$APP_DIR" ]]; then
  mkdir -p "$APP_DIR"
fi
cd "$APP_DIR"

mkdir -p data
chmod 700 data

if [[ ! -f Dockerfile || ! -d app ]]; then
  die "В текущем каталоге нет исходников проекта."
fi

log "Собираю Docker-образ..."
docker compose build

if [[ ! -f data/.env ]]; then
  log "Запускаю мастер настройки..."
  docker compose run --rm ubot python -m app.installer.wizard
  if [[ ! -f data/.env ]]; then
    die "Мастер не создал data/.env."
  fi
  chmod 600 data/.env
  ok "Мастер настройки завершён."
else
  ok "Конфигурация уже существует (data/.env)."
fi

log "Запускаю контейнер..."
docker compose up -d

sleep 2
docker compose ps

cat <<BANNER

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅  U-Bot установлен и запущен.

  Каталог приложения:  $APP_DIR
  База данных:         $APP_DIR/data/ubot.db
  Бэкапы:              $APP_DIR/data/backups/
  Конфигурация:        $APP_DIR/data/.env

  Логи:                cd $APP_DIR && docker compose logs -f
  Остановка:           cd $APP_DIR && docker compose down
  Запуск:              cd $APP_DIR && docker compose up -d
  Перезапуск:          cd $APP_DIR && docker compose restart

  Дальше:
  1) Открой Telegram, напиши боту /start
  2) Добавь бота админом в свои каналы
  3) (Опционально) установи host-agent:
     cd $APP_DIR/host_agent && sudo bash install_agent.sh
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BANNER
