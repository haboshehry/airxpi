# AirXPi - convenience targets.  Everything runs on a Debian/Raspberry Pi OS
# host; the image targets a Raspberry Pi 3B (arm64 Bookworm).

SHELL := /bin/bash
PYTHON ?= python3
SUDO ?= sudo

.PHONY: help check lint install image image-docker clean

help:
	@echo "AirXPi"
	@echo "  make check        python syntax check of every module"
	@echo "  make install      install on the current Raspberry Pi OS (needs root)"
	@echo "  make image        build the flashable image (pi-gen, native arm64 host)"
	@echo "  make image-docker build the image in Docker (any host)"
	@echo "  make clean        remove build output"

check:
	$(PYTHON) -m compileall -q src/airxpi
	$(PYTHON) - <<'PY'
import ast, pathlib, sys
bad = []
for path in pathlib.Path("src").rglob("*.py"):
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        bad.append("%s: %s" % (path, exc))
for item in bad:
    print(item)
sys.exit(1 if bad else 0)
PY
	@node --check src/airxpi/web/app.js 2>/dev/null || echo "(node not installed, skipped app.js check)"
	@echo "syntax ok"

install:
	$(SUDO) sh image/install.sh

image:
	$(SUDO) ./image/build.sh

image-docker:
	$(SUDO) ./image/build-in-docker.sh

clean:
	rm -rf .build dist
