# Building the image

## What gets built

`image/build.sh` wraps [pi-gen](https://github.com/RPi-Distro/pi-gen) (branch
`arm64`) and adds one custom stage:

```
stage0 → stage1 → stage2 (Raspberry Pi OS Lite, bookworm, arm64)
                        └── stage-airxpi
                              00-packages   git, curl, ca-certificates
                              00-run.sh     copy this repository into /opt/airxpi-src
                              01-run-chroot.sh  sh image/install.sh --image
```

`install.sh` does the real work: packages, `nqptp` + `shairport-sync 5.6` from
source (`--with-airplay-2`), the app tree, hostapd/dnsmasq/avahi/strongSwan
configuration, systemd units, the boot `config.txt` block, the kiosk UI and the
first panel password.

Result: `dist/airxpi-<date>-rpi3b.img.xz` (compressed with xz).

## Requirements

| Host | Notes |
|---|---|
| Linux x86_64 | `qemu-user-static` + `binfmt_misc` for arm64; run as root |
| Linux aarch64 | native, no emulation |
| macOS / Windows | Docker Desktop with the privileged container support used by `build-in-docker.sh`, plus `tonistiigi/binfmt` |

Disk: ~12 GB free (pi-gen work dir + image). Time: 40-90 minutes on an x86 host,
~25 minutes on an arm64 host. Most of it is compiling `shairport-sync` under
emulation.

```bash
sudo apt install -y git rsync qemu-user-static binfmt-support
sudo ./image/build.sh              # prepare + build (native)
sudo ./image/build-in-docker.sh    # prepare + build inside Docker
```

`WORK=/mnt/big/airxpi ./image/build.sh` moves the work directory. The pi-gen
settings live in `.build/pi-gen/config` after `prepare`, so you can edit them and
re-run `./image/build.sh build` without re-preparing:

```
IMG_NAME='airxpi-20261027-rpi3b'
RELEASE='bookworm'
ARCH='arm64'
DEPLOY_COMPRESSION='xz'
ENABLE_SSH='1'
TARGET_HOSTNAME='airxpi'
FIRST_USER_NAME='airxpi'      # change before publishing an image
FIRST_USER_PASS='airxpi'
STAGE_LIST='stage0 stage1 stage2 stage-airxpi'
```

## CI

`.github/workflows/build-image.yml` runs the Docker build on `ubuntu-24.04`,
uploads `airxpi-image` as an artifact (30 days) and, on a `v*` tag, attaches the
image to the GitHub release. Manual runs: *Actions → build-image → Run workflow*.

## Installing without building an image

On an existing Raspberry Pi OS Lite (bookworm, 64-bit):

```bash
sudo sh image/install.sh              # builds the AirPlay 2 stack, installs, enables units
sudo sh image/install.sh --skip-build  # reuse an already AirPlay 2 capable shairport-sync
sudo reboot
```

`--image` is the pi-gen path: it skips `systemctl start` (no PID 1 in the chroot).

## Verify a fresh install

```bash
axp-doctor                     # services, audio PCMs, interfaces, VPN, AirPlay
systemctl status axnet axpanel axplay axgui
aplay -l                       # HDMI PCM present?
curl -s localhost:8090/api/state | head -c 400
```

Then: connect the TV, pick the device from an iPhone, confirm audio and cover art,
and check `http://10.42.0.1/` from a client on the AP.

## Updating a running appliance

```bash
cd /opt/airxpi-src && git pull            # or clone the repo again
sudo sh image/install.sh                  # keeps config + password
sudo systemctl restart axnet axplay axpanel axgui
```

The vendored `airplay2` and `vpnexit` folders are copied from this repository, so
updating them means updating this repo (see `docs/THIRD_PARTY.md`).

## Customising the image

| Want | Where |
|---|---|
| Different release (bullseye/trixie) | `.build/pi-gen/config` → `RELEASE` |
| 32-bit image | `PIGEN_BRANCH=master`, drop `ARCH='arm64'` |
| Different default SSID / password | `image/install.sh` (`AirXPi`, random) or `/etc/airxpi/airxpi.json` |
| Extra packages | `image/stage-airxpi/00-packages` or `BASE_PKGS` in `install.sh` |
| Different hostname | `TARGET_HOSTNAME` in the pi-gen config |
| No GUI (headless) | `systemctl disable axgui` and drop `python3-pyqt5` |
