"""Generated test files. Nothing binary is committed; helpers build files on demand."""

from __future__ import annotations

import io
import os

from pypdf import PdfWriter

# Smallest valid JPEG (1x1 pixel), from the JPEG baseline spec.
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707070909080a0c140d0c0b0b0c"
    "1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c30313434341f27393d38323c2e333432ffc0"
    "000b080001000101011100ffc40014000100000000000000000000000000000009ffc40014100100000000000000"
    "00000000000000000000ffda0008010100003f00d2cf20ffd9"
)


def make_pdf(pages: int = 1, pad_bytes: int = 0, encrypt: str | None = None) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    if pad_bytes:
        w.add_attachment("pad.bin", os.urandom(pad_bytes))
    if encrypt:
        w.encrypt(encrypt)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()
