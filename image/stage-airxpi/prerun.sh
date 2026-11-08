#!/bin/bash -e
# Start the appliance stage from the previous rootfs.
#
# pi-gen creates (and empties) work/<image>/<stage>/rootfs *before* running
# prerun.sh, so "if the directory does not exist" is never true and the stage
# used to run against an empty tree:
#
#     realpath: .../stage-airxpi/rootfs/proc: No such file or directory
#     Unable to chroot/chdir to [.../stage-airxpi/rootfs/]  Build failed
#
# Test for a real filesystem instead, and do not depend on pi-gen's
# copy_previous(): it exists in some branches only.

if [ -e "${ROOTFS_DIR}/etc/os-release" ]; then
	exit 0
fi

src="${PREV_ROOTFS_DIR:-}"
if [ -z "${src}" ] || [ ! -d "${src}" ]; then
	# resumed build: the earlier stages were skipped, so pi-gen left
	# PREV_ROOTFS_DIR empty - reuse the newest completed stage tree
	for candidate in /work/pi-gen/work/*/stage2/rootfs /work/pi-gen/work/*/stage1/rootfs; do
		if [ -d "${candidate}" ]; then
			src="${candidate}"
			break
		fi
	done
fi

if [ -z "${src}" ] || [ ! -d "${src}" ]; then
	echo "stage-airxpi: no previous rootfs (PREV_ROOTFS_DIR='${PREV_ROOTFS_DIR}')" >&2
	exit 1
fi

echo "stage-airxpi: seeding rootfs from ${src}"
# pi-gen sets ROOTFS_DIR but does not create it before prerun runs
mkdir -p "${ROOTFS_DIR}"
cp -a "${src}/." "${ROOTFS_DIR}/"
