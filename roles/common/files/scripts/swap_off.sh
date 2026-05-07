#!/bin/bash
if [ -f /swapfile ] ; then
 echo 'Removing the swap file'
 swapoff /swapfile
 rm /swapfile
 sudo sed -i 's/^\/swapfile swap swap defaults 0 0/#\/swapfile swap swap defaults 0 0/' /etc/fstab
else
 echo 'No Swap file'
fi