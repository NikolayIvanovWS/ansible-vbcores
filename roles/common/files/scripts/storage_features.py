#!/usr/bin/python3
"""Conservative read-only probes: preserve maintenance for configured storage."""
import json
from pathlib import Path
import subprocess

result = subprocess.run(
    ['lsblk', '--json', '--list', '--output', 'TYPE,FSTYPE'],
    check=True, capture_output=True, text=True,
)
devices = json.loads(result.stdout)['blockdevices']

def populated(path):
    directory = Path(path)
    return directory.exists() and any(directory.iterdir())

def config_lines(path):
    file = Path(path)
    if not file.exists():
        return []
    return [line.strip() for line in file.read_text().splitlines()
            if line.strip() and not line.lstrip().startswith('#')]

fstab = [line.split() for line in config_lines('/etc/fstab')]
lvm = any(d.get('type') == 'lvm' or d.get('fstype') == 'LVM2_member' for d in devices)
lvm = lvm or populated('/etc/lvm/backup') or populated('/etc/lvm/archive')
# Mapper entries can also be encryption/multipath: err on the side of retaining services.
lvm = lvm or any(row[0].startswith('/dev/mapper/') for row in fstab)
raid = any(str(d.get('type', '')).startswith('raid') or d.get('fstype') == 'linux_raid_member' for d in devices)
raid = raid or any(line.startswith('ARRAY ') for p in ['/etc/mdadm/mdadm.conf', '/etc/mdadm.conf'] for line in config_lines(p))
iscsi = populated('/etc/iscsi/nodes') or populated('/sys/class/iscsi_session')
xfs = any(d.get('fstype') == 'xfs' for d in devices) or any(len(row) > 2 and row[2] == 'xfs' for row in fstab)
print(json.dumps(dict(lvm=lvm, raid=raid, iscsi=iscsi, xfs=xfs)))
