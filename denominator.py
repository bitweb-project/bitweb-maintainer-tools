#!/usr/bin/env python3
"""
denominator.py — 1:100 denomination with dust rounding up to 10000 sat
Input:  snapshot.txt  (address:satoshis)
Output: airdrop.txt   (address:satoshis_after_denomination)
"""

import math

# ════════════════════════════════════════════════
#  SETTINGS
# ════════════════════════════════════════════════

IN_FILE      = "snapshot.txt"
OUT_FILE     = "airdrop.txt"
DENOM        = 100        # 1:100
DUST_MIN     = 10_000     # anything below → raise to this value

# ════════════════════════════════════════════════

def main():
    print(f"\n╔══════════════════════════════════════════════════════════╗")
    print(f"  Denominator 1:{DENOM}")
    print(f"  Input  : {IN_FILE}")
    print(f"  Output : {OUT_FILE}")
    print(f"  Dust   : < {DUST_MIN:,} sat → raise to {DUST_MIN:,}")
    print(f"╚══════════════════════════════════════════════════════════╝\n")

    entries = []
    with open(IN_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            addr, sat_str = line.rsplit(":", 1)
            entries.append((addr, int(sat_str)))

    print(f"  Addresses loaded: {len(entries):,}")

    total_before    = sum(s for _, s in entries)
    total_after     = 0
    boosted_count   = 0
    boosted_extra   = 0   # how many satoshis were added to dust addresses

    result = []
    for addr, sat_old in entries:
        # Denomination with ceiling rounding
        sat_new = math.ceil(sat_old / DENOM)

        # Dust boost
        if sat_new < DUST_MIN:
            boosted_count += 1
            boosted_extra += DUST_MIN - sat_new
            sat_new = DUST_MIN

        total_after += sat_new
        result.append((addr, sat_new))

    # Sort descending
    result.sort(key=lambda x: -x[1])

    # Write output
    with open(OUT_FILE, "w") as f:
        for addr, sat in result:
            f.write(f"{addr}:{sat}\n")

    # ── Report ───────────────────────────────────
    print(f"\n  {'─'*54}")
    print(f"  Addresses in airdrop         : {len(result):>15,}")
    print(f"  {'─'*54}")
    print(f"  Supply before denomination   : {total_before:>20,} sat")
    print(f"  Supply after denomination    : {total_after:>20,} sat")
    print(f"  {'─'*54}")
    print(f"  Addresses boosted to {DUST_MIN:,} : {boosted_count:>15,}")
    print(f"  Satoshis added to them       : {boosted_extra:>20,}")
    print(f"  Coins added to them          : {boosted_extra/1e8:>20.8f}")
    print(f"  {'─'*54}")

    # Top-10
    print(f"\n  Top-10 after denomination:")
    print(f"  {'Address':<52} {'Satoshis':>15}  {'Coins':>16}")
    print(f"  {'-'*52} {'-'*15}  {'-'*16}")
    for addr, sat in result[:10]:
        print(f"  {addr:<52} {sat:>15,}  {sat/1e8:>16.8f}")

    print(f"""
╔══════════════════════════════════════════════════════╗
  FINAL AIRDROP SUPPLY
  ─────────────────────────────────────────────────────
  Total addresses     :  {len(result):>15,}
  Total supply (sat)  :  {total_after:>20,}
  Total supply (coins):  {total_after/1e8:>20.8f}
╚══════════════════════════════════════════════════════╝""")

    print(f"[✓] {OUT_FILE}  ({len(result):,} lines)")
    print(f"\nDone.")


if __name__ == "__main__":
    main()
