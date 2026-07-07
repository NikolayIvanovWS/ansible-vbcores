#!/bin/bash
set -eo pipefail

source /opt/ros/jazzy/setup.bash
source /home/pi/.ros_params
source /home/pi/ros2_ws/install/local_setup.bash

WAIT_SECONDS=60
MAX_CAMERAS=2

WORK_DIR="$(mktemp -d)"
PIDS=()

cleanup() {
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT INT TERM

find_camera_devices() {
    local devices=()
    local link
    local resolved

    for link in /dev/v4l/by-id/*video-index0; do
        [ -e "$link" ] || continue
        resolved="$(readlink -f "$link")"
        [ -e "$resolved" ] || continue
        devices+=("$resolved")
    done

    if [ "${#devices[@]}" -eq 0 ]; then
        for link in /dev/v4l/by-path/*usb*video-index0; do
            [ -e "$link" ] || continue
            resolved="$(readlink -f "$link")"
            [ -e "$resolved" ] || continue
            devices+=("$resolved")
        done
    fi

    printf '%s\n' "${devices[@]}" | sort -u | head -n "$MAX_CAMERAS"
}

write_camera_params() {
    local device="$1"
    local params_file="$2"
    local camera_name="$3"

    cat > "$params_file" <<EOF
/**:
    ros__parameters:
      video_device: "$device"
      framerate: 30.0
      io_method: "mmap"
      frame_id: "camera"
      pixel_format: "mjpeg2rgb"
      av_device_format: "YUV422P"
      image_width: 640
      image_height: 480
      camera_name: "$camera_name"
      camera_info_url: "package://usb_cam/config/camera_info.yaml"
      brightness: -1
      contrast: -1
      saturation: -1
      sharpness: -1
      gain: -1
      auto_white_balance: true
      white_balance: 4000
      autoexposure: true
      exposure: 100
      autofocus: false
      focus: -1
EOF
}

start_camera() {
    local index="$1"
    local device="$2"
    local camera_name="camera${index}"
    local params_file="${WORK_DIR}/${camera_name}.yaml"

    write_camera_params "$device" "$params_file" "$camera_name"
    echo "Starting ${camera_name} on ${device}"

    ros2 run usb_cam usb_cam_node_exe \
        --ros-args \
        -r "__node:=${camera_name}" \
        --params-file "$params_file" \
        -r "image_raw:=${camera_name}/image_raw" \
        -r "image_raw/compressed:=${camera_name}/image_compressed" \
        -r "image_raw/compressedDepth:=${camera_name}/compressedDepth" \
        -r "image_raw/theora:=${camera_name}/image_raw/theora" \
        -r "camera_info:=${camera_name}/camera_info" &

    PIDS+=("$!")
}

for _ in $(seq 1 "$WAIT_SECONDS"); do
    mapfile -t VIDEO_DEVICES < <(find_camera_devices)

    if [ "${#VIDEO_DEVICES[@]}" -gt 0 ]; then
        index=1
        for device in "${VIDEO_DEVICES[@]}"; do
            start_camera "$index" "$device"
            index=$((index + 1))
        done

        wait -n "${PIDS[@]}"
        exit 1
    fi
    sleep 1
done

echo "No USB camera device was found after ${WAIT_SECONDS}s" >&2
exit 1
