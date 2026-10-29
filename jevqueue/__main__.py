"""``python -m jevqueue`` -- run the demo without a key, a network or a provider.

See :mod:`jevqueue.demo` for what it shows.
"""

from __future__ import annotations

from .demo import main

if __name__ == "__main__":
    raise SystemExit(main())
