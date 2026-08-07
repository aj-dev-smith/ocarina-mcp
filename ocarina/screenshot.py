"""PNG encoding for the screenshot sense — stdlib only, by house rule.

The instrument hands back raw RGBA8 (the frame the renderer actually
composited, top-down, no downconversion) because nothing in libultraship
vendors an image encoder and this lane does not add dependencies. So the
bytes become a PNG here, with zlib and struct, which is all a PNG needs:
a signature, an IHDR, one zlib stream of filtered scanlines, an IEND.

Filter type 0 (None) on every scanline. A smarter filter would compress
better; it would also be a second thing to be wrong about in a module
whose whole job is "the pixels arrive intact". A game frame at 640 wide
is a few hundred KB either way.
"""

from __future__ import annotations

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, data: bytes) -> bytes:
    """One PNG chunk: length, type, payload, CRC32 over type+payload."""
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def encode_png(rgba: bytes, width: int, height: int, level: int = 6) -> bytes:
    """RGBA8 (top-down, 4 bytes/pixel, no padding) -> a PNG file's bytes.

    Raises ValueError when the buffer does not match the declared size —
    a truncated frame silently encoded as a short image is exactly the
    kind of quiet lie docs/08 is about.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"png dimensions must be positive, got {width}x{height}")
    expected = width * height * 4
    if len(rgba) != expected:
        raise ValueError(f"expected {expected} bytes for {width}x{height} RGBA, "
                         f"got {len(rgba)}")

    stride = width * 4
    raw = bytearray()
    for y in range(height):
        raw.append(0)                       # filter type 0: None
        raw += rgba[y * stride:(y + 1) * stride]

    ihdr = struct.pack(">IIBBBBB", width, height,
                       8,   # bit depth
                       6,   # color type 6 = truecolour with alpha
                       0,   # compression: deflate
                       0,   # filter method: adaptive (per-scanline byte)
                       0)   # interlace: none
    return (PNG_SIGNATURE
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), level))
            + _chunk(b"IEND", b""))
