#!/bin/bash -e
# Stage: run the appliance installer inside the target root filesystem.
# shairport-sync and nqptp are compiled here (qemu user emulation on x86 hosts).

cd /opt/airxpi-src
sh image/install.sh --image
cd /
rm -rf /opt/airxpi-src
