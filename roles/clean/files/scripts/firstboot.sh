#!/bin/bash
set -euo pipefail

# Host keys must be created on the device booting the copied image.
/usr/bin/ssh-keygen -A
/home/pi/extra/scripts/expand_sd_card.sh
