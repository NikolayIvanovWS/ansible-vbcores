# ansible-vbcores

Ansible-плейбук для автоматической подготовки образа ОС на базе Ubuntu 24.04 Server для устройств на электронике VBCores (в частности, для образовательного ровера BRover-E5 под управлением Raspberry Pi 5). Позволяет полностью настроить систему: от базовых параметров до ROS 2, драйверов, веб-интерфейса и финальной очистки образа перед распространением.

## Состав ролей

| Роль | Назначение |
|------|------------|
| common | Базовая настройка ОС: локаль, часовой пояс, пароль, hostname, отключение автообновлений, очистка snapd/cloud-init, swap, сеть (Wi-Fi/eth), скрипты расширения SD-карты и диагностики питания. |
| ros2 | Установка ROS 2 Jazzy (репозиторий, ros-base, дополнительные пакеты), настройка Fast DDS discovery-сервера, sysctl-оптимизации. |
| canhat | Поддержка CAN-шины: оверлей Seeed CAN-FD HAT v2, скрипты инициализации CAN, установка Yakut, PyCyphal, компиляция Cyphal-типов (стандартных и Voltbro). |
| vscode | Установка VS Code Server (code-server) через официальный installer, настройка парольного доступа, открытие порта 8090, предустановка Python/Pylance-расширений. |
| brover_soft | Исходный код и зависимости ровера: клонирование репозиториев (brover, cyphal_ros2_bridge, brover_web), сборка, настройка systemd-сервиса ros_nodes, конфигурационные файлы (.ros_params, .bashrc), udev-правило для IMU, установка системных зависимостей, смена hostname на brover01, запись IMAGE_VERSION в /etc/os-release, замена /boot/firmware/config.txt. |
| network-fallback | Резервный DHCP-сервер на eth0: при отсутствии DHCP робот сам становится точкой доступа (192.168.123.1/24) и раздаёт адреса. |
| clean | Подготовка образа к распространению: очистка логов, временных файлов, сброс SSH-ключей, machine-id, apt-кэша, уменьшение journal, восстановление firstboot-механизма и перезагрузка. |

## Требования

- **Управляющая машина:** Ubuntu/Windows WSL с установленным Ansible (рекомендуется версия не ниже 2.15) и доступом в интернет.
- **Целевое устройство:** Raspberry Pi 5 с microSD-картой (рекомендуемый объём 16 ГБ или больше), на которую записан чистый образ Ubuntu 24.04 Server (arm64).
- **Сеть:** робот должен быть доступен по SSH (парольный вход, пользователь `pi` с правами sudo). По умолчанию IP адрес и пароли задаются в файле `hosts`.
- **Питание:** стабильное питание Raspberry Pi на всё время развёртывания (процесс может длиться до 40–60 минут).

## Быстрый старт

1. Запишите чистый образ Ubuntu 24.04 Server для Raspberry Pi 5 на microSD-карту.
2. Вставьте карту в робота, подключите питание и дождитесь загрузки.
3. Подключитесь к роботу по SSH (логин/пароль по умолчанию, если не менялись):

```bash
ssh pi@<ip-адрес>
```
4. Обновите систему и перезагрузите робота:

```bash
sudo apt update -y && sudo apt upgrade -y
sudo reboot
```
5. Склонируйте репозиторий плейбука на свой компьютер:

```bash
git clone https://github.com/NikolayIvanovWS/ansible-vbcores.git
cd ansible-vbcores
```

6. Скорректируйте IP-адрес, пользователя, пароль и sudo-пароль в группе `[canhat]` файла `hosts`.

Пример:

```ini
[canhat]
ubuntu24common ansible_host=192.168.1.48 ansible_ssh_user=pi ansible_ssh_pass=brobro ansible_sudo_pass=brobro ansible_become=yes ansible_become_method=sudo
```

При необходимости также скорректируйте переменные в `group_vars/all.yml`.

7. Запустите полный сценарий настройки:

```bash
ansible-playbook -i hosts raspberry_brover.yml
```
Процесс займёт 40–60 минут. После успешного завершения робот будет готов к работе.

## Подготовка чистого образа для пользователей

После завершения `raspberry_brover.yml` и проверки всех функций робота, выполните:

1. Укажите IP-адрес подготовленного устройства в группе `[clean]` файла `hosts`.

Пример:

```ini
[clean]
brover01 ansible_host=192.168.1.48 ansible_ssh_user=pi ansible_ssh_pass=brobro ansible_sudo_pass=brobro ansible_become=yes ansible_become_method=sudo
```

2. Запустите очистку:

```bash
ansible-playbook -i hosts raspberry_clean.yml
```
Роль `clean`:

- удаляет логи, историю команд, кэши;
- сбрасывает SSH host keys и machine-id (будут сгенерированы уникальные при первой загрузке пользователя);
- очищает apt-кэш и старые пакеты;
- восстанавливает механизм firstboot для автоматического расширения SD-карты;
- перезагружает устройство.

После перезагрузки выключите робота, извлеките microSD и создайте образ для распространения.

### Установка PiShrink и подготовка каталога
Эта утилита понадобится, чтобы обрезать пустое пространство в финальном образе.

```bash
mkdir -p ~/OS_image && cd ~/OS_image
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh
sudo mv pishrink.sh /usr/local/bin
```

### Определение имени SD-карты
Вставьте карту в компьютер c Ubuntu и найдите её имя по размеру (например, /dev/sdc). Важно не перепутать с системным диском.

```bash
lsblk
```

### Создание и оптимизация образа
Последовательно выполните эти команды. Замените /dev/sdc на имя вашего устройства.

Скопировать данные в .img файл:

```bash
sudo dd bs=4M status=progress if=/dev/sdc of=broverOS_v.2.X.img
```

Удалить из образа пустое пространство:

```bash
sudo pishrink.sh ./broverOS_v.2.X.img
```

Сжать образ в архив:

```bash
gzip broverOS_v.2.X.img
```

Готовый файл broverOS_v.2.X.img.gz можно загружать в GitHub Releases или передавать пользователям. Для записи на microSD пользователям достаточно будет использовать Raspberry Pi Imager.

Полученный образ полностью настроен и готов к использованию конечными пользователями.
