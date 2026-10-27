"""``python3 -m airxpi.gui`` - what the ``axgui-client`` wrapper starts."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
