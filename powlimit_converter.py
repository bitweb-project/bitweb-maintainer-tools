#!/usr/bin/env python3
"""
Bitcoin / Altcoin  powLimit converter
======================================
Converts between two PoW target formats:

  compact  (nBits)  — 32-bit value, e.g. 0x1d00ffff
  uint256  (hex)    — 64-char hex string, e.g.
                      "00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

Algorithm taken directly from Bitcoin Core:
  src/arith_uint256.cpp  ->  SetCompact / GetCompact

Standalone — no external dependencies required.
"""

# ─────────────────────────────────────────────────────────────────────────────
#  Core conversion (exact mirror of Bitcoin Core arith_uint256.cpp)
# ─────────────────────────────────────────────────────────────────────────────

def compact_to_uint256(nbits: int) -> int:
    """
    SetCompact: compact (nBits) -> big integer (uint256).

    Formula: N = mantissa * 256^(exponent - 3)
      - high 8 bits  = exponent  (byte length of the number)
      - bits 0-22    = mantissa  (significant bytes)
      - bit 23 (0x800000) = sign flag (always 0 for PoW targets)
    """
    n_size = nbits >> 24
    n_word = nbits & 0x007fffff

    if n_size <= 3:
        n_word >>= 8 * (3 - n_size)
        result = n_word
    else:
        result = n_word << (8 * (n_size - 3))

    # Negative values and overflow are invalid for PoW — return 0
    negative = (n_word != 0) and bool(nbits & 0x00800000)
    overflow = (n_word != 0) and (
        (n_size > 34) or
        (n_word > 0xff   and n_size > 33) or
        (n_word > 0xffff and n_size > 32)
    )
    if negative or overflow:
        return 0
    return result


def uint256_to_compact(target: int) -> int:
    """
    GetCompact: big integer (uint256) -> compact (nBits).

    Finds the minimum number of bytes to store the value,
    takes the top 3 bytes as the mantissa.
    If the top bit of the mantissa is set (sign bit),
    shifts right by 1 byte and increments the exponent.
    """
    # Count significant bytes
    n_size = (target.bit_length() + 7) // 8

    if n_size <= 3:
        n_word = target << (8 * (3 - n_size))
    else:
        n_word = target >> (8 * (n_size - 3))

    # If bit 0x800000 is set, shift to avoid sign-bit misinterpretation
    if n_word & 0x800000:
        n_word >>= 8
        n_size  += 1

    return (n_size << 24) | (n_word & 0x007fffff)


# ─────────────────────────────────────────────────────────────────────────────
#  Helper formatting functions
# ─────────────────────────────────────────────────────────────────────────────

def uint256_to_hex(value: int) -> str:
    """int -> 64-char hex string (no 0x prefix)."""
    return format(value, '064x')

def hex_to_uint256(hex_str: str) -> int:
    """hex string -> int."""
    return int(hex_str.strip().lstrip('0x').lstrip('0X') or '0', 16)

def difficulty(target: int, genesis_target: int = None) -> float:
    """
    Difficulty relative to genesis_target.
    Defaults to mainnet difficulty-1 target.
    """
    if genesis_target is None:
        genesis_target = compact_to_uint256(0x1d00ffff)
    if target == 0:
        return float('inf')
    return genesis_target / target


# ─────────────────────────────────────────────────────────────────────────────
#  Pretty-print a single target
# ─────────────────────────────────────────────────────────────────────────────

def print_target_info(label, nbits, genesis_nbits=None):
    target = compact_to_uint256(nbits)
    hex64  = uint256_to_hex(target)
    genesis_target = compact_to_uint256(genesis_nbits) if genesis_nbits else None
    diff   = difficulty(target, genesis_target)

    print(f"\n{'─'*60}")
    print(f"  {label}")
    print(f"{'─'*60}")
    print(f"  compact (nBits)  : 0x{nbits:08x}  ({nbits})")
    print(f"  uint256 (hex)    : {hex64}")
    print(f"  uint256S(\"{hex64}\")")
    print(f"  integer value    : {target}")
    print(f"  leading zeros    : {len(hex64) - len(hex64.lstrip('0'))} chars")
    if genesis_nbits:
        print(f"  difficulty       : {diff:,.6f}  (relative to 0x{genesis_nbits:08x})")
    print(f"{'─'*60}")


# ─────────────────────────────────────────────────────────────────────────────
#  Interactive mode
# ─────────────────────────────────────────────────────────────────────────────

def interactive():
    print("\n" + "="*60)
    print("   powLimit converter  (Bitcoin compact <-> uint256)")
    print("="*60)
    print("  1  compact -> uint256    (0x1d00ffff -> hex string)")
    print("  2  uint256 -> compact    (hex string -> 0x1d00ffff)")
    print("  3  exit")
    print("="*60)

    while True:
        choice = input("\nSelect mode [1/2/3]: ").strip()

        if choice == '1':
            raw = input("  compact nBits (e.g. 0x1d00ffff or 486604799): ").strip()
            try:
                nbits = int(raw, 0)   # handles 0x prefix and decimal
            except ValueError:
                print("  x Invalid number format")
                continue
            target = compact_to_uint256(nbits)
            hex64  = uint256_to_hex(target)
            print(f"\n  -> uint256 hex  : {hex64}")
            print(f"  -> uint256S(\"{hex64}\")")
            print(f"  -> integer      : {target}")

        elif choice == '2':
            raw = input("  uint256 hex string (64 chars): ").strip()
            try:
                target = int(raw.lstrip('0x').lstrip('0X') or '0', 16)
            except ValueError:
                print("  x Invalid hex")
                continue
            nbits = uint256_to_compact(target)
            print(f"\n  -> compact nBits : 0x{nbits:08x}")
            print(f"  -> decimal       : {nbits}")
            print(f"  consensus.powLimit = uint256S(\"{uint256_to_hex(target)}\");")
            print(f"  // genesis nBits: 0x{nbits:08x}")

        elif choice == '3':
            break
        else:
            print("  Enter 1, 2 or 3")


# ─────────────────────────────────────────────────────────────────────────────
#  Built-in demo examples
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    print("\n" + "="*60)
    print("  BUILT-IN EXAMPLES")
    print("="*60)

    # Example 1: Bitcoin mainnet difficulty-1
    nbits_mainnet = 0x1d00ffff
    print_target_info("Bitcoin mainnet  (difficulty-1)", nbits_mainnet)

    # Example 2: regtest / very easy target
    nbits_regtest = 0x207fffff
    print_target_info("Bitcoin regtest", nbits_regtest, genesis_nbits=nbits_mainnet)

    # Example 3: custom powLimit
    custom_hex = "001fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    custom_target = hex_to_uint256(custom_hex)
    custom_nbits  = uint256_to_compact(custom_target)
    print_target_info(
        f"Custom powLimit  ({custom_hex[:16]}...)",
        custom_nbits,
        genesis_nbits=nbits_mainnet
    )
    # Verify round-trip
    back_hex = uint256_to_hex(compact_to_uint256(custom_nbits))
    print(f"  Round-trip check : {back_hex}")
    print(f"  {'OK - match' if back_hex == custom_hex else 'NOTE: compact is lossy (only top 3 bytes stored)'}")

    # Example 4: round-trip test
    print("\n" + "="*60)
    print("  ROUND-TRIP TEST")
    print("="*60)
    test_cases = [
        ("00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "mainnet"),
        ("001fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "custom"),
        ("00000000000005a2d4000000000000000000000000000000000000000000000000"[:64], "very hard"),
    ]
    for hex_str, name in test_cases:
        t  = hex_to_uint256(hex_str)
        nb = uint256_to_compact(t)
        t2 = compact_to_uint256(nb)
        h2 = uint256_to_hex(t2)
        ok = "OK" if h2 == hex_str else "lossy (expected — compact stores top 3 bytes only)"
        print(f"  {name:15s}: 0x{nb:08x}  {ok}")

    # Interactive mode
    print()
    try:
        interactive()
    except (KeyboardInterrupt, EOFError):
        print("\n  Exit.")
