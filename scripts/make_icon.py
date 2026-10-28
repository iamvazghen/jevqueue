"""Generate the plugin icon: a queue.

A stack of three bars, the top one held back from the other two. That is the whole idea:
steps waiting to be released by a decision.

Written with zlib rather than Pillow so the repository needs no image dependency.
"""

from __future__ import annotations

import os
import struct
import zlib

SIZE = 512
BACKGROUND = (0x1F, 0x23, 0x28, 255)
FOREGROUND = (0xFF, 0xFF, 0xFF, 255)
HELD = (0x7C, 0x9C, 0xFF, 255)


def _pixel(x: int, y: int) -> tuple[int, int, int, int]:
    # Three horizontal bars, evenly spaced. The middle one is offset to the right, which is
    # the one being held out of the queue.
    bars = (
        (120, 392, 150, 210),  # left, right, top, height
        (210, 440, 231, 210),
        (120, 392, 312, 210),
    )
    for index, (left, right, top, height) in enumerate(bars):
        if top <= y < top + height and left <= x < right:
            return HELD if index == 1 else FOREGROUND
    return BACKGROUND


def _png(path: str) -> None:
    raw = bytearray()
    for y in range(SIZE):
        raw.append(0)  # filter type 0
        for x in range(SIZE):
            raw.extend(_pixel(x, y))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    blob = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as handle:
        handle.write(blob)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    target = os.path.normpath(os.path.join(here, "..", "assets", "icon.png"))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    _png(target)
    print(f"wrote {target} ({os.path.getsize(target)} bytes)")
