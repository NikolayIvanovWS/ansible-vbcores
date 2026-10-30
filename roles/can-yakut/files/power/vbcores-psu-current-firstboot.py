#!/usr/bin/env python3
"""Set the Pi 5 EEPROM PSU limit once per physical board (5 A HAT only)."""

import pathlib
import re
import subprocess
import sys
import tempfile


MODEL = pathlib.Path("/proc/device-tree/model")
SERIAL = pathlib.Path("/proc/device-tree/serial-number")
STATE = pathlib.Path("/var/lib/vbcores-psu-current/checked-serial")
CONFIG_TXT_SECTION = re.compile(r"(?m)^\[config\.txt\][ \t]*$")
PSU_SETTING = re.compile(r"(?m)^PSU_MAX_CURRENT=([^\r\n]*)$")


def device_tree_string(path):
    try:
        return path.read_bytes().rstrip(b"\0").decode("ascii").strip()
    except FileNotFoundError:
        return ""


def mark_checked(serial):
    if serial:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(serial + "\n", encoding="ascii")


def main():
    model = device_tree_string(MODEL)
    serial = device_tree_string(SERIAL)

    if serial and STATE.exists() and STATE.read_text(encoding="ascii").strip() == serial:
        return 0

    if model.startswith("Raspberry Pi 4"):
        print("Raspberry Pi 4: EEPROM power setting left unchanged")
        mark_checked(serial)
        return 0

    if not model.startswith("Raspberry Pi 5"):
        print(f"Unsupported model {model!r}: EEPROM power setting left unchanged")
        return 0

    # --apply without an EEPROM image selects the newest image *from the
    # installed package*. That image can be older than this board's firmware.
    with tempfile.TemporaryDirectory(prefix="vbcores-eeprom-") as temp_dir:
        current_image = pathlib.Path(temp_dir) / "current.bin"
        config_file = pathlib.Path(temp_dir) / "boot.conf"
        subprocess.run(
            [
                "flashrom",
                "-p",
                "linux_spi:dev=/dev/spidev10.0,spispeed=16000",
                "-r",
                str(current_image),
            ],
            check=True,
        )
        config = subprocess.check_output(
            ["rpi-eeprom-config", str(current_image)], text=True
        )
        section = CONFIG_TXT_SECTION.search(config)
        boot_config = config[:section.start()] if section else config
        settings = PSU_SETTING.findall(boot_config)

        if len(settings) > 1:
            raise ValueError("Multiple PSU_MAX_CURRENT settings in bootloader configuration")

        current = settings[0].strip() if settings else None
        if current == "5000":
            print("PSU_MAX_CURRENT=5000 is already active")
            mark_checked(serial)
            return 0

        if current not in (None, "3000"):
            print(f"PSU_MAX_CURRENT={current!r}: leaving existing setting unchanged")
            mark_checked(serial)
            return 0

        if current == "3000":
            updated = PSU_SETTING.sub("PSU_MAX_CURRENT=5000", config, count=1)
        else:
            insert_at = section.start() if section else len(config)
            separator = "" if not insert_at or config[insert_at - 1] == "\n" else "\n"
            updated = config[:insert_at] + separator + "PSU_MAX_CURRENT=5000\n" + config[insert_at:]

        config_file.write_text(updated, encoding="utf-8")
        subprocess.run(
            ["rpi-eeprom-config", "--apply", str(config_file), str(current_image)],
            check=True,
        )

    print("Scheduled PSU_MAX_CURRENT=5000 EEPROM update; reboot required")
    # Do not mark completion yet: verify the EEPROM after the next reboot.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"EEPROM power setup failed: {error}", file=sys.stderr)
        sys.exit(1)
