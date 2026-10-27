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

    # Debian's archive keys must be readable inside the rootfs before the first
    # chroot apt run. With a foreign-architecture debootstrap (qemu) the keyring
    # occasionally ends up missing, and every `apt-get update` then fails with
    # NO_PUBKEY. Insert the copy right before pi-gen enters the chroot.
    STAGE0="$PIGEN/stage0/00-configure-apt/00-run.sh"
    if ! grep -q 'airxpi: keep the Debian archive keyring' "$STAGE0"; then
        cat > "$WORK/keyring-sync.txt" <<'KEYRING'
# -- airxpi: keep the Debian archive keyring inside the rootfs
mkdir -p "${ROOTFS_DIR}/usr/share/keyrings" "${ROOTFS_DIR}/etc/apt/trusted.gpg.d"
install -m 644 /usr/share/keyrings/debian-archive-keyring.gpg "${ROOTFS_DIR}/usr/share/keyrings/debian-archive-keyring.gpg"
# debian.sources in this pi-gen release points at the .pgp name
install -m 644 /usr/share/keyrings/debian-archive-keyring.gpg "${ROOTFS_DIR}/usr/share/keyrings/debian-archive-keyring.pgp"
cp -f /etc/apt/trusted.gpg.d/debian-archive-*.asc "${ROOTFS_DIR}/etc/apt/trusted.gpg.d/" 2>/dev/null || true
ls -l "${ROOTFS_DIR}/usr/share/keyrings/debian-archive-keyring.gpg" >&2

KEYRING
        awk '/^on_chroot/ && !done { while ((getline line < sync) > 0) print line; done = 1 } { print }' \
            sync="$WORK/keyring-sync.txt" "$STAGE0" > "$STAGE0.new"
        cat "$STAGE0.new" > "$STAGE0"
        rm -f "$STAGE0.new"
        chmod 755 "$STAGE0"
        echo "==> stage0 keyring sync injected"
    fi

    # These Raspberry Pi utilities exist only in newer repositories; on the
    # arm64 bookworm branch apt aborts with "Unable to locate package".
    PKGS="$PIGEN/stage2/01-sys-tweaks/00-packages"
    if [ -f "$PKGS" ] && grep -q 'rpi-swap' "$PKGS"; then
        sed -i \
            -e 's/^rpi-swap rpi-loop-utils$/# rpi-swap rpi-loop-utils: only in newer RPi repositories/' \
            -e 's/rpi-usb-gadget //' \
            "$PKGS"
        echo "==> dropped packages that the bookworm arm64 repository lacks"
    fi

    # rpi-resize is a unit of the newer Raspberry Pi OS layout; on the arm64
    # bookworm branch `systemctl enable` aborts the stage with "unit does not
    # exist". The appliance resizes its card on first boot by itself, so the unit
    # (and the failure) is irrelevant here.
    SYS_TWEAKS="$PIGEN/stage2/01-sys-tweaks/01-run.sh"
    if [ -f "$SYS_TWEAKS" ] && grep -q 'systemctl enable rpi-resize' "$SYS_TWEAKS"; then
        sed -i 's@^[[:space:]]*systemctl enable rpi-resize[[:space:]]*$@systemctl enable rpi-resize 2>/dev/null || true@' "$SYS_TWEAKS"
        echo "==> made the rpi-resize enable non-fatal"
    fi

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

    # Foreign-architecture builds: pi-gen's dependency check looks for a binary
    # called qemu-aarch64, while Debian ships qemu-aarch64-static (the
    # qemu-user-binfmt package conflicts with qemu-user-static).
    if ! arch-test -n arm64 >/dev/null 2>&1; then
        for candidate in /usr/bin/qemu-aarch64-static /usr/local/bin/qemu-aarch64-static; do
            if [ -x "$candidate" ] && [ ! -e /usr/local/bin/qemu-aarch64 ]; then
                ln -sf "$candidate" /usr/local/bin/qemu-aarch64
            fi
        done
    fi

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
