#!/bin/bash
# Build a flashable AirXPi image for the Raspberry Pi 3B with pi-gen.
#
#   ./image/build.sh prepare     # clone pi-gen and assemble the custom stage
#   ./image/build.sh build       # run the build (needs root + binfmt on x86)
#   ./image/build.sh             # prepare + build
#
# Requirements: a Debian/Ubuntu host, root (or sudo), git, rsync, binfmt_misc
# with qemu-user-static when the host is not arm64.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK="${WORK:-$REPO_ROOT/.build}"
PIGEN="$WORK/pi-gen"
PIGEN_REPO="${PIGEN_REPO:-https://github.com/RPi-Distro/pi-gen.git}"
PIGEN_BRANCH="${PIGEN_BRANCH:-arm64}"
RELEASE="${RELEASE:-bookworm}"
IMG_NAME="${IMG_NAME:-airxpi-$(date +%Y%m%d)-rpi3b}"

prepare() {
    echo "==> preparing $WORK"
    mkdir -p "$WORK"
    if [ ! -d "$PIGEN/.git" ]; then
        git clone --depth 1 --branch "$PIGEN_BRANCH" "$PIGEN_REPO" "$PIGEN"
    fi

    rm -rf "$PIGEN/stage-airxpi"
    mkdir -p "$PIGEN/stage-airxpi"
    cp -a "$REPO_ROOT/image/stage-airxpi/." "$PIGEN/stage-airxpi/"
    rsync -a --delete \
        --exclude '.git' --exclude '.build' --exclude 'dist' \
        "$REPO_ROOT/" "$PIGEN/stage-airxpi/repo/"

    # only the last stage exports an image
    for stage in stage0 stage1 stage2; do
        rm -f "$PIGEN/$stage/EXPORT_IMAGE" "$PIGEN/$stage/EXPORT_NOOBS"
    done

    cat > "$PIGEN/config" <<EOF
IMG_NAME='$IMG_NAME'
RELEASE='$RELEASE'
ARCH='arm64'
DEPLOY_COMPRESSION='xz'
COMPRESSION_LEVEL='6'
ENABLE_SSH='1'
TARGET_HOSTNAME='airxpi'
FIRST_USER_NAME='airxpi'
FIRST_USER_PASS='airxpi'
DISABLE_FIRST_BOOT_USER_RENAME='1'
STAGE_LIST='stage0 stage1 stage2 stage-airxpi'
EOF

    # keep WPA config out of the image: the appliance is the access point
    rm -f "$PIGEN/stage2/00-install-wpa-conf" 2>/dev/null || true
    echo "==> stage ready"
}

build() {
    [ "$(id -u)" = "0" ] || { echo "build needs root: sudo $0 build" >&2; exit 1; }
    prepare
    cd "$PIGEN"
    echo "==> running pi-gen (this takes 40-90 minutes on an x86 host)"
    ./build.sh
    mkdir -p "$REPO_ROOT/dist"
    cp -v deploy/*.zip deploy/*.img.xz "$REPO_ROOT/dist/" 2>/dev/null || true
    echo "==> artefacts in $REPO_ROOT/dist"
    ls -lh "$REPO_ROOT/dist" || true
}

case "${1:-all}" in
    prepare) prepare ;;
    build) build ;;
    all) build ;;
    *) echo "usage: $0 [prepare|build]" >&2; exit 2 ;;
esac
