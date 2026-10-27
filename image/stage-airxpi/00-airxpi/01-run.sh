#!/bin/bash -e
# Copy the appliance sources into the image, then run the installer inside the
# root filesystem. pi-gen runs this from the sub-stage directory, so `files/`
# and `ROOTFS_DIR` are both available.

install -d "${ROOTFS_DIR}/opt/airxpi-src"
cp -a files/repo/. "${ROOTFS_DIR}/opt/airxpi-src/"
rm -rf "${ROOTFS_DIR}/opt/airxpi-src/.git" "${ROOTFS_DIR}/opt/airxpi-src/.build"

# shairport-sync 5.6 and nqptp are compiled here; on an emulated builder this is
# the slow part of the image build.
on_chroot << EOF
cd /opt/airxpi-src
sh image/install.sh --image
cd /
rm -rf /opt/airxpi-src
EOF
