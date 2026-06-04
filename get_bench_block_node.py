#!/usr/bin/env python3
"""
get_bench_block.py

Export a block from an already-running Bitweb node as a binary .raw file.
The node must be running and synced. This script only uses bitweb-cli.

Usage:
  python3 get_bench_block.py
  python3 get_bench_block.py --height 1000
  python3 get_bench_block.py --height 1000 --out block1000.raw
  python3 get_bench_block.py --cli /path/to/bitweb-cli --height 1000
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys

IS_WINDOWS = platform.system() == "Windows"


def find_cli(hint=None):
    """
    Find bitweb-cli in order:
      1. --cli argument
      2. Same folder as this script  (most useful: script placed next to binaries)
      3. Current working directory
      4. PATH (shutil.which)
      5. Ask user interactively
    """
    candidates = ["bitweb-cli.exe", "bitweb-cli"] if IS_WINDOWS else ["bitweb-cli"]

    # 1. Explicit hint
    if hint:
        hint = os.path.expanduser(hint.strip().strip('"').strip("'"))
        if os.path.isfile(hint):
            return hint
        print(f"[!] Not found: {hint}", file=sys.stderr)

    # 2. Same folder as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for name in candidates:
        path = os.path.join(script_dir, name)
        if os.path.isfile(path):
            print(f"Found bitweb-cli: {path}")
            return path

    # 3. Current working directory
    cwd = os.getcwd()
    if cwd != script_dir:
        for name in candidates:
            path = os.path.join(cwd, name)
            if os.path.isfile(path):
                print(f"Found bitweb-cli: {path}")
                return path

    # 4. PATH
    for name in candidates:
        found = shutil.which(name)
        if found:
            print(f"Found bitweb-cli: {found}")
            return found

    # 5. Ask user
    print("bitweb-cli not found automatically.")
    while True:
        path = input("Path to bitweb-cli: ").strip().strip('"').strip("'")
        path = os.path.expanduser(path)
        if os.path.isfile(path):
            return path
        print(f"[!] Not found: {path}")


def cli_run(cli, datadir, *cmd_args):
    """Run bitweb-cli with optional -datadir."""
    base = [cli]
    if datadir:
        base.append(f"-datadir={datadir}")
    base.extend(str(a) for a in cmd_args)

    r = subprocess.run(base, capture_output=True, text=True)
    if r.returncode != 0:
        err = r.stderr.strip() or r.stdout.strip()
        print(f"\n[!] bitweb-cli error:\n{err}", file=sys.stderr)

        if "authentication cookie" in err or "RPC credentials" in err:
            print(
                "\nHint: bitweb-cli cannot find the auth cookie.\n"
                "      The node was likely started with a custom -datadir.\n"
                "      Re-run and enter the node datadir when prompted.\n"
                "      Windows default: C:\\Users\\<YOU>\\AppData\\Local\\Bitweb\n"
                "      Linux default:   ~/.bitweb",
                file=sys.stderr,
            )
        elif "connect to the server" in err or "EOF" in err:
            print(
                "\nHint: cannot reach node RPC. Make sure bitwebd is running.",
                file=sys.stderr,
            )

        sys.exit(1)
    return r.stdout.strip()


# ── Args ──────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Export a block from a running Bitweb node as .raw binary"
)
parser.add_argument("--cli",     metavar="PATH", help="Path to bitweb-cli")
parser.add_argument("--datadir", metavar="PATH", help="Node datadir (optional, if non-default)")
parser.add_argument("--height",  type=int,       help="Block height to export")
parser.add_argument("--out",     metavar="PATH", help="Output file path")
args = parser.parse_args()

# ── Interactive prompts ───────────────────────────────────────────────────────

print()
CLI = find_cli(args.cli)

# Datadir — ask interactively if not passed as argument
if args.datadir:
    DATADIR = args.datadir
else:
    if IS_WINDOWS:
        default_hint = "C:\\Users\\<YOU>\\AppData\\Local\\Bitweb"
    else:
        default_hint = "~/.bitweb"
    raw = input(
        f"Node datadir (Enter = node default, or full path if started with custom -datadir)\n"
        f"  [{default_hint}]\n"
        f"  > "
    ).strip().strip('"').strip("'")
    DATADIR = os.path.expanduser(raw) if raw else None

if args.height is None:
    raw = input("Block height [0]: ").strip()
    args.height = int(raw) if raw else 0

if args.out is None:
    default = f"block{args.height}.raw"
    raw = input(f"Output file [{default}]: ").strip().strip('"').strip("'")
    args.out = os.path.expanduser(raw) if raw else default

args.out = os.path.abspath(args.out)

# ── Fetch block ───────────────────────────────────────────────────────────────

print(f"\nConnecting to node...")
current = int(cli_run(CLI, DATADIR, "getblockcount"))
print(f"Node height: {current}")

if args.height > current:
    print(f"[!] Height {args.height} > current chain height {current}", file=sys.stderr)
    sys.exit(1)

print(f"Fetching block {args.height}...")
block_hash = cli_run(CLI, DATADIR, "getblockhash", str(args.height))
print(f"Hash: {block_hash}")

block_hex = cli_run(CLI, DATADIR, "getblock", block_hash, "0")
raw_bytes = bytes.fromhex(block_hex)
print(f"Size: {len(raw_bytes)} bytes")

# ── Write file ────────────────────────────────────────────────────────────────

out_dir = os.path.dirname(args.out)
if out_dir:
    os.makedirs(out_dir, exist_ok=True)

with open(args.out, "wb") as f:
    f.write(raw_bytes)

print(f"\nWritten: {args.out}")
