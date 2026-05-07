#!/bin/bash
set -a  # экспортируем все переменные

source /opt/ros/jazzy/setup.bash
source /home/pi/.ros_params
source /home/pi/ros2_ws/install/local_setup.bash

set +a

# Запускаем ноды

ros2 launch usb_cam camera.launch.py &
ros2 launch brover_control brover_control_launch.xml &
ros2 launch brover_web web_server.xml &

ros2 service call /odom/reset std_srvs/srv/Empty &
ros2 service call /hmi/led cyphal_ros2_bridge/srv/CallHMILed "{'led': {'r':0, 'g':255, 'b':0, 'interface':0}}" &
ros2 service call /hmi/led cyphal_ros2_bridge/srv/CallHMILed "{'led': {'r':255, 'g':0, 'b':0, 'interface':1}}" &
ros2 service call /hmi/beep cyphal_ros2_bridge/srv/CallHMIBeeper "{'beeper': {'duration':1, 'frequency':1.5}}" &
# Диагностика окружения
printenv | grep ROS > /tmp/ros_env_check.txt

wait