#!/usr/bin/env python3
"""
get_bench_block.py  —  run from ~/bitweb/

Starts a temporary mainnet node, exports a block at given height as binary .raw
file for use in benchmarks, then stops the node and cleans up.

Usage:
  python3 get_bench_block.py                        # exports genesis (height 0)
  python3 get_bench_block.py --height 1000          # exports block at height 1000
  python3 get_bench_block.py --height 0 --out src/bench/data/block0.raw

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO DO IT MANUALLY FROM A RUNNING NODE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  # 1. Get block hash at desired height (e.g. 0 for genesis, or any other)
  bitweb-cli getblockhash <HEIGHT>

  # 2. Get raw hex of the block (format "0" = raw hex, no JSON)
  bitweb-cli getblock <HASH> 0

  # 3. Convert hex to binary .raw file in one shot
  bitweb-cli getblock $(bitweb-cli getblockhash <HEIGHT>) 0 | xxd -r -p > src/bench/data/my_block.raw

  # Example — genesis block:
  bitweb-cli getblock $(bitweb-cli getblockhash 0) 0 | xxd -r -p > src/bench/data/block0.raw

  # Example — block at height 50000 (once mainnet has enough blocks):
  bitweb-cli getblock $(bitweb-cli getblockhash 50000) 0 | xxd -r -p > src/bench/data/block50000.raw

  # 4. Verify the file looks correct:
  ls -lh src/bench/data/my_block.raw
  xxd src/bench/data/my_block.raw | head

  # 5. Add to src/Makefile.bench.include (or CMakeLists):
  #    RAW_BENCH_FILES = \
  #      src/bench/data/block413567.raw \
  #      src/bench/data/my_block.raw

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHEN TO REPLACE THE GENESIS BLOCK WITH A REAL MAINNET BLOCK:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Genesis block is minimal (1 coinbase tx, ~300 bytes). It is valid for
  correctness testing but not representative for performance benchmarking.

  Replace it with a block from a mature height (e.g. 100 000+) once mainnet
  has enough real transactions. A block with 1000+ txs will give meaningful
  deserialization and validation timing numbers.

  The only requirement: the block must pass CheckBlock() —
    - Valid Argon2id PoW
    - Valid merkle root
    - No malformed transactions
  Any real mainnet block satisfies this automatically.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse, subprocess, time, os, sys, shutil

# ── Config ───────────────────────────────────────────────────────────────────
BITWEB_DIR  = os.path.expanduser("~/bitweb")
CLI         = f"{BITWEB_DIR}/build/bin/bitweb-cli"
DAEMON      = f"{BITWEB_DIR}/build/bin/bitwebd"
NODE_DIR    = "/tmp/bw_bench_block_export"
# ─────────────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Export a Bitweb block as binary .raw file for benchmarks",
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
parser.add_argument(
    "--height", type=int, default=0,
    help="Block height to export (default: 0 = genesis)",
)
parser.add_argument(
    "--out", metavar="PATH", default=None,
    help=(
        "Output file path. "
        "Default: src/bench/data/block0.raw for height 0, "
        "src/bench/data/block<HEIGHT>.raw for others."
    ),
)
args = parser.parse_args()

# Resolve output path
if args.out is None:
    if args.height == 0:
        args.out = f"{BITWEB_DIR}/src/bench/data/block0.raw"
    else:
        args.out = f"{BITWEB_DIR}/src/bench/data/block{args.height}.raw"


def run(*cmd, check=True):
    cmd = [str(c) for c in cmd]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"FAIL: {' '.join(cmd)}", file=sys.stderr)
        print(r.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return r.stdout.strip()


def rpc(*rpc_args, check=True):
    return run(CLI, f"-datadir={NODE_DIR}", *rpc_args, check=check)


def wait_rpc(timeout=60):
    print("  Waiting for node...", end="", flush=True)
    for _ in range(timeout):
        r = subprocess.run(
            [CLI, f"-datadir={NODE_DIR}", "getblockcount"],
            capture_output=True
        )
        if r.returncode == 0:
            print(" ready")
            return
        time.sleep(1)
        print(".", end="", flush=True)
    print("\nTimeout!", file=sys.stderr)
    sys.exit(1)


def cleanup():
    if os.path.exists(NODE_DIR):
        shutil.rmtree(NODE_DIR)


# ── Main ─────────────────────────────────────────────────────────────────────

print(f"\n=== Exporting block at height {args.height} ===")

print("\n--- Step 1: Starting mainnet node ---")
cleanup()
os.makedirs(NODE_DIR)

run(DAEMON,
    f"-datadir={NODE_DIR}",
    "-daemon",
    "-listen=0",       # no inbound p2p
    "-connect=0",      # no outbound p2p
    "-nodnsseed",      # no DNS seed lookup
    "-noseednode")     # no hardcoded seed nodes
wait_rpc()

# Sanity check: requested height must exist
current_height = int(rpc("getblockcount"))
if args.height > current_height:
    print(f"\nERROR: requested height {args.height} > current chain height {current_height}",
          file=sys.stderr)
    rpc("stop", check=False)
    time.sleep(2)
    cleanup()
    sys.exit(1)


print(f"\n--- Step 2: Fetching block at height {args.height} ---")
block_hash = rpc("getblockhash", str(args.height))
print(f"  hash:  {block_hash}")

block_hex = rpc("getblock", block_hash, "0")
print(f"  size:  {len(block_hex) // 2} bytes")


print(f"\n--- Step 3: Writing {args.out} ---")
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
raw_bytes = bytes.fromhex(block_hex)
with open(args.out, "wb") as f:
    f.write(raw_bytes)
print(f"  OK — {len(raw_bytes)} bytes written")


print("\n--- Step 4: Shutdown and cleanup ---")
rpc("stop")
time.sleep(3)
cleanup()
print("  Temp node removed")


print(f"""
Done. Next steps:

  1. Add to src/Makefile.bench.include:
       RAW_BENCH_FILES = \\
         src/bench/data/block413567.raw \\
         src/bench/data/{os.path.basename(args.out)}

  2. Include in bench/block_bench.cpp:
       #include <src/bench/data/{os.path.splitext(os.path.basename(args.out))[0]}.raw.h>

  3. Use in benchmark:
       DataStream stream(benchmark::data::{os.path.splitext(os.path.basename(args.out))[0].replace('.', '_')});
""")
