#!/bin/bash

# Проверка на права суперпользователя
if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Этот скрипт должен быть запущен с правами суперпользователя (sudo)."
    echo "   Пожалуйста, запустите: sudo ./change_hostname.sh"
    exit 1
fi

# 1. Запрос нового имени хоста
read -r -p "Введите НОВОЕ имя хоста (например, pi-server): " NEW_HOSTNAME

# Проверка, что имя не пустое
if [ -z "$NEW_HOSTNAME" ]; then
    echo "❌ Имя хоста не может быть пустым. Отмена."
    exit 1
fi

# Получение текущего имени хоста
OLD_HOSTNAME=$(cat /etc/hostname)

echo ""
echo "Текущее имя хоста: **$OLD_HOSTNAME**"
echo "Новое имя хоста:   **$NEW_HOSTNAME**"
echo "---"

# 2. Обновление файла /etc/hostname
echo "➡️ Обновление файла **/etc/hostname**..."
echo "$NEW_HOSTNAME" > /etc/hostname
if [ $? -eq 0 ]; then
    echo "✅ /etc/hostname обновлен."
else
    echo "❌ Ошибка при записи в /etc/hostname."
fi

# 3. Обновление файла /etc/hosts
echo "➡️ Обновление файла **/etc/hosts**..."

# Ubuntu обычно хранит имя хоста в строке 127.0.1.1.
if grep -qE '^127\.0\.1\.1[[:space:]]+' /etc/hosts; then
    sed -i -E "s/^127\.0\.1\.1[[:space:]]+.*/127.0.1.1\t$NEW_HOSTNAME/" /etc/hosts
else
    echo -e "127.0.1.1\t$NEW_HOSTNAME" >> /etc/hosts
fi

sed -i -E "s/^127\.0\.0\.1[[:space:]]+$OLD_HOSTNAME([[:space:]]|$)/127.0.0.1\t$NEW_HOSTNAME\1/" /etc/hosts
sed -i -E "s/^::1[[:space:]]+$OLD_HOSTNAME([[:space:]]|$)/::1\t$NEW_HOSTNAME\1/" /etc/hosts

if [ $? -eq 0 ]; then
    echo "✅ /etc/hosts обновлен."
else
    echo "❌ Ошибка при обновлении /etc/hosts."
fi

# 4. Немедленное применение нового имени (без перезагрузки)
echo "➡️ Немедленное применение имени хоста..."
hostnamectl set-hostname "$NEW_HOSTNAME"
if [ $? -eq 0 ]; then
    echo "✅ Имя хоста успешно применено."
else
    echo "❌ Ошибка при применении имени хоста через hostnamectl."
fi

# 5. Перезапуск mDNS, чтобы имя .local обновилось в сети
echo "➡️ Перезапуск avahi-daemon для обновления имени .local..."
if systemctl list-unit-files avahi-daemon.service >/dev/null 2>&1; then
    systemctl restart avahi-daemon
    echo "✅ avahi-daemon перезапущен."
else
    echo "⚠️ avahi-daemon не установлен. Имя .local может не работать."
fi

# 6. Завершение
echo ""
echo "🎉 Готово! Имя хоста изменено на **$NEW_HOSTNAME**."
echo "Для полной уверенности рекомендуется **ПЕРЕЗАГРУЗИТЬ** систему."
echo "   sudo reboot"
echo ""

exit 0
