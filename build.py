#!/usr/bin/env python3
"""Build the modified firmware for Laserwar Smart PRO Remote from the official v1.14.

  python build.py Smart_PRO_Remote_v1_14.zip
  python build.py Smart_PRO_Remote_v1.14.bin -o my.bin
"""
from __future__ import annotations

import argparse
import hashlib
import io
import struct
import sys
import time
import zipfile
from pathlib import Path

from patcher.cave import APP_BASE, build_image, expect, load_profile, verify
from patcher.thumb import STOCK_SIZE, stm32_crc_le

MOD_VERSION = "1.04"
STOCK_SHA256 = "097808d64c3cb744bc2328200359f57fa9592ab4148d43a722d9dd4785143d94"
STOCK_URL = "https://laserwar.ru/admin/uploads/adminFiles/Smart_PRO_Remote_v1_14.zip"
GAP_MS = 120


def read_stock(path: Path) -> bytes:
    """Official v1.14 image from the .zip as downloaded or from the .bin inside it."""
    data = path.read_bytes()
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            images = [z.read(n) for n in z.namelist() if n.lower().endswith(".bin")]
        found = [img for img in images if hashlib.sha256(img).hexdigest() == STOCK_SHA256]
        if not found:
            sys.exit(f"{path.name}: no official v1.14 .bin inside the archive.\nDownload: {STOCK_URL}")
        return found[0]
    if hashlib.sha256(data).hexdigest() != STOCK_SHA256:
        sys.exit(f"{path.name}: this is not the official v1.14 firmware (SHA-256 mismatch).\n"
                 f"Download: {STOCK_URL}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Smart PRO Remote v1.14 mod " + MOD_VERSION)
    ap.add_argument("stock", type=Path, help="Smart_PRO_Remote_v1_14.zip or the .bin from it")
    ap.add_argument("-o", "--out", type=Path, default=Path(f"Smart_PRO_Remote_v1.14_mod_{MOD_VERSION}.bin"))
    ap.add_argument("--quick", action="store_true", help="skip the self-check (about a minute)")
    ap.add_argument("--verbose", action="store_true", help="print every checked menu item")
    args = ap.parse_args()

    stock = read_stock(args.stock)
    expect(len(stock) == STOCK_SIZE and stm32_crc_le(stock[:-4]) == struct.unpack("<I", stock[-4:])[0],
           "stock image is damaged")
    p = load_profile("1.14")
    try:
        image, meta = build_image(p, stock, GAP_MS)
        if not args.quick:
            print("Checking the new menu, this takes about a minute...")
            t0 = time.time()
            log = verify(p, bytes(image), stock, meta)
            if args.verbose:
                print("\n".join(log))
            print(f"Check passed in {time.time() - t0:.0f} s: {log[-3].strip()}")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    args.out.write_bytes(image)
    free = STOCK_SIZE - meta["cave_end"]
    print(f"Written {args.out} ({len(image)} bytes, signature {meta['sig'].hex()}, "
          f"{free} bytes of flash left, code at {APP_BASE + p.cave:#x})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
