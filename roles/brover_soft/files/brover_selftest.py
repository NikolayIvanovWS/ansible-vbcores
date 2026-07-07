#!/usr/bin/env python3
"""BRover-E5 acceptance self-test.

Default mode runs the full acceptance test, including HMI and motor checks.
Use --skip-motor-test only when the rover is not on a stand.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
INFO = "INFO"

ROS_SETUP = (
    "source /opt/ros/jazzy/setup.bash 2>/dev/null; "
    "source /home/pi/ros2_ws/install/setup.bash 2>/dev/null; "
    "source /home/pi/.ros_params 2>/dev/null; "
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def log(message: str) -> None:
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", file=sys.stderr, flush=True)


def log_items(items: list[dict[str, Any]]) -> None:
    for item in items:
        log(f"  [{status_ru(item['status'])}] {item['name']}: {item['message']}")


def log_step_result(label: str, items: list[dict[str, Any]], started_at: float) -> None:
    status = worst_status(items) if items else INFO
    duration = time.time() - started_at
    log(f"Готово: {label} -> {status_ru(status)} за {duration:.1f} с")
    log_items(items)


def run_step(label: str, fn: Any) -> list[dict[str, Any]]:
    started_at = time.time()
    log(f"Начинаю: {label}")
    items = fn()
    log_step_result(label, items, started_at)
    return items


def run(cmd: str, timeout: float = 10.0) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            executable="/bin/bash",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "cmd": cmd,
            "rc": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "duration_s": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "rc": 124,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": "timeout",
            "duration_s": round(time.time() - started, 3),
        }


def ros(cmd: str, timeout: float = 15.0) -> dict[str, Any]:
    return run(f"bash -lc {shlex.quote(ROS_SETUP + cmd)}", timeout=timeout)


def ros_python(code: str, timeout: float = 60.0) -> dict[str, Any]:
    encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
    cmd = f"python3 -c \"$(echo {encoded} | base64 -d)\""
    return ros(cmd, timeout=timeout)


def result(name: str, status: str, message: str, data: Any = None) -> dict[str, Any]:
    item = {"name": name, "status": status, "message": message}
    if data is not None:
        item["data"] = data
    return item


def worst_status(items: list[dict[str, Any]]) -> str:
    statuses = {item["status"] for item in items}
    if FAIL in statuses:
        return FAIL
    if WARN in statuses:
        return "PASS_WITH_WARNINGS"
    return PASS


def status_ru(status: str) -> str:
    return {
        PASS: "OK",
        WARN: "ПРЕДУПРЕЖДЕНИЕ",
        FAIL: "ОШИБКА",
        INFO: "ИНФО",
        "PASS_WITH_WARNINGS": "OK С ПРЕДУПРЕЖДЕНИЯМИ",
    }.get(status, status)


def check_group(name: str) -> str:
    if name.startswith(("hostname", "os_", "disk_", "uptime")):
        return "ОС и образ"
    if name.startswith("service:"):
        return "Сервисы"
    if name.startswith("port:"):
        return "Сеть"
    if name.startswith("can:"):
        return "CAN"
    if name.startswith(("usb_cameras", "ros_camera_topic")):
        return "Камеры"
    if name.startswith(("ros_", "topic_rate:")):
        return "ROS 2"
    if name.startswith("battery"):
        return "Питание"
    if name.startswith("hmi_"):
        return "HMI"
    if name.startswith("motor"):
        return "Моторы"
    return "Прочее"


def format_human_report(report: dict[str, Any]) -> str:
    checks = report["checks"]
    counts = {
        PASS: sum(1 for item in checks if item["status"] == PASS),
        WARN: sum(1 for item in checks if item["status"] == WARN),
        FAIL: sum(1 for item in checks if item["status"] == FAIL),
        INFO: sum(1 for item in checks if item["status"] == INFO),
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in checks:
        groups.setdefault(check_group(item["name"]), []).append(item)

    lines = [
        "BRover-E5 self-test",
        "=" * 20,
        "",
        f"Итог: {status_ru(report['overall_status'])}",
        f"Ровер: {report.get('host')}",
        f"Начало: {report['started_at']}",
        f"Конец:  {report['finished_at']}",
        "",
        "Сводка:",
        f"  OK: {counts[PASS]}",
        f"  Ошибки: {counts[FAIL]}",
        f"  Предупреждения: {counts[WARN]}",
        f"  Инфо: {counts[INFO]}",
        "",
    ]

    failures = [item for item in checks if item["status"] == FAIL]
    warnings = [item for item in checks if item["status"] == WARN]
    if failures:
        lines.append("Что нужно исправить:")
        for item in failures:
            lines.append(f"  - {item['name']}: {item['message']}")
        lines.append("")
    if warnings:
        lines.append("На что обратить внимание:")
        for item in warnings:
            lines.append(f"  - {item['name']}: {item['message']}")
        lines.append("")

    lines.append("Подробности:")
    order = ["ОС и образ", "Сервисы", "Сеть", "CAN", "Камеры", "ROS 2", "Питание", "HMI", "Моторы", "Прочее"]
    for group in order:
        items = groups.get(group)
        if not items:
            continue
        lines.append("")
        lines.append(group)
        lines.append("-" * len(group))
        for item in items:
            lines.append(f"[{status_ru(item['status'])}] {item['name']}: {item['message']}")

    lines.append("")
    lines.append("Машинный JSON-отчёт лежит рядом с этим файлом.")
    return "\n".join(lines) + "\n"


def parse_float_from_echo(text: str, field: str = "data") -> float | None:
    m = re.search(rf"^\s*{re.escape(field)}:\s*([-+]?\d+(?:\.\d+)?)", text, re.M)
    return float(m.group(1)) if m else None


def parse_battery(text: str) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for field in ("voltage", "current", "percentage"):
        m = re.search(rf"^\s*{field}:\s*([-+]?\d+(?:\.\d+)?)", text, re.M)
        out[field] = float(m.group(1)) if m else None
    return out


def check_os() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    hostname = run("hostname")
    os_release = run("cat /etc/os-release")
    df = run("df -hT / /boot/firmware 2>/dev/null")
    uptime = run("uptime")

    image_version = None
    m = re.search(r'^IMAGE_VERSION="?([^"\n]+)"?', os_release["stdout"], re.M)
    if m:
        image_version = m.group(1)

    items.append(result("hostname", PASS if hostname["rc"] == 0 else FAIL, hostname["stdout"], hostname))
    items.append(result("os_image", PASS if image_version else WARN, image_version or "IMAGE_VERSION not found", os_release))
    items.append(result("disk_space", PASS if df["rc"] == 0 else FAIL, "disk usage collected", df))
    items.append(result("uptime", PASS if uptime["rc"] == 0 else WARN, uptime["stdout"], uptime))
    return items


def check_services() -> list[dict[str, Any]]:
    services = ["ros_nodes.service", "fastdds.service", "ssh.service", "code-server@pi.service"]
    items: list[dict[str, Any]] = []
    for svc in services:
        r = run(f"systemctl is-active {shlex.quote(svc)}")
        items.append(result(f"service:{svc}", PASS if r["stdout"] == "active" else FAIL, r["stdout"] or r["stderr"], r))

    cam = run("systemctl is-active camera.service")
    items.append(result("service:camera.service", PASS if cam["stdout"] == "active" else WARN, cam["stdout"] or cam["stderr"], cam))
    return items


def check_network() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    ss = run("ss -tulpn")
    required = {
        "22": "ssh",
        "8080": "web_ui",
        "8090": "code_server",
        "9090": "rosbridge",
        "9999": "web_video_server",
    }
    for port, label in required.items():
        ok = re.search(rf":{port}\s+", ss["stdout"]) is not None
        items.append(result(f"port:{label}:{port}", PASS if ok else FAIL, "listening" if ok else "not listening"))

    return items


def check_can() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for iface, required in (("can0", True), ("can1", False)):
        samples = []
        for _ in range(3):
            samples.append(run(f"ip -details link show {iface}", timeout=5))
            time.sleep(0.5)
        last = samples[-1]
        text = "\n".join(sample["stdout"] for sample in samples)
        if last["rc"] != 0:
            items.append(result(f"can:{iface}", FAIL if required else WARN, "interface not found", samples))
            continue
        states = re.findall(r"can <[^>]*>\s+state\s+([A-Z-]+)", text)
        state = states[-1] if states else "UNKNOWN"
        fd_ok = "FD" in text
        bitrate_ok = "bitrate 1000000" in text and "dbitrate 8000000" in text
        counters = [(int(tx), int(rx)) for tx, rx in re.findall(r"berr-counter tx (\d+) rx (\d+)", text)]
        tx = counters[-1][0] if counters else None
        rx = counters[-1][1] if counters else None
        any_error_counter = any((txv > 0 or rxv > 0) for txv, rxv in counters)
        any_bad_state = any(s != "ERROR-ACTIVE" for s in states)

        if not fd_ok or not bitrate_ok:
            status = FAIL if required else WARN
            msg = f"{state}, wrong CAN FD bitrate settings"
        elif any(s in ("BUS-OFF", "STOPPED") for s in states):
            status = FAIL if required else WARN
            msg = f"{state}, tx={tx}, rx={rx}, states={states}"
        elif any_bad_state or any_error_counter:
            status = WARN
            msg = f"{state}, tx={tx}, rx={rx}, states={states}"
        else:
            status = PASS
            msg = f"{state}, tx={tx}, rx={rx}"
        items.append(result(f"can:{iface}", status, msg, samples))
    return items


def check_usb_cameras(expected: str) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    v4l = run("command -v v4l2-ctl >/dev/null && v4l2-ctl --list-devices || true")
    camera_count = 0
    for line in v4l["stdout"].splitlines():
        stripped = line.strip()
        is_device_header = line and not line[0].isspace() and stripped.endswith(":")
        if is_device_header and re.search(r"camera", stripped, re.I):
            camera_count += 1

    # Fallback: count video devices that expose capture capability.
    if camera_count == 0:
        devs = run("ls /dev/video* 2>/dev/null | sort -V")
        camera_count = len(re.findall(r"/dev/video\d+", devs["stdout"]))

    status = PASS
    msg = f"detected {camera_count} camera device(s)"
    if expected != "auto" and camera_count != int(expected):
        status = FAIL
        msg += f", expected {expected}"
    elif camera_count == 0:
        status = INFO
        msg += ", allowed"

    items.append(result("usb_cameras", status, msg, v4l))
    return items, camera_count


def check_ros(camera_count: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    nodes_r = ros("ros2 node list --spin-time 3", timeout=20)
    nodes = set(nodes_r["stdout"].splitlines())

    required_nodes = {
        "/bat_monitor",
        "/control_move",
        "/cyphal_bridge",
        "/imu",
        "/joy",
        "/odom",
        "/radiolink_control",
        "/rosbridge_server",
        "/web_video_server",
    }
    missing = sorted(required_nodes - nodes)
    items.append(result("ros_nodes", FAIL if missing else PASS, f"missing: {missing}" if missing else "all required nodes present", nodes_r))

    topics_r = ros("ros2 topic list -t", timeout=20)
    topics = topics_r["stdout"]
    required_topics = [
        "/bat ",
        "/bhi360/imu ",
        "/cmd_vel ",
        "/joy ",
        "/m_odom1 ",
        "/m_odom2 ",
        "/m_odom3 ",
        "/m_odom4 ",
        "/m_odom5 ",
        "/m_odom6 ",
        "/m_vel1 ",
        "/m_vel2 ",
        "/m_vel3 ",
        "/m_vel4 ",
        "/m_vel5 ",
        "/m_vel6 ",
        "/odom_pose2d ",
        "/user_button ",
    ]
    missing_topics = [t.strip() for t in required_topics if t not in topics]
    items.append(result("ros_topics", FAIL if missing_topics else PASS, f"missing: {missing_topics}" if missing_topics else "all required topics present", topics_r))

    for i in range(1, camera_count + 1):
        topic = f"/camera{i}/image_raw "
        ok = topic in topics
        items.append(result(f"ros_camera_topic:{i}", PASS if ok else FAIL, "present" if ok else "missing"))

    services_r = ros("ros2 service list -t", timeout=20)
    services = services_r["stdout"]
    for svc in ("/hmi/led ", "/hmi/beep ", "/odom/reset "):
        ok = svc in services
        items.append(result(f"ros_service:{svc.strip()}", PASS if ok else FAIL, "present" if ok else "missing"))

    return items


def check_topic_rates() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    checks = [
        ("/bat", 5.0, 80.0),
        ("/bhi360/imu", 50.0, 1000.0),
        ("/odom_pose2d", 5.0, 120.0),
    ]
    for topic, min_hz, max_hz in checks:
        r = ros(f"timeout 7 ros2 topic hz {shlex.quote(topic)}", timeout=9)
        rates = [float(x) for x in re.findall(r"average rate:\s+([0-9.]+)", r["stdout"])]
        hz = rates[-1] if rates else None
        ok = hz is not None and min_hz <= hz <= max_hz
        items.append(result(f"topic_rate:{topic}", PASS if ok else FAIL, f"{hz} Hz" if hz else "no messages", r))
    return items


def check_battery() -> list[dict[str, Any]]:
    r = ros("timeout 5 ros2 topic echo --once /bat", timeout=7)
    data = parse_battery(r["stdout"])
    voltage = data.get("voltage")
    current = data.get("current")
    if voltage is None:
        return [result("battery", FAIL, "no /bat voltage", r)]

    if 13.0 <= voltage <= 18.0:
        status = PASS
    elif 12.0 <= voltage < 13.0 or 18.0 < voltage <= 19.0:
        status = WARN
    else:
        status = FAIL

    if voltage < 15.7:
        source = "external_15v_or_low_battery"
    elif voltage <= 17.2:
        source = "battery_or_charged_external"
    else:
        source = "unknown_high_voltage"

    msg = f"voltage={voltage:.2f}V current={current} source_guess={source}"
    return [result("battery", status, msg, {"echo": r, "parsed": data, "source_guess": source})]


def call_hmi() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    calls = [
        ("hmi_led_power", "ros2 service call /hmi/led cyphal_ros2_bridge/srv/CallHMILed \"{'led': {'r':0, 'g':80, 'b':0, 'interface':0}}\""),
        ("hmi_led_user", "ros2 service call /hmi/led cyphal_ros2_bridge/srv/CallHMILed \"{'led': {'r':80, 'g':0, 'b':0, 'interface':1}}\""),
        ("hmi_beep", "ros2 service call /hmi/beep cyphal_ros2_bridge/srv/CallHMIBeeper \"{'beeper': {'duration':0.2, 'frequency':1.0}}\""),
    ]
    for name, cmd in calls:
        r = ros(f"timeout 5 {cmd}", timeout=7)
        ok = r["rc"] == 0 and ("success" in r["stdout"].lower() or "response" in r["stdout"].lower())
        items.append(result(name, PASS if ok else WARN, "called" if ok else "call failed or no response", r))
    return items


def stop_motors() -> None:
    stop_cmd_vel()


def stop_cmd_vel() -> None:
    ros(
        "ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist "
        "\"{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}\"",
        timeout=4,
    )


def publish_all_motor_zero() -> None:
    code = r"""
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32

rclpy.init()
node = Node("brover_selftest_zero")
pubs = [node.create_publisher(Float32, f"/m_vel{i}", 10) for i in range(1, 7)]
msg = Float32()
msg.data = 0.0
end = time.monotonic() + 0.6
while time.monotonic() < end:
    for pub in pubs:
        pub.publish(msg)
    rclpy.spin_once(node, timeout_sec=0.02)
    time.sleep(0.05)
node.destroy_node()
rclpy.shutdown()
"""
    ros_python(code, timeout=5)


def read_float_topic(topic: str, timeout_s: float = 5.0) -> tuple[float | None, dict[str, Any]]:
    r = ros(f"timeout {timeout_s:g} ros2 topic echo --once {shlex.quote(topic)}", timeout=timeout_s + 2)
    return parse_float_from_echo(r["stdout"]), r


def parse_pose2d(text: str) -> dict[str, float | None]:
    pose: dict[str, float | None] = {}
    for field in ("x", "y", "theta"):
        m = re.search(rf"^\s*{field}:\s*([-+]?\d+(?:\.\d+)?)", text, re.M)
        pose[field] = float(m.group(1)) if m else None
    return pose


def read_pose2d(timeout_s: float = 5.0) -> tuple[dict[str, float | None], dict[str, Any]]:
    r = ros(f"timeout {timeout_s:g} ros2 topic echo --once /odom_pose2d", timeout=timeout_s + 2)
    return parse_pose2d(r["stdout"]), r


def find_control_move_pids() -> list[int]:
    r = run("ps -eo pid=,args=", timeout=5)
    pids = []
    for line in r["stdout"].splitlines():
        if "/home/pi/ros2_ws/install/brover_move_control/lib/brover_move_control/move_node" not in line:
            continue
        parts = line.strip().split(maxsplit=1)
        if not parts:
            continue
        try:
            pids.append(int(parts[0]))
        except ValueError:
            continue
    return pids


def stop_control_move() -> dict[str, Any]:
    before = find_control_move_pids()
    if before:
        for pid in before:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        time.sleep(1.0)
        still_running = find_control_move_pids()
        for pid in still_running:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(0.5)
    after = find_control_move_pids()
    return {"before": before, "after": after}


def start_control_move() -> dict[str, Any]:
    before = find_control_move_pids()
    if not before:
        with open(os.devnull, "wb") as devnull:
            subprocess.Popen(
                [
                    "bash",
                    "-lc",
                    ROS_SETUP + "exec ros2 run brover_move_control move_node --ros-args -r __node:=control_move",
                ],
                stdout=devnull,
                stderr=devnull,
                start_new_session=True,
            )
        time.sleep(2.0)
    after = find_control_move_pids()
    return {"before": before, "after": after}


def motor_test(min_speed: float, max_speed: float, ramp_step: float) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def cleanup(signum: int | None = None, frame: Any = None) -> None:
        log("Моторы: аварийная остановка, отправляю нулевые скорости")
        stop_motors()
        if signum is not None:
            raise SystemExit(2)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        log("Моторы: отправляю нулевой /cmd_vel")
        stop_cmd_vel()
        log("Моторы: обнуляю команды всех колес")
        publish_all_motor_zero()
        log("Моторы: временно останавливаю control_move для индивидуальной проверки колес")
        control_state = stop_control_move()
        if control_state["after"]:
            items.append(result("motor_control_move_stop", FAIL, f"control_move still running: {control_state['after']}", control_state))
            return items

        log("Моторы: сбрасываю одометрию")
        reset = ros("timeout 5 ros2 service call /odom/reset std_srvs/srv/Empty", timeout=7)
        log(
            "Моторы: запускаю ramp-тест колес "
            f"(min={min_speed:g}, max={max_speed:g}, step={ramp_step:g}; может занять до 2 минут)"
        )
        code = f"""
import json
import math
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32
from geometry_msgs.msg import Pose2D

MIN_SPEED = {min_speed!r}
MAX_SPEED = {max_speed!r}
RAMP_STEP = {ramp_step!r}
PUBLISH_DT = 0.10
SETTLE_DT = 0.25

class MotorRamp(Node):
    def __init__(self):
        super().__init__("brover_selftest_motor_ramp")
        self.pubs = [self.create_publisher(Float32, f"/m_vel{{i}}", 10) for i in range(1, 7)]
        self.odom = [None] * 6
        self.pose = None
        for i in range(6):
            self.create_subscription(Float32, f"/m_odom{{i + 1}}", lambda msg, idx=i: self._odom_cb(idx, msg), 10)
        self.create_subscription(Pose2D, "/odom_pose2d", self._pose_cb, 10)

    def _odom_cb(self, idx, msg):
        self.odom[idx] = float(msg.data)

    def _pose_cb(self, msg):
        self.pose = {{"x": float(msg.x), "y": float(msg.y), "theta": float(msg.theta)}}

    def spin_for(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.02)

    def publish_wheel(self, wheel, value):
        for idx, pub in enumerate(self.pubs, start=1):
            msg = Float32()
            msg.data = float(value if idx == wheel else 0.0)
            pub.publish(msg)
        rclpy.spin_once(self, timeout_sec=0.02)

    def zero_all(self, seconds=0.5):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for pub in self.pubs:
                msg = Float32()
                msg.data = 0.0
                pub.publish(msg)
            rclpy.spin_once(self, timeout_sec=0.02)
            time.sleep(0.05)

def frange(start, stop, step):
    values = []
    x = start
    while x <= stop + 1e-9:
        values.append(round(x, 4))
        x += step
    if values[-1] != stop:
        values.append(stop)
    return values

rclpy.init()
node = MotorRamp()
node.spin_for(1.0)
pose_before = node.pose
up = frange(MIN_SPEED, MAX_SPEED, RAMP_STEP)
down = list(reversed(up[:-1]))
profile = up + down + [0.0]
results = []

for wheel in range(1, 7):
    direction = 1.0 if wheel <= 3 else -1.0
    node.zero_all(0.4)
    before = node.odom[wheel - 1]
    max_abs = 0.0
    max_signed = None
    samples = []
    for speed in profile:
        value = direction * speed
        node.publish_wheel(wheel, value)
        node.spin_for(PUBLISH_DT)
        current = node.odom[wheel - 1]
        samples.append(current)
        if current is not None and abs(current) >= max_abs:
            max_abs = abs(current)
            max_signed = current
        time.sleep(0.01)
    node.zero_all(SETTLE_DT)
    node.spin_for(0.2)
    after = node.odom[wheel - 1]
    sign_ok = max_signed is not None and max_signed * direction > 0
    reached_min = max_abs >= max(0.05, MIN_SPEED * 0.5)
    reached_high = max_abs >= max(MIN_SPEED, MAX_SPEED * 0.45)
    stopped = after is not None and abs(after) < 0.20
    results.append({{
        "wheel": wheel,
        "direction": direction,
        "before": before,
        "max_abs": max_abs,
        "max_signed": max_signed,
        "after_stop": after,
        "sign_ok": sign_ok,
        "reached_min": reached_min,
        "reached_high": reached_high,
        "stopped": stopped,
        "sample_count": len(samples),
    }})

node.zero_all(0.8)
node.spin_for(0.5)
pose_after = node.pose
node.destroy_node()
rclpy.shutdown()
print(json.dumps({{"profile": profile, "pose_before": pose_before, "pose_after": pose_after, "wheels": results}}, ensure_ascii=False))
"""
        ramp = ros_python(code, timeout=120)
        log("Моторы: ramp-тест завершен, разбираю результаты")
        try:
            data = json.loads(ramp["stdout"].splitlines()[-1])
        except Exception as exc:
            items.append(result("motor_ramp_runner", FAIL, f"failed to parse ramp output: {exc}", ramp))
            return items

        items.append(result("motor_control_move_stop", PASS, "control_move stopped for individual wheel test", control_state))
        for wheel_data in data["wheels"]:
            ok = (
                wheel_data["sign_ok"]
                and wheel_data["reached_min"]
                and wheel_data["reached_high"]
                and wheel_data["stopped"]
            )
            items.append(
                result(
                    f"motor:{wheel_data['wheel']}",
                    PASS if ok else FAIL,
                    (
                        f"max={wheel_data['max_signed']}, after_stop={wheel_data['after_stop']}, "
                        f"direction={wheel_data['direction']:+.0f}"
                    ),
                    wheel_data,
                )
            )

        pose_before = data.get("pose_before") or {}
        pose_after = data.get("pose_after") or {}
        x0 = pose_before.get("x")
        x2 = pose_after.get("x")
        dx = (x2 - x0) if x0 is not None and x2 is not None else None
        odom_ok = dx is not None and abs(dx) > 0.01
        items.append(
            result(
                "motor_odometry_link",
                PASS if odom_ok else FAIL,
                f"x before={x0}, after={x2}, dx={dx}",
                {"reset": reset, "ramp": ramp, "pose_before": pose_before, "pose_after": pose_after},
            )
        )
    finally:
        log("Моторы: финальное обнуление команд")
        publish_all_motor_zero()
        log("Моторы: восстанавливаю control_move")
        start_state = start_control_move()
        items.append(
            result(
                "motor_control_move_restore",
                PASS if start_state["after"] else FAIL,
                f"control_move pids after restore: {start_state['after']}",
                start_state,
            )
        )
        stop_cmd_vel()
        log("Моторы: /cmd_vel снова в нуле")

    return items


def write_reports(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    hostname = report.get("host", "brover")
    json_path = out_dir / f"selftest-{hostname}-{stamp}.json"
    txt_path = out_dir / f"selftest-{hostname}-{stamp}.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(format_human_report(report), encoding="utf-8")
    return json_path, txt_path


def main() -> int:
    parser = argparse.ArgumentParser(description="BRover-E5 acceptance self-test")
    parser.add_argument("--expected-cameras", choices=["auto", "0", "1", "2"], default="auto")
    parser.add_argument("--motor-test", action="store_true", default=True, help="run motor test; enabled by default")
    parser.add_argument("--skip-motor-test", dest="motor_test", action="store_false", help="skip motor test")
    parser.add_argument("--motor-min-speed", type=float, default=1.0)
    parser.add_argument("--motor-max-speed", type=float, default=9.6)
    parser.add_argument("--motor-ramp-step", type=float, default=0.8)
    parser.add_argument("--hmi-test", action="store_true", default=True, help="run HMI LED/beep test; enabled by default")
    parser.add_argument("--skip-hmi-test", dest="hmi_test", action="store_false", help="skip HMI LED/beep test")
    parser.add_argument("--out-dir", default="/home/pi/brover_selftest_reports")
    args = parser.parse_args()

    started = now_iso()
    host = run("hostname")["stdout"] or "unknown"
    checks: list[dict[str, Any]] = []

    log("BRover-E5 self-test started")
    log(f"Хост: {host}")
    log(f"Отчеты будут сохранены в: {args.out_dir}")

    checks.extend(run_step("ОС и образ", check_os))
    checks.extend(run_step("Сервисы", check_services))
    checks.extend(run_step("Сеть", check_network))
    checks.extend(run_step("CAN", check_can))

    cam_started_at = time.time()
    log(f"Начинаю: Камеры USB (expected={args.expected_cameras})")
    cam_items, camera_count = check_usb_cameras(args.expected_cameras)
    log_step_result("Камеры USB", cam_items, cam_started_at)
    checks.extend(cam_items)
    checks.extend(run_step(f"ROS 2 граф и топики камер (camera_count={camera_count})", lambda: check_ros(camera_count)))
    checks.extend(run_step("Частоты ROS 2 топиков", check_topic_rates))
    checks.extend(run_step("Питание", check_battery))

    if args.hmi_test:
        checks.extend(run_step("HMI LED/beep", call_hmi))
    else:
        item = result("hmi_test", INFO, "skipped by --skip-hmi-test")
        checks.append(item)
        log_items([item])

    if args.motor_test:
        checks.extend(
            run_step(
                "Моторы",
                lambda: motor_test(args.motor_min_speed, args.motor_max_speed, args.motor_ramp_step),
            )
        )
    else:
        item = result("motor_test", INFO, "skipped by --skip-motor-test")
        checks.append(item)
        log_items([item])

    report = {
        "tool": "brover_selftest",
        "version": "0.1.0",
        "host": host,
        "started_at": started,
        "finished_at": now_iso(),
        "overall_status": worst_status(checks),
        "checks": checks,
    }
    json_path, txt_path = write_reports(report, Path(args.out_dir))

    log(f"Self-test finished: {status_ru(report['overall_status'])}")
    log(f"JSON report: {json_path}")
    log(f"Text report: {txt_path}")

    print(f"overall_status: {report['overall_status']}")
    print(f"json_report: {json_path}")
    print(f"text_report: {txt_path}")
    print("")
    for item in checks:
        if item["status"] in (FAIL, WARN):
            print(f"[{status_ru(item['status'])}] {item['name']}: {item['message']}")

    return 1 if report["overall_status"] == FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
