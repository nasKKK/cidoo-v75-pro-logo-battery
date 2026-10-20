#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rebuilds patch/logo-patch.hex from src/ with the TC32 GCC toolchain and checks that the result,
applied to the official firmware, gives the expected image.

  python build.py --tc32 <toolchain bin folder> [--updater V75PRO.zip]

Toolchain: tc32-elf-gcc 4.5.1 (github.com/devbis/tc32, branch for your system).
"""
import argparse
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import install  # noqa: E402

SRC = os.path.join(HERE, "src")
BUILD = os.path.join(HERE, "build")


def run(args):
    r = subprocess.run(args, cwd=SRC, capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        sys.exit("FAILED: %s\n%s%s" % (" ".join(args), r.stdout, r.stderr))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tc32", required=True, help="folder with tc32-elf-gcc, -ld, -objcopy")
    ap.add_argument("--updater", help="V75PRO.zip (downloaded from Epomaker if not given)")
    a = ap.parse_args()

    ext = ".exe" if os.name == "nt" else ""
    tool = lambda name: os.path.join(a.tc32, "tc32-elf-" + name + ext)  # noqa: E731
    os.makedirs(BUILD, exist_ok=True)
    o = lambda name: os.path.join(BUILD, name)  # noqa: E731
    cflags = ["-Os", "-ffreestanding", "-fno-builtin", "-fno-common", "-ffunction-sections", "-Wall", "-Wextra"]
    run([tool("gcc"), "-c"] + cflags + ["logo.c", "-o", o("logo.o")])
    run([tool("gcc"), "-c", "hooks.S", "-o", o("hooks.o")])
    run([tool("ld"), "-T", "patch.ld", "-nostdlib", o("hooks.o"), o("logo.o"), "-o", o("patch.elf"), "-Map", o("patch.map")])
    run([tool("objcopy"), "-O", "ihex", o("patch.elf"), install.PATCH_HEX])

    fw = install.original_firmware(a.updater or install.download_updater())
    image = install.apply_patch(fw, install.load_ihex(install.PATCH_HEX))
    install.check_image(image, "patched firmware")
    sha = hashlib.sha256(image).hexdigest()
    print("patched image:", len(image), "bytes, sha256", sha)
    if sha != install.PATCHED_SHA256:
        print("differs from PATCHED_SHA256 in install.py: update it if the change is intended")


if __name__ == "__main__":
    main()
