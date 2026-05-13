#!/bin/bash
set -eo pipefail

source /opt/ros/jazzy/setup.bash
source /home/pi/.ros_params
source /home/pi/ros2_ws/install/local_setup.bash

VIDEO_DEVICE="/dev/video0"
WAIT_SECONDS=60

for _ in $(seq 1 "$WAIT_SECONDS"); do
    if [ -e "$VIDEO_DEVICE" ]; then
        exec ros2 launch usb_cam camera.launch.py
    fi
    sleep 1
done

echo "Camera device $VIDEO_DEVICE was not found after ${WAIT_SECONDS}s" >&2
exit 1
