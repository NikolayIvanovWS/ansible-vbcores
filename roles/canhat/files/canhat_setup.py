import subprocess
import psutil

from systemd import journal

from config import config


def setup_can() -> bool:
    journal.send("Setting up CAN")

    CAN_CONFIG = config["CAN"]
    CAN_TYPE = CAN_CONFIG["type"]
    CAN_BITRATE = CAN_CONFIG.get("bitrate", "1000000")
    CAN_DBITRATE = CAN_CONFIG.get("dbitrate", "8000000")

    if CAN_TYPE == "fd":
        CAN_COMMAND = "ip link set {iface} up txqueuelen 65535 type can bitrate {bitrate} dbitrate {dbitrate} restart-ms 1000 berr-reporting on fd on"
    elif CAN_TYPE == "classic":
        CAN_COMMAND = "ip link set {iface} up txqueuelen 65535 type can bitrate {bitrate} berr-reporting on"
    else:
        journal.send(f"Unknown CAN type {CAN_TYPE}")
        return False

    net_stats = psutil.net_if_stats()

    for iface in ("can0", "can1"):
        network = net_stats.get(iface)
        if not network:
            journal.send(f"Network {iface} not found, skipping")
            continue
        if network.isup:
            journal.send(f"Network {iface} is already UP, skipping")
            continue

        cmd = CAN_COMMAND.format(
            iface=iface, bitrate=CAN_BITRATE, dbitrate=CAN_DBITRATE
        )
        journal.send(f"Running {cmd}...")
        retcode = subprocess.call(cmd.split(" "))
        if retcode != 0:
            journal.send(
                f"Failed to configure {iface}, stopping can config", RETCODE=retcode
            )
            break
    else:
        return True
    return False


def main() -> None:
    journal.send("Starting board configuration")
    for setup_func in (setup_can,):
        success = setup_func()
        if not success:
            journal.send(f"Failed during {setup_func.__name__}")
            return 1
    else:
        journal.send("All done")
        return 0


if __name__ == "__main__":
    exit(main())