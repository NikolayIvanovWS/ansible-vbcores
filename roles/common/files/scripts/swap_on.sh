#!/bin/bash
if [ ! -f /swapfile ] ; then
 echo 'Creating the swap file'
 fallocate -l 1G /swapfile
 chmod 0600 /swapfile
 mkswap /swapfile
 swapon /swapfile
 sudo sed -i 's/^#\/swapfile swap swap defaults 0 0/\/swapfile swap swap defaults 0 0/' /etc/fstab
else
 echo 'Swap file already exist'
fi