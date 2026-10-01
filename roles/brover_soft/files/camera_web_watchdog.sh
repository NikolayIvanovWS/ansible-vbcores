#!/usr/bin/env bash

source /opt/ros/jazzy/setup.bash
source /home/pi/.ros_params
source /home/pi/ros2_ws/install/local_setup.bash
set -uo pipefail

active_topics=0
failures=()

for camera in camera1 camera2; do
    topic="/${camera}/image_raw"
    timeout 3 ros2 topic info "$topic" >/dev/null 2>&1 || continue
    active_topics=$((active_topics + 1))

    for attempt in 1 2 3; do
        output="$(mktemp /tmp/camera-web-watchdog.XXXXXX.jpg)"
        http_code="$(curl -sS --max-time 5 -o "$output" -w '%{http_code}' \
            "http://127.0.0.1:9999/snapshot?topic=${topic}&type=jpeg" 2>/dev/null || true)"
        bytes="$(stat -c %s "$output" 2>/dev/null || printf '0')"
        rm -f -- "$output"

        if [[ "$http_code" == "200" ]] && ((bytes > 1000)); then
            exit 0
        fi
        ((attempt < 3)) && sleep 2
    done

    failures+=("${topic}:HTTP=${http_code:-нет},bytes=${bytes}")
done

if ((active_topics > 0)); then
    logger -t camera-web-watchdog \
        "web_video_server не отвечает ни для одного активного топика (${failures[*]}); перезапуск процесса"
    pkill -TERM -f '^/opt/ros/jazzy/lib/web_video_server/web_video_server([[:space:]]|$)' || true
fi

# Нет активных топиков или выполнено восстановление: ошибка systemd не требуется.
exit 0
