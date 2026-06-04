#!/usr/bin/env python3
"""
feature_signet_get_blocks.py  —  run from ~/bitweb/

Generates signet keys, mines test blocks, and prints everything needed to
update chainparams.cpp and feature_signet.py.

Usage:
  python3 feature_signet_get_blocks.py                         # generate new keys + mine
  python3 feature_signet_get_blocks.py --challenge HEX --descriptor DESC  # reuse existing keys, re-mine
  python3 feature_signet_get_blocks.py --challenge HEX --descriptor DESC --address ADDR

Options:
  --challenge  HEX    Existing signetchallenge hex (skips regtest key generation)
  --descriptor DESC   Existing multi(1,...) descriptor with checksum (required with --challenge)
  --address    ADDR   Miner reward address (optional; derived from descriptor wallet if omitted)
  --help, -h          Show this help message
"""

import argparse, subprocess, json, time, os, re, sys, shutil, hashlib

# ── Config ───────────────────────────────────────────────────────────────────
BITWEB_DIR     = os.path.expanduser("~/bitweb")
CLI            = f"{BITWEB_DIR}/build/bin/bitweb-cli"
DAEMON         = f"{BITWEB_DIR}/build/bin/bitwebd"
UTIL           = f"{BITWEB_DIR}/build/bin/bitweb-util"
MINER          = f"{BITWEB_DIR}/contrib/signet/miner"

KEYGEN_DIR     = "/tmp/bw_keygen"
SIGNET_DIR     = "/tmp/bw_signet"

NBITS          = "1f036fb2"
MAX_BLOCKS     = 15
COLLECT_BLOCKS = 10
# ─────────────────────────────────────────────────────────────────────────────


# ── CLI args ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(
    prog="signettestgen.py",
    description=(
        "Generate signet keys and mine test blocks for Bitweb.\n\n"
        "Without --challenge: generates a fresh key pair via a temporary regtest node.\n"
        "With --challenge + --descriptor: skips key generation and reuses existing values\n"
        "  (useful when the challenge is unchanged and only test blocks need to be regenerated)."
    ),
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=(
        "Examples:\n"
        "  python3 signettestgen.py\n"
        "  python3 signettestgen.py \\\n"
        "    --challenge 512103...51ae \\\n"
        "    --descriptor 'multi(1,tprv.../84h/1h/0h/0/0)#xxxxxxxx'\n"
        "  python3 signettestgen.py \\\n"
        "    --challenge 512103...51ae \\\n"
        "    --descriptor 'multi(1,tprv.../84h/1h/0h/0/0)#xxxxxxxx' \\\n"
        "    --address tb1q...\n"
    ),
)
parser.add_argument(
    "--challenge",
    metavar="HEX",
    help="Existing signetchallenge (e.g. 5121<pubkey>51ae). Skips regtest key generation.",
)
parser.add_argument(
    "--descriptor",
    metavar="DESC",
    help="Existing multi(1,...) descriptor with checksum. Required when --challenge is set.",
)
parser.add_argument(
    "--address",
    metavar="ADDR",
    help=(
        "Miner reward address. If omitted, a new address is derived from the miner wallet "
        "(using the imported descriptor key)."
    ),
)
args = parser.parse_args()

# Validate combinations
if args.challenge and not args.descriptor:
    parser.error("--descriptor is required when --challenge is provided")
if args.descriptor and not args.challenge:
    parser.error("--challenge is required when --descriptor is provided")
# ─────────────────────────────────────────────────────────────────────────────


def run(*cmd, check=True, stream=False):
    cmd = [str(c) for c in cmd]
    if stream:
        r = subprocess.run(cmd)
        if check and r.returncode != 0:
            print(f"FAIL: {' '.join(cmd)}", file=sys.stderr)
            sys.exit(1)
        return ""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"FAIL: {' '.join(cmd)}", file=sys.stderr)
        print(r.stderr.strip(), file=sys.stderr)
        sys.exit(1)
    return r.stdout.strip()


def rpc(datadir, chain, *args, wallet=None, check=True):
    base = [CLI, f"-{chain}", f"-datadir={datadir}"]
    if wallet:
        base += [f"-rpcwallet={wallet}"]
    return run(*base, *args, check=check)


def wait_rpc(datadir, chain, timeout=60):
    print(f"  Waiting for node ({chain})...", end="", flush=True)
    for _ in range(timeout):
        r = subprocess.run(
            [CLI, f"-{chain}", f"-datadir={datadir}", "getblockcount"],
            capture_output=True
        )
        if r.returncode == 0:
            print(" ready")
            return
        time.sleep(1)
        print(".", end="", flush=True)
    print("\nTimeout!", file=sys.stderr)
    sys.exit(1)


def cleanup(*dirs):
    for d in dirs:
        if os.path.exists(d):
            shutil.rmtree(d)


def varint(n: int) -> bytes:
    """Bitcoin compact-size integer encoding."""
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return b'\xfd' + n.to_bytes(2, 'little')
    elif n <= 0xffffffff:
        return b'\xfe' + n.to_bytes(4, 'little')
    else:
        return b'\xff' + n.to_bytes(8, 'little')


def compute_magic(challenge_hex: str) -> bytes:
    """
    Compute pchMessageStart (network magic) from signet challenge.
    Mirrors chainparams.cpp:
        HashWriter h{};
        h << consensus.signet_challenge;   // Bitcoin vector serialization: varint(len) + bytes
        uint256 hash = h.GetHash();        // double-SHA256
        std::copy_n(hash.begin(), 4, pchMessageStart.begin());
    """
    raw = bytes.fromhex(challenge_hex)
    serialized = varint(len(raw)) + raw
    digest = hashlib.sha256(hashlib.sha256(serialized).digest()).digest()
    return digest[:4]


def pubkey_from_challenge(challenge_hex: str) -> str:
    """Extract the 33-byte compressed pubkey from a 1-of-1 multisig challenge (5121<pubkey>51ae)."""
    # 5121 = OP_1 OP_PUSHBYTES_33, 51ae = OP_1 OP_CHECKMULTISIG
    if challenge_hex.startswith("5121") and challenge_hex.endswith("51ae"):
        return challenge_hex[4:-4]
    return "<unknown>"


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — Key generation (skipped if --challenge provided)
# ═══════════════════════════════════════════════════════════════════════════
if args.challenge:
    print("\n=== Step 1: Using existing keys (skipping regtest) ===")
    challenge  = args.challenge
    multi_desc = args.descriptor
    pubkey     = pubkey_from_challenge(challenge)
    print(f"  pubkey:          {pubkey}")
    print(f"  signetchallenge: {challenge}")
    print(f"  descriptor:      {multi_desc}")
else:
    print("\n=== Step 1: Key generation (regtest) ===")

    cleanup(KEYGEN_DIR, SIGNET_DIR)
    os.makedirs(KEYGEN_DIR)
    os.makedirs(SIGNET_DIR)

    run(DAEMON, "-regtest", f"-datadir={KEYGEN_DIR}", "-daemon")
    wait_rpc(KEYGEN_DIR, "regtest")

    rpc(KEYGEN_DIR, "regtest", "createwallet", "keygen")

    # Get address and pubkey
    addr_k = rpc(KEYGEN_DIR, "regtest", "getnewaddress", "", "bech32", wallet="keygen")
    info   = json.loads(rpc(KEYGEN_DIR, "regtest", "getaddressinfo", addr_k, wallet="keygen"))
    pubkey = info["pubkey"]

    # Build 1-of-1 multisig signetchallenge
    challenge = f"5121{pubkey}51ae"

    # Find the wpkh external descriptor with xprv (path 84h/.../0/*)
    descs_raw = json.loads(rpc(KEYGEN_DIR, "regtest", "listdescriptors", "true", wallet="keygen"))
    wpkh_desc_str = None
    for d in descs_raw["descriptors"]:
        desc = d["desc"]
        if desc.startswith("wpkh(") and "84h" in desc and not d.get("internal", False):
            wpkh_desc_str = desc
            break

    if not wpkh_desc_str:
        print("wpkh descriptor with 84h not found!", file=sys.stderr)
        sys.exit(1)

    # Extract xprv path: wpkh(XPRV/84h/.../0/*)#cs -> XPRV/84h/.../0/0
    inner        = re.match(r"wpkh\((.+)\)#\w+$", wpkh_desc_str).group(1)
    inner_single = re.sub(r"/0/\*$", "/0/0", inner)

    # Build multi(1,xprv.../0/0) and get its checksum.
    # IMPORTANT: getdescriptorinfo returns two separate fields:
    #   "descriptor" = canonical form WITHOUT private keys (xprv -> xpub) — DO NOT USE THIS
    #   "checksum"   = checksum for the INPUT descriptor (with xprv)      — USE THIS
    multi_raw  = f"multi(1,{inner_single})"
    desc_info  = json.loads(rpc(KEYGEN_DIR, "regtest", "getdescriptorinfo", multi_raw))
    checksum   = desc_info["checksum"]
    multi_desc = f"{multi_raw}#{checksum}"

    # Stop regtest node
    rpc(KEYGEN_DIR, "regtest", "stop")
    time.sleep(3)
    shutil.rmtree(KEYGEN_DIR)

    print(f"  pubkey:          {pubkey}")
    print(f"  signetchallenge: {challenge}")
    print(f"  import_desc:     {multi_desc}")

# Compute network magic (always, from whichever challenge we have)
magic_bytes = compute_magic(challenge)
magic_hex   = magic_bytes.hex()
magic_cpp   = "{" + ", ".join(f"0x{b:02X}" for b in magic_bytes) + "}"
print(f"  magic:           {magic_hex}  ->  {magic_cpp}")

if not args.challenge:
    os.makedirs(SIGNET_DIR, exist_ok=True)
else:
    cleanup(SIGNET_DIR)
    os.makedirs(SIGNET_DIR)


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — Signet node
# ═══════════════════════════════════════════════════════════════════════════
print("\n=== Step 2: Signet node ===")

run(DAEMON,
    "-signet",
    f"-signetchallenge={challenge}",
    f"-datadir={SIGNET_DIR}",
    "-daemon",
    "-fallbackfee=0.0001")
wait_rpc(SIGNET_DIR, "signet")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — Miner wallet
# ═══════════════════════════════════════════════════════════════════════════
print("\n=== Step 3: Miner wallet ===")

rpc(SIGNET_DIR, "signet", "createwallet", "miner")

import_payload = json.dumps([{"desc": multi_desc, "timestamp": "now"}])
result = json.loads(rpc(SIGNET_DIR, "signet", "importdescriptors", import_payload, wallet="miner"))
if not result[0].get("success"):
    print(f"importdescriptors failed: {result}", file=sys.stderr)
    sys.exit(1)

# Miner address: use provided --address, or derive from wallet (same key as descriptor)
if args.address:
    miner_addr = args.address
    print(f"  miner_addr: {miner_addr}  (from --address)")
else:
    miner_addr = rpc(SIGNET_DIR, "signet", "getnewaddress", wallet="miner")
    print(f"  miner_addr: {miner_addr}  (derived from descriptor key)")

# Show address info
addr_info = json.loads(rpc(SIGNET_DIR, "signet", "getaddressinfo", miner_addr, wallet="miner"))
print(f"  addr type:  {addr_info.get('type', 'unknown')}")
print(f"  addr desc:  {addr_info.get('desc', 'n/a')}")
is_watchonly = addr_info.get("iswatchonly", False)
is_mine      = addr_info.get("ismine", False)
print(f"  ismine:     {is_mine}   iswatchonly: {is_watchonly}")
if not is_mine and not is_watchonly:
    print("  WARNING: address does not belong to miner wallet — mining rewards may be unspendable",
          file=sys.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — Mining
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n=== Step 4: Mining {MAX_BLOCKS} blocks ===")

cli_str = f"{CLI} -signet -datadir={SIGNET_DIR}"
run("python3", MINER,
    f"--cli={cli_str}",
    "generate",
    f"--address={miner_addr}",
    f"--grind-cmd={UTIL} grind",
    f"--nbits={NBITS}",
    f"--max-blocks={MAX_BLOCKS}",
    stream=True)


# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — Collect block hexes
# ═══════════════════════════════════════════════════════════════════════════
print(f"\n=== Step 5: Collecting {COLLECT_BLOCKS} blocks ===")

block_count = int(rpc(SIGNET_DIR, "signet", "getblockcount"))
print(f"  Total mined: {block_count}")

blocks = []
for h in range(1, COLLECT_BLOCKS + 1):
    bhash = rpc(SIGNET_DIR, "signet", "getblockhash", str(h))
    raw   = rpc(SIGNET_DIR, "signet", "getblock", bhash, "0")
    blocks.append(raw)
    print(f"  block {h}: {raw[:32]}...")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 6 — Stop and cleanup
# ═══════════════════════════════════════════════════════════════════════════
print("\n=== Step 6: Shutdown ===")
rpc(SIGNET_DIR, "signet", "stop")
time.sleep(3)
shutil.rmtree(SIGNET_DIR)
print("  Temp dirs removed")


# ═══════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════
sep = "=" * 70
print(f"\n{sep}")
print("REPORT")
print(sep)

print("\n--- 1. chainparams.cpp / -signetchallenge= ---")
print(f"  {challenge}")

print("\n--- 2. Network magic (pchMessageStart) ---")
print(f"  hex: {magic_hex}")
print(f"  C++: pchMessageStart = {magic_cpp};")

print("\n--- 3. Miner address ---")
print(f"  {miner_addr}")

print("\n--- 4. importdescriptors (miner wallet, save this) ---")
print(json.dumps([{"desc": multi_desc, "timestamp": "now"}], indent=2))

print("\n--- 5. feature_signet.py — replace old values with these ---")
print(f"\nSIGNET_DEFAULT_CHALLENGE = '{challenge}'\n")
print("signet_blocks = [")
for b in blocks:
    print(f"    '{b}',")
print("]")

print(f"\n{sep}")
print("Done.")
