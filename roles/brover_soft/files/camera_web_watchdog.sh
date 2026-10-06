#!/usr/bin/env bash
set -uo pipefail

VIDEO_EXE=/opt/ros/jazzy/lib/web_video_server/web_video_server
CAMERA_EXE=/opt/ros/jazzy/lib/usb_cam/usb_cam_node_exe
STATE_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/camera-web-watchdog"
mkdir -p "$STATE_DIR" || exit 1
exec 9>"$STATE_DIR/lock"
flock -n 9 || exit 0

log() { logger -t camera-web-watchdog -- "$*"; }

process_identity() {
    local pid="$1"
    [[ -r "/proc/$pid/stat" ]] || return 1
    awk '{print $22}' "/proc/$pid/stat"
}

same_process() {
    [[ "$(process_identity "$1" 2>/dev/null)" == "$2" ]] &&
        [[ "$(readlink -f "/proc/$1/exe" 2>/dev/null)" == "$VIDEO_EXE" ]]
}

active_cameras() {
    local camera
    for camera in camera1 camera2; do
        pgrep -f "^${CAMERA_EXE} .*__node:=${camera}([[:space:]]|$)" >/dev/null &&
            printf '%s\n' "$camera"
    done
}

snapshot_ok() {
    local camera="$1" output code bytes first last
    output="$(mktemp "$STATE_DIR/snapshot.XXXXXX")" || return 1
    code="$(curl -sS --connect-timeout 1 --max-time 3 -o "$output" -w '%{http_code}' \
        "http://127.0.0.1:9999/snapshot?topic=/${camera}/image_raw&type=jpeg" 2>/dev/null || true)"
    bytes="$(stat -c %s "$output" 2>/dev/null || printf 0)"
    first="$(od -An -tx1 -N2 "$output" | tr -d ' \n')"
    last="$(tail -c 2 "$output" | od -An -tx1 | tr -d ' \n')"
    rm -f -- "$output"
    [[ "$code" == 200 && "$first" == ffd8 && "$last" == ffd9 ]] && ((bytes > 1000))
}

mapfile -t cameras < <(active_cameras)
((${#cameras[@]})) || exit 0
failed=()
for camera in "${cameras[@]}"; do
    snapshot_ok "$camera" || failed+=("$camera")
done
((${#failed[@]})) || exit 0

sleep 1
confirmed=()
for camera in "${failed[@]}"; do
    # Камера могла быть физически отключена во время проверки.
    pgrep -f "^${CAMERA_EXE} .*__node:=${camera}([[:space:]]|$)" >/dev/null || continue
    snapshot_ok "$camera" || confirmed+=("$camera")
done
((${#confirmed[@]})) || exit 0

# Отказ одной камеры при работающем HTTP-сервере не доказывает зависание сервера.
if curl -fsS --connect-timeout 1 --max-time 2 http://127.0.0.1:9999/ -o /dev/null; then
    log "Нет снимков от ${confirmed[*]}, HTTP-сервер отвечает; перезапуск не выполняется"
    exit 0
fi

stamp="$(date +%s)"
last_restart=0
[[ -r "$STATE_DIR/last_restart" ]] && read -r last_restart < "$STATE_DIR/last_restart"
[[ "$last_restart" =~ ^[0-9]+$ ]] || last_restart=0
if ((stamp - last_restart < 120)); then
    log "Видеосервер недоступен; повторное восстановление отложено до окончания паузы 120 с"
    exit 0
fi
printf '%s\n' "$stamp" > "$STATE_DIR/last_restart"

mapfile -t pids < <(pgrep -f "^${VIDEO_EXE}([[:space:]]|$)")
for pid in "${pids[@]}"; do
    identity="$(process_identity "$pid")" || continue
    same_process "$pid" "$identity" || continue
    log "Видеосервер PID $pid недоступен; SIGTERM"
    kill -TERM "$pid" 2>/dev/null || true
    for _ in {1..10}; do
        same_process "$pid" "$identity" || break
        sleep 0.5
    done
    if same_process "$pid" "$identity"; then
        log "Видеосервер PID $pid не завершился за 5 с; SIGKILL"
        kill -KILL "$pid" 2>/dev/null || true
    fi
done

# Launch повторно запускает видеосервер с respawn_delay=5.
for _ in {1..15}; do
    sleep 1
    recovered=true
    mapfile -t cameras < <(active_cameras)
    ((${#cameras[@]})) || exit 0
    for camera in "${cameras[@]}"; do
        snapshot_ok "$camera" || recovered=false
    done
    if "$recovered"; then
        log "Видео восстановлено для ${cameras[*]}"
        exit 0
    fi
done
log "Восстановление видео не подтверждено; необходима диагностика"
exit 1
