#!/usr/bin/env python3
import json, time, os
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from base64 import b64encode

# ─── Settings ─────────────────────────────────────────────────────────────────
RPC_HOST   = "127.0.0.1"
RPC_PORT   = 8334
RPC_USER   = "userbitweb"
RPC_PASS   = "userbitweb1"

IN_FILE    = "airdrop.txt"        # format: address:satoshis
PROGRESS   = "airdrop_progress.txt"
BATCH_SIZE = 500
POLL_SEC   = 15                   # pause between confirmation checks
FEE_RATE   = 2                    # sat/vB
# ──────────────────────────────────────────────────────────────────────────────

_AUTH = "Basic " + b64encode(f"{RPC_USER}:{RPC_PASS}".encode()).decode()
_URL  = f"http://{RPC_HOST}:{RPC_PORT}/"


def rpc(method, params):
    body = json.dumps({
        "jsonrpc": "1.0", "id": 1,
        "method": method, "params": params
    }).encode()
    req = Request(_URL, data=body,
                  headers={"Content-Type": "text/plain",
                           "Authorization": _AUTH})
    try:
        with urlopen(req, timeout=120) as r:
            data = json.loads(r.read())
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} [{method}]: {e.read().decode()[:300]}")
    if data.get("error"):
        raise RuntimeError(f"RPC error [{method}]: {data['error']}")
    return data["result"]


def sat_to_coin(sat):
    return round(sat / 1e8, 8)


def wait_confirmation(txid):
    """Wait until the transaction has at least 1 confirmation."""
    print(f"    Waiting for confirmation {txid[:16]}...", end="", flush=True)
    while True:
        tx = rpc("gettransaction", [txid])
        if tx["confirmations"] >= 1:
            print(f" ✓  ({tx['confirmations']} conf., block {tx['blockindex'] if 'blockindex' in tx else '?'})")
            return
        time.sleep(POLL_SEC)
        print(".", end="", flush=True)


def load_progress():
    try:
        return int(open(PROGRESS).read().strip())
    except FileNotFoundError:
        return 0


def save_progress(val):
    open(PROGRESS, "w").write(str(val))


def main():
    # ── Read input file ───────────────────────────────────────────────────────
    entries = []
    with open(IN_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            addr, sat_str = line.rsplit(":", 1)
            entries.append((addr.strip(), int(sat_str.strip())))

    batches   = [entries[i:i + BATCH_SIZE] for i in range(0, len(entries), BATCH_SIZE)]
    total_sat = sum(s for _, s in entries)

    print(f"\n  Addresses : {len(entries):,}")
    print(f"  Batches   : {len(batches)}  ({BATCH_SIZE} addresses + remainder {len(entries) % BATCH_SIZE or BATCH_SIZE})")
    print(f"  Coins     : {sat_to_coin(total_sat):.8f}")
    print(f"  Fee       : {FEE_RATE} sat/vB\n")

    # ── Checkpoint ───────────────────────────────────────────────────────────
    start = load_progress()
    if start >= len(batches):
        print("  Everything has already been sent.")
        try: os.remove(PROGRESS)
        except: pass
        return
    if start == 0:
        if input("  Type 'yes' to start: ").strip().lower() != "yes":
            print("  Cancelled.")
            return
    else:
        print(f"  Resuming from batch {start + 1}/{len(batches)}")

    txids = []

    for idx in range(start, len(batches)):
        batch   = batches[idx]
        amounts = {addr: sat_to_coin(sat) for addr, sat in batch}

        print(f"\n  ── Batch {idx + 1}/{len(batches)}  ({len(batch)} addresses) ──")

        try:
            txid = rpc("sendmany", {
                "dummy":    "",
                "amounts":  amounts,
                "fee_rate": FEE_RATE
            })
        except RuntimeError as e:
            # Dump all remaining addresses to file and stop
            failed_file = f"airdrop_failed_batch{idx + 1}.txt"
            remaining   = entries[idx * BATCH_SIZE:]
            with open(failed_file, "w") as ff:
                for addr, sat in remaining:
                    ff.write(f"{addr}:{sat}\n")
            print(f"\n  [ERROR] {e}")
            print(f"  Batch {idx + 1} was not sent.")
            print(f"  Remaining {len(remaining)} addresses → {failed_file}")
            return

        txids.append(txid)
        print(f"    txid : {txid}")

        # Save progress immediately after successful send
        save_progress(idx + 1)

        # Wait for at least 1 confirmation before the next batch
        if idx + 1 < len(batches):
            wait_confirmation(txid)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  Done. {len(txids)} transactions, {sat_to_coin(total_sat):.8f} coins:\n")
    for n, t in enumerate(txids, 1):
        print(f"  {n:>3}. {t}")

    try: os.remove(PROGRESS)
    except: pass


if __name__ == "__main__":
    main()
