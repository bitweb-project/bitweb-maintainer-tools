#!/usr/bin/env python3
"""
snapshot.py — final balances via RPC (batch mode)
Supports all script types: P2PK, P2PKH, P2SH, P2WPKH, P2WSH, P2TR
Output format: address:satoshis
"""

import json
import time
import hashlib
from urllib.request import urlopen, Request
from base64 import b64encode

# ════════════════════════════════════════════════
#  SETTINGS
# ════════════════════════════════════════════════

RPC_HOST = "127.0.0.1"
RPC_PORT = 8332
RPC_USER = "userbitweb"
RPC_PASS = "userbitweb1"

OUT_TXT  = "snapshot.txt"
OUT_JSON = "snapshot.json"

VALIDATION_BLOCKS = 1000
PROGRESS_EVERY    = 50_000
BATCH_SIZE        = 1000

# Bitweb prefix for P2PK → P2PKH address
PUBKEY_ADDRESS_VERSION = 33   # base58Prefixes[PUBKEY_ADDRESS] = {33} → 'E...'

# ════════════════════════════════════════════════
#  BASE58CHECK for P2PK → address
# ════════════════════════════════════════════════

BASE58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    result = ""
    while n:
        n, rem = divmod(n, 58)
        result = BASE58_CHARS[rem] + result
    for b in data:
        if b == 0:
            result = BASE58_CHARS[0] + result
        else:
            break
    return result

def _hash160(data: bytes) -> bytes:
    h = hashlib.new("sha256", data).digest()
    return hashlib.new("ripemd160", h).digest()

def _checksum(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]

def pubkey_to_address(pubkey_hex: str) -> str:
    """P2PK pubkey → Bitweb P2PKH address with version byte 33."""
    pubkey  = bytes.fromhex(pubkey_hex)
    h160    = _hash160(pubkey)
    payload = bytes([PUBKEY_ADDRESS_VERSION]) + h160
    return _b58encode(payload + _checksum(payload))

# ════════════════════════════════════════════════
#  ADDRESS EXTRACTION FROM SCRIPTPUBKEY
# ════════════════════════════════════════════════

def extract_address(spk: dict):
    """
    Returns the address from a scriptPubKey of any type.
    The node decodes P2PKH / P2SH / P2WPKH / P2WSH / P2TR itself —
    they arrive in the 'address' field already with correct Bitweb prefixes.
    P2PK is the only type where the node does not return an address;
    we decode it manually from the pubkey.
    """
    # P2PKH, P2SH, P2WPKH, P2WSH, P2TR — node decodes these itself
    addr = spk.get("address")
    if addr:
        return addr

    # Old Bitcoin Core < 22 format
    addrs = spk.get("addresses")
    if addrs:
        return addrs[0]

    # P2PK: asm = "<pubkey> OP_CHECKSIG"
    if spk.get("type") == "pubkey":
        asm   = spk.get("asm", "")
        parts = asm.split()
        if len(parts) >= 2 and parts[-1] == "OP_CHECKSIG":
            pubkey_hex = parts[0]
            if len(pubkey_hex) in (66, 130):  # compressed or uncompressed
                return pubkey_to_address(pubkey_hex)

    return None

# ════════════════════════════════════════════════
#  RPC
# ════════════════════════════════════════════════

class RPC:
    def __init__(self):
        auth = b64encode(f"{RPC_USER}:{RPC_PASS}".encode()).decode()
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
        }
        self.url = f"http://{RPC_HOST}:{RPC_PORT}/"
        self._id = 0

    def __call__(self, method, *params):
        self._id += 1
        body = json.dumps({
            "jsonrpc": "1.1", "id": self._id,
            "method": method, "params": list(params),
        }).encode()
        req = Request(self.url, data=body, headers=self.headers)
        with urlopen(req, timeout=300) as r:
            res = json.loads(r.read())
        if res.get("error"):
            raise RuntimeError(res["error"])
        return res["result"]

    def batch(self, calls):
        payload = []
        for method, params in calls:
            self._id += 1
            payload.append({
                "jsonrpc": "1.1", "id": self._id,
                "method": method, "params": params,
            })
        body = json.dumps(payload).encode()
        req  = Request(self.url, data=body, headers=self.headers)
        with urlopen(req, timeout=300) as r:
            results = json.loads(r.read())
        results.sort(key=lambda x: x["id"])
        for r in results:
            if r.get("error"):
                raise RuntimeError(r["error"])
        return [r["result"] for r in results]


def to_satoshis(value):
    return int(round(value * 1e8))

# ════════════════════════════════════════════════
#  BLOCK SCANNING
# ════════════════════════════════════════════════

def process_blocks(rpc, from_height, to_height, label="", print_every=PROGRESS_EVERY):
    utxo               = {}
    skipped_op_return  = 0
    skipped_other      = 0
    t0                 = time.time()
    total              = to_height - from_height + 1

    height = from_height
    while height <= to_height:
        chunk_end     = min(height + BATCH_SIZE - 1, to_height)
        chunk_heights = list(range(height, chunk_end + 1))

        hashes = rpc.batch([("getblockhash", [h]) for h in chunk_heights])
        blocks = rpc.batch([("getblock", [bh, 2]) for bh in hashes])

        for block in blocks:
            for tx in block["tx"]:
                txid = tx["txid"]

                # Remove spent UTXOs
                for vin in tx.get("vin", []):
                    if "txid" in vin:
                        utxo.pop((vin["txid"], vin["vout"]), None)

                # Add new UTXOs
                for vout in tx.get("vout", []):
                    spk      = vout.get("scriptPubKey", {})
                    satoshis = to_satoshis(vout.get("value", 0))

                    if satoshis <= 0:
                        continue

                    if spk.get("type") == "nulldata":
                        skipped_op_return += 1
                        continue

                    address = extract_address(spk)
                    if address:
                        utxo[(txid, vout["n"])] = (address, satoshis)
                    else:
                        skipped_other += 1

        done    = chunk_end - from_height + 1
        elapsed = time.time() - t0
        rate    = done / max(elapsed, 1)
        left    = (total - done) / max(rate, 0.001)

        if done % print_every < BATCH_SIZE or chunk_end == to_height:
            print(
                f"  {label}block {chunk_end:>9,} / {to_height:,} | "
                f"{rate:>7.0f} blocks/s | "
                f"~{left/60:.1f} min | "
                f"UTXOs: {len(utxo):,}"
            )

        height = chunk_end + 1

    if skipped_other:
        print(f"  [i] Skipped nonstandard/bare-multisig: {skipped_other:,}")
    print(f"  [i] Skipped OP_RETURN (expected): {skipped_op_return:,}")

    return utxo


def aggregate(utxo):
    balances = {}
    for (address, satoshis) in utxo.values():
        balances[address] = balances.get(address, 0) + satoshis
    return balances


def print_sample(balances, n=10):
    items = sorted(balances.items(), key=lambda x: -x[1])[:n]
    print(f"\n  {'Address':<52} {'Satoshis':>20}  {'Coins':>18}")
    print(f"  {'-'*52} {'-'*20}  {'-'*18}")
    for addr, sat in items:
        print(f"  {addr:<52} {sat:>20,}  {sat/1e8:>18.8f}")


def print_supply_banner(total_sat, addr_count):
    coins = total_sat / 1e8
    print(f"""
╔══════════════════════════════════════════════════════╗
  FINAL SUPPLY — verify against explorer
  ─────────────────────────────────────────────────────
  Addresses with balance :  {addr_count:>15,}
  Total supply (satoshis):  {total_sat:>20,}
  Total supply (coins)   :  {coins:>20.8f}
╚══════════════════════════════════════════════════════╝""")

# ════════════════════════════════════════════════
#  GENESIS DIAGNOSTICS
# ════════════════════════════════════════════════

def diagnose_genesis(rpc):
    bh    = rpc("getblockhash", 0)
    block = rpc("getblock", bh, 2)
    print(f"\n  Genesis block (block 0):")
    for tx in block["tx"]:
        for vout in tx.get("vout", []):
            spk  = vout["scriptPubKey"]
            addr = extract_address(spk)
            print(f"    vout[{vout['n']}]  value={vout['value']}  type={spk.get('type','?')}")
            print(f"           → address = {addr}")

# ════════════════════════════════════════════════
#  PHASE 1 — VALIDATION
# ════════════════════════════════════════════════

def run_validation(rpc, tip):
    limit = min(VALIDATION_BLOCKS, tip)

    print(f"\n{'='*60}")
    print(f"  PHASE 1: Validation — blocks 0..{limit}")
    print(f"{'='*60}")

    diagnose_genesis(rpc)

    utxo     = process_blocks(rpc, 0, limit, label="[val] ", print_every=100)
    balances = aggregate(utxo)

    total_sat  = sum(balances.values())
    addr_count = len(balances)

    print(f"\n  Result:")
    print(f"  ├─ Blocks       : {limit + 1:,}")
    print(f"  ├─ Addresses    : {addr_count:,}")
    print(f"  ├─ UTXO entries : {len(utxo):,}")
    print(f"  └─ Total        : {total_sat:,} sat  ({total_sat/1e8:.8f} coins)")

    if addr_count == 0:
        print("\n  [!] ERROR: no addresses found even in the first blocks!")
        return False

    print(f"\n  Top-10 (from first {limit+1} blocks):")
    print_sample(balances)

    return True

# ════════════════════════════════════════════════
#  PHASE 2 — FULL SCAN
# ════════════════════════════════════════════════

def run_full_scan(rpc, tip, tip_hash, snap_time):
    print(f"\n{'='*60}")
    print(f"  PHASE 2: Full scan — blocks 0..{tip:,}")
    print(f"{'='*60}\n")

    t_start  = time.time()
    utxo     = process_blocks(rpc, 0, tip, label="", print_every=PROGRESS_EVERY)
    balances = aggregate(utxo)
    balances = dict(sorted(balances.items(), key=lambda x: -x[1]))

    total_sat  = sum(balances.values())
    addr_count = len(balances)
    elapsed    = time.time() - t_start

    print(f"\n  Scan completed in {elapsed/60:.1f} min  ({elapsed/3600:.2f} h)")
    print(f"\n  Top-10 of final snapshot:")
    print_sample(balances)
    print_supply_banner(total_sat, addr_count)

    with open(OUT_TXT, "w") as f:
        for addr, sat in balances.items():
            f.write(f"{addr}:{sat}\n")
    print(f"\n[✓] {OUT_TXT}  ({addr_count:,} lines)")

    with open(OUT_JSON, "w") as f:
        json.dump({
            "meta": {
                "block_height"   : tip,
                "block_hash"     : tip_hash,
                "snapshot_time"  : snap_time,
                "denomination"   : 1,
                "total_satoshis" : total_sat,
                "total_coins"    : total_sat / 1e8,
                "address_count"  : addr_count,
                "scan_minutes"   : round(elapsed / 60, 1),
            },
            "balances": balances,
        }, f, indent=2)
    print(f"[✓] {OUT_JSON}")
    print(f"\nDone.")

# ════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════

def main():
    rpc = RPC()

    tip       = rpc("getblockcount")
    tip_hash  = rpc("getblockhash", tip)
    snap_time = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    print(f"\n╔══════════════════════════════════════════════════════════╗")
    print(f"  Balance Snapshot — Bitweb")
    print(f"  Block     : {tip:,}")
    print(f"  Hash      : {tip_hash}")
    print(f"  Time      : {snap_time}")
    print(f"  Batch     : {BATCH_SIZE} blocks/request")
    print(f"  Formats   : P2PK / P2PKH / P2SH / P2WPKH / P2WSH / P2TR")
    print(f"  Output    : address:satoshis  (no denomination)")
    print(f"╚══════════════════════════════════════════════════════════╝")

    ok = run_validation(rpc, tip)
    if not ok:
        print("\n[!] Validation failed. Stopping.")
        return

    print(f"\n{'─'*60}")
    print(f"  Validation OK. Run full scan of {tip:,} blocks?")
    print(f"{'─'*60}")
    ans = input("  Type 'yes' to start: ").strip().lower()
    if ans != "yes":
        print("  Cancelled.")
        return

    run_full_scan(rpc, tip, tip_hash, snap_time)


if __name__ == "__main__":
    main()
