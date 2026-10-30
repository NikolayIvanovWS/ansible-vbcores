# ansible-vbcores

Ansible-плейбуки для подготовки образов Ubuntu Server 24.04 для ровера BRover-E5 и универсального бортового компьютера VBCores: Raspberry Pi 5 + VBCores CAN FD Raspberry Pi HAT + VBCores CAN FD HAT Quick Connect.

## Состав ролей

| Роль | Назначение |
|------|------------|
| `common` | Базовые параметры ОС: пользователь `pi`, hostname, локаль, часовой пояс, сеть, swap, отключение автообновлений и ненужных служб, удаление snap/cloud-init, скрипты диагностики питания и изменения имени/пароля. |
| `ros2` | ROS 2 Jazzy Base, `ros-dev-tools`, дополнительные ROS-пакеты по настройкам профиля, Fast DDS discovery server и его окружение. |
| `can-yakut` | Настройка CAN0/CAN1 через overlay и udev, CAN-utils, Yakut/PyCyphal, Python-зависимости и типы OpenCyphal/Voltbro. Установка службы настройки питания EEPROM; она остаётся выключенной до этапа `clean`. |
| `vscode` | Веб-редактор code-server на порту `8090`, настройки и Python/Pylance-расширения. Используется в образе ровера. |
| `brover_soft` | Исходники, зависимости и сборка ПО ровера, Cyphal–ROS-мост, веб-интерфейс, запуск ROS-узлов, USB-камер и watchdog видеосервера. |
| `cyphal_workspace` | Общие исходники Cyphal–ROS-моста и его подмодулей. Роль `brover_soft` подключает её задачу `sources.yml`. |
| `network-fallback` | Резервная Ethernet-сеть: если кабель подключён, но DHCP-адрес не получен, плата использует `192.168.123.1/24` и раздаёт адреса подключённым устройствам. |
| `network-wifi-fallback` | Резервная Wi-Fi-точка доступа при отсутствии клиентского подключения: SSID совпадает с hostname, адрес платы `192.168.50.1`, пароль `turtlew001`. Начальное ожидание — 60 секунд. |
| `clean` | Финальная подготовка образа: очистка данных сборки, удаление SSH-ключей, сброс machine-id, включение firstboot и настройки EEPROM, выключение платы. |

Основные сценарии:

| Назначение | Плейбук | Группа в `hosts` | Имя хоста после установки |
|------------|---------|------------------|----------------------------|
| Ровер BRover-E5 | `raspberry_brover.yml` | `[brover]` | `brover01` |
| Универсальный образ | `raspberry_vbcores.yml` | `[vbcores]` | `vbcores01` |
| Подготовка любого из образов к распространению | `raspberry_clean.yml` | `[clean]` | Не изменяется |


## 1. Подготовка microSD

В Raspberry Pi Imager выберите Raspberry Pi 5, последнюю доступную версию **Ubuntu Server 24.04 LTS (64-bit)** и целевую microSD-карту.

Перед записью обязательно задайте параметры ОС:

| Параметр | Значение |
|----------|----------|
| Имя хоста | `ubuntu24common` |
| Имя пользователя | `pi` |
| Пароль пользователя | `brobro` |
| SSID Wi-Fi | `TurtleBro5G` |
| Пароль Wi-Fi | `turtlew001` |
| SSH | Включён |
| Способ аутентификации SSH | По паролю |

Запишите карту, вставьте её в Raspberry Pi и подключите питание. Дождитесь первой загрузки. В веб-интерфейсе роутера найдите устройство `ubuntu24common` и его IP-адрес.

Далее `<IP_RPI>` означает текущий адрес Raspberry Pi из роутера. Заменяйте этот шаблон своим адресом.

## 2. Подготовка SSH и обновление ОС

Команды этого раздела сначала выполняются **на компьютере**, с которого запускается Ansible.

Если этот IP раньше принадлежал другой установке ОС, удалите старую запись SSH host key:

```bash
ssh-keygen -f "$HOME/.ssh/known_hosts" -R "<IP_RPI>"
```

Если на компьютере уже есть SSH-ключ, скопируйте его на плату:

```bash
ssh-copy-id pi@<IP_RPI>
```

При запросе пароля введите `brobro`. Если нужно выбрать конкретный ключ:

```bash
ssh-copy-id -i "$HOME/.ssh/id_ed25519.pub" pi@<IP_RPI>
```

При отсутствии ключа сначала создайте его командой `ssh-keygen -t ed25519`, затем выполните `ssh-copy-id`.

Подключитесь к Raspberry Pi:

```bash
ssh pi@<IP_RPI>
```

Теперь **на Raspberry Pi** обновите систему:

```bash
sudo apt update -y && sudo apt upgrade -y
sudo reboot
```

Дождитесь возвращения платы в сеть. Если адрес изменился, найдите новый в роутере. Дальнейшие команды Ansible выполняются **на компьютере**, а не на Raspberry Pi.

## 3. Выбор профиля и настройка установки

На компьютере должны быть установлены Ansible и коллекция `community.general`, используемая ролями. Если репозиторий ещё не скачан:

```bash
git clone https://github.com/NikolayIvanovWS/ansible-vbcores.git
cd ansible-vbcores
```

Если он уже скачан, перейдите в его каталог.

### Ровер BRover-E5

В файле `hosts` задайте параметры устройства в группе `[brover]`:

```ini
[brover]
ubuntu24common ansible_host=<IP_RPI> ansible_user=pi ansible_become=true ansible_become_method=sudo ansible_become_password=brobro
```

Откройте `raspberry_brover.yml` и установите имя и версию собираемого образа:

```yaml
vars:
  common_hostname: brover01
  image_version: "broverOS_vX.X>"
```

Запустите установку:

```bash
ansible-playbook -i hosts raspberry_brover.yml
```

### Универсальный образ VBCores

В файле `hosts` задайте параметры устройства в группе `[vbcores]`:

```ini
[vbcores]
ubuntu24common ansible_host=<IP_RPI> ansible_user=pi ansible_become=true ansible_become_method=sudo ansible_become_password=brobro
```

Откройте `raspberry_vbcores.yml` и измените `image_version`, сохранив остальные переменные плейбука:

```yaml
vars:
  common_hostname: vbcores01
  image_version: "vbcoresOS_vX.X"
  # Остальные переменные профиля оставьте на месте.
```

Запустите установку:

```bash
ansible-playbook -i hosts raspberry_vbcores.yml
```

Во всех примерах используется вход по установленному SSH-ключу; пароль SSH в inventory не задаётся. Если в существующей строке есть `ansible_ssh_pass` или `ansible_password`, удалите его. Пароль `ansible_become_password` нужен для выполнения задач через sudo.

Параметр `image_version` из выбранного плейбука переопределяет значение из `group_vars/all.yml` и записывается в `/etc/os-release` как `IMAGE_VERSION`. Имя `ubuntu24common` в inventory — условное имя устройства для Ansible; после смены hostname во время установки его менять не требуется.

Плейбуки рассчитаны на чистую ОС. Во время установки Raspberry Pi несколько раз перезагрузится; Ansible сам дождётся её возвращения. После завершения проверьте, что в `PLAY RECAP` значения `failed` и `unreachable` равны нулю.

## 4. Проверка установленного образа

После основного плейбука проверьте работу всех функций устройства. Особенно важно сделать это, если перед сборкой менялись задачи Ansible, конфигурации или устанавливаемое ПО.

К финальной очистке переходите после успешной проверки. Сохраните необходимые результаты диагностики до запуска `clean`, поскольку журналы будут очищены.

## 5. Подготовка чистого образа для пользователей

В веб-интерфейсе роутера уточните текущий IP-адрес подготовленной платы и укажите его в группе `[clean]` файла `hosts`:

```ini
[clean]
image_source ansible_host=<IP_RPI> ansible_user=pi ansible_become=true ansible_become_method=sudo ansible_become_password=brobro
```

`image_source` — условное имя для Ansible, одинаково подходящее для любого профиля.

Запустите:

```bash
ansible-playbook -i hosts raspberry_clean.yml
```

Роль `clean`:

- очищает журналы, историю команд, временные файлы, кэши и APT-кэш;
- удаляет SSH-ключи пользователей `pi` и `root`, включая `authorized_keys`, а также SSH host keys платы;
- сбрасывает machine-id;
- подготавливает firstboot для генерации SSH host keys и расширения файловой системы на карте пользователя;
- обновляет и включает установленную службу настройки питания EEPROM;
- сохраняет каталог `/home/pi/ros2_ws/build`;
- планирует выключение платы с задержкой 30 секунд.

**После завершения Raspberry Pi не перезагружается, а выключается.** Дождитесь выключения, отключите питание и извлеките microSD. Не загружайте плату с этой картой до снятия образа: следующая загрузка уже запустит firstboot-службы.

При первом запуске копии образа создаются новые SSH host keys. На Raspberry Pi 5 служба питания проверяет EEPROM и при необходимости задаёт `PSU_MAX_CURRENT=5000`; для применения изменения требуется ещё одна перезагрузка. Это предназначено для сборок с HAT, обеспечивающей питание 5 А. На Raspberry Pi 4 настройка питания EEPROM не меняется.

## 6. Снятие, уменьшение и сжатие образа

Все команды выполняются **на компьютере с Ubuntu**, к которому подключена microSD после выключения Raspberry Pi.

### Подготовка PiShrink

Один раз установите PiShrink из [официального репозитория](https://github.com/Drewsif/PiShrink):

```bash
wget https://raw.githubusercontent.com/Drewsif/PiShrink/master/pishrink.sh
chmod +x pishrink.sh
sudo mv pishrink.sh /usr/local/bin/pishrink.sh
```

Создайте каталог для образов:

```bash
mkdir -p ~/OS_image
cd ~/OS_image
```

### Выбор карты и имени образа

Найдите карту по размеру и модели:

```bash
lsblk -o NAME,SIZE,MODEL,TYPE,MOUNTPOINTS
```

Отмонтируйте все смонтированные разделы этой карты, например через файловый менеджер, оставив саму карту подключённой.

Задайте устройство **всей карты**, не отдельного раздела, и имя файла без расширения. Замените `/dev/sdX` и шаблон имени своими значениями; проверьте, что выбран именно носитель Raspberry Pi.

```bash
SD_DEVICE="/dev/sdX"
IMAGE_NAME="<ИМЯ_ОБРАЗА_И_ВЕРСИЯ>"
```

Для `IMAGE_NAME` используйте то же имя и версию, которые задавались в `image_version` выбранного плейбука.

### Создание файла образа

```bash
sudo dd if="$SD_DEVICE" of="${IMAGE_NAME}.img" bs=4M status=progress conv=fsync
```

Уменьшите образ:

```bash
sudo pishrink.sh -s "${IMAGE_NAME}.img"
```

Флаг `-s` отключает добавление собственного механизма авторасширения PiShrink: в нашем образе расширение карты уже выполняется через `firstboot.service`.

Сожмите результат:

```bash
sudo gzip "${IMAGE_NAME}.img"
```

Итоговый файл — `${IMAGE_NAME}.img.gz`. Его можно передавать пользователям для записи на microSD через Raspberry Pi Imager с выбором собственного образа.
