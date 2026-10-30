#!/usr/bin/python3
"""Remove dependent snaps before bases, preserving failures for Ansible."""
import shutil
import subprocess

if not shutil.which('snap'):
    print('Snap CLI absent; residual cleanup follows')
    raise SystemExit(0)


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=180)

result = run('snap', 'list')
if result.returncode:
    # An installed CLI with a broken daemon must not be mistaken for no snaps.
    if 'No snaps are installed' in result.stderr:
        raise SystemExit(0)
    raise SystemExit(result.stderr or result.stdout)
remaining = [line.split()[0] for line in result.stdout.splitlines()[1:] if line.strip()]
while remaining:
    progress = False
    errors = []
    # The snapd snap can only be removed after all other snaps.
    for name in sorted(remaining, key=lambda value: value == 'snapd'):
        result = run('snap', 'remove', '--purge', name)
        if result.returncode == 0:
            remaining.remove(name)
            progress = True
            print('Removed snap:', name)
        else:
            errors.append(f'{name}: {result.stderr or result.stdout}')
    if not progress:
        raise SystemExit('\n'.join(errors))
