# Универсальный бортовой компьютер VBCores

Комплект: Raspberry Pi 5 + VBCores CAN FD Raspberry Pi HAT + Quick Connect.
Hostname: ros2vbcores. ROS 2 Jazzy, Fast DDS, code-server (:8090).

CAN0 и CAN1 поднимаются canhat.service с номинальной скоростью 1 Мбит/с
и скоростью данных 8 Мбит/с. Yakut по умолчанию использует CAN0, node ID 101.

```bash
ip -details link show can0
ip -details link show can1
yakut monitor
UAVCAN__CAN__IFACE=socketcan:can1 yakut monitor
```

Мост установлен и собран, но автоматически не запускается.
/home/pi/ros2_ws/config/can0.json — заготовка с node ID 102 и пустым списком
connections, а не конфигурация готового оборудования. Добавьте сообщения,
порты и ROS-топики своего устройства. Node ID участников одной CAN-шины
должны различаться. Для CAN1 создайте отдельную копию конфигурации.
Документация моста: /home/pi/ros2_ws/src/cyphal_ros2_bridge/README.md.

Ручной запуск после настройки:

```bash
source /opt/ros/jazzy/setup.bash
source /home/pi/.ros_params
source /home/pi/ros2_ws/install/local_setup.bash
ros2 run cyphal_ros2_bridge cyphal_bridge --ros-args -p config_file:=/home/pi/ros2_ws/config/can0.json
```

rosbridge установлен без автозапуска. Пример ручного запуска:

```bash
ros2 launch rosbridge_server rosbridge_websocket_launch.xml
```

Окружение совместимо с ROS/Cyphal-средой BRover-E5; программы шасси,
готовый веб-интерфейс ровера и автозапуск камер не установлены.
Образ не имитирует отсутствующую электронику.
