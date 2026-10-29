#!/usr/bin/env python3
"""The jevqueue command line, from the plugin's own directory.

The implementation is :mod:`jevqueue.cli`, so an installed copy and this one behave
identically.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jevqueue.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
