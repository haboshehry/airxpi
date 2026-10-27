#!/bin/bash -e
# Start the appliance stage from the previous rootfs (pi-gen provides
# copy_previous; every stage needs its own prerun.sh).

if [ ! -d "${ROOTFS_DIR}" ]; then
	copy_previous
fi
