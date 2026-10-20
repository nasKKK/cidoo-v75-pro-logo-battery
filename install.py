#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Battery level on the logo light bar of a CIDOO V75 Pro: installer.

The patched firmware is not distributed. This script takes the official CIDOO firmware V0101
from Epomaker's updater, checks that it is exactly that build, applies the patch in
patch/logo-patch.hex and sends the result to the keyboard over its USB cable, with the
update protocol of the keyboard's own firmware.

  python install.py              patch and install (asks before writing)
  python install.py --restore    install the original firmware V0101 again
  python install.py --check      everything except talking to the keyboard
  python install.py --updater FILE   use a downloaded V75PRO.zip or the .exe in it

Needs Python 3.8+ and the "hidapi" package (pip install hidapi).
"""
import argparse
import hashlib
import io
import os
import struct
import sys
import types
import urllib.request
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
UPDATER_URL = "https://epomaker.com/cdn/shop/files/V75PRO.zip"
CACHE = os.path.join(HERE, "downloads")
PATCH_HEX = os.path.join(HERE, "patch", "logo-patch.hex")

ORIG_SIZE = 121332
ORIG_SHA256 = "b0c88f17eb2dcabb1dc4fcc06161f147643eead1e0414df3546fd526c098af20"
PATCHED_SHA256 = "ae4bb42a1c8a466ce603b7cdbc98728cbe0ed5b9ec02302950cd53d390ee3912"
CODE_START = 0x1DA00

# Factory bytes each hook replaces, as stored in the image.
HOOKS = {
    0xB41C: bytes.fromhex("ff97949f"),  # tjl 0xb348 (logo mode 3, static colour)
    0xB66E: bytes.fromhex("530ca248"),  # low battery branch, after the LED buffers are cleared
    0xB558: bytes.fromhex("970a1148"),  # low battery branch, between its refreshes
}

USB_VID, USB_PID, USB_PRODUCT, USB_RELEASE = 0x320F, 0x5055, "CIDOO V75", 0x0101


# --- the image ------------------------------------------------------------------------------
def telink_crc32(data):
    return zlib.crc32(data) ^ 0xFFFFFFFF


def check_image(img, label):
    size = struct.unpack_from("<I", img, 0x18)[0]
    if img[8:12] != b"KNLT" or size != len(img) or size % 16 != 4 or size > 0x20000:
        sys.exit(f"{label}: not a valid firmware image")
    if struct.unpack_from("<I", img, size - 4)[0] != telink_crc32(img[:-4]):
        sys.exit(f"{label}: CRC-32 does not match")


def load_ihex(path):
    mem, base = {}, 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue
            rec = bytes.fromhex(line[1:])
            if sum(rec) & 0xFF:
                sys.exit(f"{path}: bad checksum")
            n, addr, typ = rec[0], int.from_bytes(rec[1:3], "big"), rec[3]
            data = rec[4:4 + n]
            if typ == 0:
                for i, b in enumerate(data):
                    mem[base + addr + i] = b
            elif typ == 2:
                base = int.from_bytes(data, "big") << 4
            elif typ == 4:
                base = int.from_bytes(data, "big") << 16
    return mem


def apply_patch(orig, mem):
    """The factory image with the hooks and the new code; refuses anything unexpected."""
    for addr, old in HOOKS.items():
        if orig[addr:addr + len(old)] != old:
            sys.exit("the factory bytes at 0x%x are not the expected ones" % addr)
    allowed = {a + i for a, old in HOOKS.items() for i in range(len(old))}
    hooks = [a for a in mem if a < CODE_START]
    code = sorted(a for a in mem if a >= CODE_START)
    if set(hooks) != allowed:
        sys.exit("the patch writes outside the hook sites")
    body = bytearray(orig[:-4])
    for a in hooks:
        body[a] = mem[a]
    body += bytes(code[-1] + 1 - len(body))
    for a in code:
        body[a] = mem[a]
    body += bytes(-len(body) % 16)  # with the CRC the size is 16n + 4
    struct.pack_into("<I", body, 0x18, len(body) + 4)
    return bytes(body) + struct.pack("<I", telink_crc32(bytes(body)))


# --- the official firmware ------------------------------------------------------------------
def read_updater(path):
    """The updater .exe from V75PRO.zip, or the .exe itself."""
    data = open(path, "rb").read()
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            exes = [n for n in z.namelist() if n.lower().endswith(".exe")]
            if len(exes) != 1:
                sys.exit(f"{path}: expected one .exe in the archive, found {exes}")
            data = z.read(exes[0])
    return data


def download_updater():
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "V75PRO.zip")
    if not os.path.exists(path):
        print(f"downloading the official updater: {UPDATER_URL}")
        req = urllib.request.Request(UPDATER_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r, open(path + ".part", "wb") as f:
            f.write(r.read())
        os.replace(path + ".part", path)
    return path


def original_firmware(updater):
    exe = read_updater(updater)
    pos = exe.find(b"KNLT")
    if pos < 8:
        sys.exit("no firmware image found in the updater")
    start = pos - 8
    size = struct.unpack_from("<I", exe, start + 0x18)[0]
    fw = exe[start:start + size]
    if len(fw) != ORIG_SIZE or hashlib.sha256(fw).hexdigest() != ORIG_SHA256:
        sys.exit("the firmware in this updater is not CIDOO V75 Pro V0101 as expected: nothing done")
    check_image(fw, "original firmware")
    return fw


# --- the keyboard ---------------------------------------------------------------------------
def telink_ota():
    """tools/telink_ota.py (zmk-tc32) with either Python HID package: "hid" (hid.Device) or
    "hidapi" (hid.device)."""
    import hid

    if not hasattr(hid, "Device"):
        class Device:
            def __init__(self, path):
                self._d = hid.device()
                self._d.open_path(path)
                self.product = self._d.get_product_string()

            def write(self, data):
                n = self._d.write(bytes(data))
                if n < 0:
                    raise IOError("HID write failed")
                return n

            def read(self, size, timeout_ms):
                return bytes(self._d.read(size, timeout_ms))

            def get_report_descriptor(self):
                return bytes(self._d.get_report_descriptor())

            def close(self):
                self._d.close()

        shim = types.ModuleType("hid")
        shim.enumerate = hid.enumerate
        shim.Device = Device
        sys.modules["hid"] = shim
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import telink_ota as ota

    return ota


def flash(image, name, yes):
    path = os.path.join(CACHE, name)
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "wb") as f:
        f.write(image)
    if not yes:
        print("\nThe keyboard must be on its USB cable, mode switch in the wired position, charged.")
        print("Keep the cable in until the script says it is done (about 20 seconds).")
        if input("Write the firmware to the keyboard now? Type yes: ").strip().lower() != "yes":
            sys.exit("nothing written")
    ota = telink_ota()
    ota.main(["flash", path, "--vid", "%04x" % USB_VID, "--pid", "%04x" % USB_PID,
              "--product", USB_PRODUCT, "--release", "%04x" % USB_RELEASE, "--yes"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--updater", help="V75PRO.zip or the updater .exe (downloaded from Epomaker if not given)")
    ap.add_argument("--restore", action="store_true", help="install the original firmware V0101")
    ap.add_argument("--check", action="store_true", help="prepare and check the image, do not talk to the keyboard")
    ap.add_argument("--yes", action="store_true", help="do not ask before writing")
    a = ap.parse_args()

    fw = original_firmware(a.updater or download_updater())
    print("original firmware V0101: OK")
    if a.restore:
        image, name = fw, "cidoo-v75pro-V0101.bin"
    else:
        image, name = apply_patch(fw, load_ihex(PATCH_HEX)), "cidoo-v75pro-V0101-logo-battery.bin"
        check_image(image, "patched firmware")
        if hashlib.sha256(image).hexdigest() != PATCHED_SHA256:
            sys.exit("the patched image is not the expected one: nothing done")
        print("patched firmware: OK")
    if a.check:
        print("check only: nothing sent to the keyboard")
        return
    flash(image, name, a.yes)
    print("\nDone. Select the logo colour after purple with Fn+PgDn (logo mode: solid colour, Fn+PgUp).")


if __name__ == "__main__":
    main()
