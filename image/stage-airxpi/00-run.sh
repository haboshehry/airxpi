#!/bin/bash -e
# Stage: copy the AirXPi sources into the image so the chroot can install them.

install -d "${ROOTFS_DIR}/opt/airxpi-src"
cp -a "${BASE_DIR}/stage-airxpi/repo/." "${ROOTFS_DIR}/opt/airxpi-src/"
rm -rf "${ROOTFS_DIR}/opt/airxpi-src/.git" "${ROOTFS_DIR}/opt/airxpi-src/.build"
