#!/usr/bin/env bash

MAX_CAMERAS=2
SCAN_INTERVAL=1
RESTART_DELAY=5
RECONNECT_GRACE=10

source /opt/ros/jazzy/setup.bash
source /home/pi/.ros_params
source /home/pi/ros2_ws/install/local_setup.bash
set -uo pipefail

declare -A CURRENT_DEVICES=()
declare -a SLOT_LINK SLOT_DEVICE SLOT_PID SLOT_MISSING_AT SLOT_RESTART_AT

log() {
    printf '%s [camera-supervisor] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

now() {
    date +%s
}

discover_cameras() {
    local link device
    CURRENT_DEVICES=()

    shopt -s nullglob
    for link in /dev/v4l/by-path/*usb-*-video-index0; do
        device="$(readlink -f "$link" 2>/dev/null || true)"
        [[ -c "$device" ]] && CURRENT_DEVICES["$link"]="$device"
    done

    if ((${#CURRENT_DEVICES[@]} == 0)); then
        for link in /dev/v4l/by-id/*-video-index0; do
            device="$(readlink -f "$link" 2>/dev/null || true)"
            [[ -c "$device" ]] && CURRENT_DEVICES["$link"]="$device"
        done
    fi
    shopt -u nullglob
}

slot_for_link() {
    local link="$1" slot
    for ((slot = 1; slot <= MAX_CAMERAS; slot++)); do
        [[ "${SLOT_LINK[$slot]:-}" == "$link" ]] && printf '%s\n' "$slot" && return 0
    done
    return 1
}

free_slot() {
    local slot
    for ((slot = 1; slot <= MAX_CAMERAS; slot++)); do
        [[ -z "${SLOT_LINK[$slot]:-}" ]] && printf '%s\n' "$slot" && return 0
    done
    return 1
}

stop_camera() {
    local slot="$1" pid="${SLOT_PID[$1]:-}"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        log "Остановка camera${slot}, PID ${pid}"
        kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
        for _ in {1..20}; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.1
        done
        kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
    [[ -n "$pid" ]] && wait "$pid" 2>/dev/null || true
    SLOT_PID[$slot]=""
}

start_camera() {
    local slot="$1" link="${SLOT_LINK[$1]}" device="${SLOT_DEVICE[$1]}"
    local stamp
    stamp="$(now)"

    if [[ ! -c "$device" ]]; then
        log "camera${slot}: устройство ${device} недоступно"
        SLOT_RESTART_AT[$slot]=$((stamp + RESTART_DELAY))
        return
    fi

    log "Запуск camera${slot}: ${link} -> ${device}"
    setsid /opt/ros/jazzy/lib/usb_cam/usb_cam_node_exe --ros-args \
        -r __node:="camera${slot}" \
        -r image_raw:="/camera${slot}/image_raw" \
        -r camera_info:="/camera${slot}/camera_info" \
        -p video_device:="$device" \
        -p image_width:=640 \
        -p image_height:=480 \
        -p framerate:=30.0 \
        -p pixel_format:="mjpeg2rgb" &
    SLOT_PID[$slot]=$!
    SLOT_RESTART_AT[$slot]=0
}

reap_camera() {
    local slot="$1" pid="${SLOT_PID[$1]:-}" exit_code stamp
    [[ -z "$pid" ]] && return
    kill -0 "$pid" 2>/dev/null && return

    wait "$pid" 2>/dev/null
    exit_code=$?
    stamp="$(now)"
    log "camera${slot}: процесс PID ${pid} завершился с кодом ${exit_code}; повторный запуск через ${RESTART_DELAY} с"
    SLOT_PID[$slot]=""
    SLOT_RESTART_AT[$slot]=$((stamp + RESTART_DELAY))
}

refresh_assigned_slots() {
    local stamp slot link new_device
    stamp="$(now)"

    for ((slot = 1; slot <= MAX_CAMERAS; slot++)); do
        link="${SLOT_LINK[$slot]:-}"
        [[ -z "$link" ]] && continue

        if [[ -n "${CURRENT_DEVICES[$link]:-}" ]]; then
            new_device="${CURRENT_DEVICES[$link]}"
            SLOT_MISSING_AT[$slot]=0
            if [[ "${SLOT_DEVICE[$slot]:-}" != "$new_device" ]]; then
                log "camera${slot}: номер устройства изменился ${SLOT_DEVICE[$slot]:-нет} -> ${new_device}"
                stop_camera "$slot"
                SLOT_DEVICE[$slot]="$new_device"
                SLOT_RESTART_AT[$slot]=0
            fi
            continue
        fi

        if ((${SLOT_MISSING_AT[$slot]:-0} == 0)); then
            log "camera${slot}: камера отключена, ожидаю переподключение ${RECONNECT_GRACE} с"
            SLOT_MISSING_AT[$slot]="$stamp"
            stop_camera "$slot"
        elif ((stamp - SLOT_MISSING_AT[$slot] >= RECONNECT_GRACE)); then
            log "camera${slot}: время ожидания истекло, слот освобождён"
            SLOT_LINK[$slot]=""
            SLOT_DEVICE[$slot]=""
            SLOT_MISSING_AT[$slot]=0
            SLOT_RESTART_AT[$slot]=0
        fi
    done
}

assign_new_devices() {
    local link slot
    while IFS= read -r link; do
        [[ -z "$link" ]] && continue
        slot_for_link "$link" >/dev/null && continue
        slot="$(free_slot || true)"
        if [[ -z "$slot" ]]; then
            log "Найдена лишняя камера, доступно только ${MAX_CAMERAS} слота: ${link}"
            continue
        fi
        SLOT_LINK[$slot]="$link"
        SLOT_DEVICE[$slot]="${CURRENT_DEVICES[$link]}"
        SLOT_PID[$slot]=""
        SLOT_MISSING_AT[$slot]=0
        SLOT_RESTART_AT[$slot]=0
        log "Назначен слот camera${slot}: ${link}"
    done < <(printf '%s\n' "${!CURRENT_DEVICES[@]}" | sort)
}

run_cameras() {
    local stamp slot
    stamp="$(now)"
    for ((slot = 1; slot <= MAX_CAMERAS; slot++)); do
        [[ -z "${SLOT_LINK[$slot]:-}" ]] && continue
        [[ -n "${CURRENT_DEVICES[${SLOT_LINK[$slot]}]:-}" ]] || continue
        reap_camera "$slot"
        if [[ -z "${SLOT_PID[$slot]:-}" ]] && ((stamp >= ${SLOT_RESTART_AT[$slot]:-0})); then
            start_camera "$slot"
        fi
    done
}

cleanup() {
    local slot
    trap - EXIT INT TERM
    log "Завершение супервизора камер"
    for ((slot = 1; slot <= MAX_CAMERAS; slot++)); do
        stop_camera "$slot"
    done
    exit 0
}

trap cleanup EXIT INT TERM
log "Супервизор запущен: максимум ${MAX_CAMERAS} камеры"

while true; do
    discover_cameras
    refresh_assigned_slots
    assign_new_devices
    run_cameras
    sleep "$SCAN_INTERVAL"
done
