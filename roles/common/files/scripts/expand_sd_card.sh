#!/bin/bash
sudo /usr/bin/growpart /dev/mmcblk0 2
sudo /usr/sbin/resize2fs /dev/mmcblk0p2
