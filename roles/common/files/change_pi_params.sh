#!/bin/bash
set -euo pipefail

TARGET_USER="${SUDO_USER:-pi}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
CODE_SERVER_CONFIG="$TARGET_HOME/.config/code-server/config.yaml"

if [ "$(id -u)" -ne 0 ]; then
    echo "Этот скрипт должен быть запущен с правами суперпользователя."
    echo "Запустите: sudo ./change_pi_params.sh"
    exit 1
fi

if [ -z "$TARGET_HOME" ]; then
    echo "Не удалось определить домашнюю директорию пользователя '$TARGET_USER'."
    exit 1
fi

read -r -p "Введите НОВОЕ имя хоста, например brover02: " NEW_HOSTNAME

if [ -z "$NEW_HOSTNAME" ]; then
    echo "Имя хоста не может быть пустым."
    exit 1
fi

if ! [[ "$NEW_HOSTNAME" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]]; then
    echo "Некорректное имя хоста. Используйте только латинские буквы, цифры и дефисы."
    exit 1
fi

echo ""
read -r -s -p "Введите НОВЫЙ пароль для пользователя '$TARGET_USER' и code-server: " NEW_PASSWORD
echo ""
read -r -s -p "Повторите НОВЫЙ пароль: " NEW_PASSWORD_REPEAT
echo ""

if [ -z "$NEW_PASSWORD" ]; then
    echo "Пароль не может быть пустым."
    exit 1
fi

if [ "$NEW_PASSWORD" != "$NEW_PASSWORD_REPEAT" ]; then
    echo "Пароли не совпадают."
    exit 1
fi

OLD_HOSTNAME="$(cat /etc/hostname)"

echo ""
echo "Текущее имя хоста: $OLD_HOSTNAME"
echo "Новое имя хоста:   $NEW_HOSTNAME"
echo "Пользователь:      $TARGET_USER"
echo "---"

echo "Обновление /etc/hostname..."
echo "$NEW_HOSTNAME" > /etc/hostname

echo "Обновление /etc/hosts..."
if grep -qE '^127\.0\.1\.1[[:space:]]+' /etc/hosts; then
    sed -i -E "s/^127\.0\.1\.1[[:space:]]+.*/127.0.1.1\t$NEW_HOSTNAME/" /etc/hosts
else
    echo -e "127.0.1.1\t$NEW_HOSTNAME" >> /etc/hosts
fi

sed -i -E "s/^127\.0\.0\.1[[:space:]]+$OLD_HOSTNAME([[:space:]]|$)/127.0.0.1\t$NEW_HOSTNAME\1/" /etc/hosts
sed -i -E "s/^::1[[:space:]]+$OLD_HOSTNAME([[:space:]]|$)/::1\t$NEW_HOSTNAME\1/" /etc/hosts

echo "Применение нового имени хоста..."
hostnamectl set-hostname "$NEW_HOSTNAME"

echo "Изменение пароля Linux-пользователя '$TARGET_USER'..."
printf '%s:%s\n' "$TARGET_USER" "$NEW_PASSWORD" | chpasswd

echo "Обновление пароля code-server..."
mkdir -p "$(dirname "$CODE_SERVER_CONFIG")"

python3 - "$CODE_SERVER_CONFIG" "$NEW_PASSWORD" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
password = sys.argv[2]

def yaml_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"

lines = path.read_text().splitlines() if path.exists() else []
out = []
seen_auth = False
seen_password = False

for line in lines:
    stripped = line.lstrip()
    indent = line[:len(line) - len(stripped)]

    if stripped.startswith("auth:"):
        out.append(f"{indent}auth: password")
        seen_auth = True
    elif stripped.startswith("password:"):
        out.append(f"{indent}password: {yaml_single_quote(password)}")
        seen_password = True
    else:
        out.append(line)

if not seen_auth:
    out.append("auth: password")

if not seen_password:
    out.append(f"password: {yaml_single_quote(password)}")

path.write_text("\n".join(out) + "\n")
PY

chown "$TARGET_USER:$TARGET_USER" "$(dirname "$CODE_SERVER_CONFIG")" "$CODE_SERVER_CONFIG"
chmod 700 "$(dirname "$CODE_SERVER_CONFIG")"
chmod 600 "$CODE_SERVER_CONFIG"

echo "Перезапуск avahi-daemon..."
if systemctl list-unit-files avahi-daemon.service >/dev/null 2>&1; then
    systemctl restart avahi-daemon
else
    echo "Предупреждение: avahi-daemon не установлен."
fi

echo ""
echo "Готово."
echo "Имя хоста изменено на: $NEW_HOSTNAME"
echo "Пароль изменен для пользователя: $TARGET_USER"
echo "Конфиг code-server обновлен: $CODE_SERVER_CONFIG"
echo ""
echo "Через 3 секунды Raspberry Pi будет перезагружена..."

for seconds in 3 2 1; do
    echo "$seconds..."
    sleep 1
done

echo "Перезагрузка..."
systemctl reboot