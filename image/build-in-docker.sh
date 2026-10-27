#!/bin/bash
# Build the AirXPi image inside a privileged Docker container (works on macOS,
# Windows/WSL and any Linux host, and is what CI uses).
#
#   sudo ./image/build-in-docker.sh
#
# qemu-user-static + binfmt_misc are required for arm64 emulation on x86 hosts.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK="${WORK:-$REPO_ROOT/.build}"
PIGEN="$WORK/pi-gen"

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }

# arm64 emulation for non-arm64 hosts
if [ "$(uname -m)" != "aarch64" ] && [ "$(uname -m)" != "arm64" ]; then
    if [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
        echo "==> registering binfmt handlers"
        docker run --privileged --rm tonistiigi/binfmt --install arm64
    fi
fi

"$REPO_ROOT/image/build.sh" prepare

echo "==> building in docker (privileged; 40-90 minutes)"
cd "$PIGEN"
./build-docker.sh

mkdir -p "$REPO_ROOT/dist"
cp -v deploy/*.zip deploy/*.img.xz "$REPO_ROOT/dist/" 2>/dev/null || true
ls -lh "$REPO_ROOT/dist"
