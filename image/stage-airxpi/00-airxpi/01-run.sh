#!/bin/bash -e
# Copy the appliance sources into the image, then run the installer inside the
# root filesystem. pi-gen runs this from the sub-stage directory, so `files/`
# and `ROOTFS_DIR` are both available.

install -d "${ROOTFS_DIR}/opt/airxpi-src"
cp -a files/repo/. "${ROOTFS_DIR}/opt/airxpi-src/"
rm -rf "${ROOTFS_DIR}/opt/airxpi-src/.git" "${ROOTFS_DIR}/opt/airxpi-src/.build"

# install.sh skips a build when the binary already exists.  A stage that is
# re-run on top of an older rootfs therefore keeps the *old* configure flags
# (no --with-ffmpeg / --with-pipe), which is exactly how the "AirPlay 2 does
# not run" image was produced.  Drop them so the flags in this tree win.
rm -f "${ROOTFS_DIR}/usr/local/bin/shairport-sync" "${ROOTFS_DIR}/usr/local/bin/nqptp"
rm -rf "${ROOTFS_DIR}/root/shairport-sync" "${ROOTFS_DIR}/root/nqptp"

# shairport-sync 5.6 and nqptp are compiled here; on an emulated builder this is
# the slow part of the image build.
on_chroot << EOF
set -e
cd /opt/airxpi-src
sh image/install.sh --image
cd /
rm -rf /opt/airxpi-src
EOF
