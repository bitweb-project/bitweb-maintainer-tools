#!/usr/bin/env python3
"""
Block Reward & Supply Calculator
Uses integer right-shift (>>) to match Bitcoin's C++ implementation exactly.
"""

# =============================================================================
# PARAMETERS — edit here
# =============================================================================

HALVING_INTERVAL    = 150   # blocks per halving  (BTC: 210000 | Bitweb: 420000)
INITIAL_REWARD      = 50        # coins at genesis     (BTC: 50    | Bitweb: 50)
MAX_HALVINGS        = 64        # safety cap           (same everywhere)

# Premine: set PREMINE_BLOCK = None to disable entirely
PREMINE_BLOCK       = None      # block height of premine  (e.g. 3)
PREMINE_AMOUNT      = 0         # total coins at that block (e.g. 4_000_050)

# =============================================================================

COIN = 100_000_000  # satoshis per coin


def get_block_subsidy(height: int) -> int:
    """Mirrors GetBlockSubsidy() in C++ exactly."""
    halvings = height // HALVING_INTERVAL
    if halvings >= MAX_HALVINGS:
        return 0
    reward = (INITIAL_REWARD * COIN) >> halvings
    if PREMINE_BLOCK is not None and height == PREMINE_BLOCK:
        reward = PREMINE_AMOUNT * COIN
    return reward


def calculate():
    rows = []
    total_sat = 0

    for period in range(MAX_HALVINGS):
        reward_sat = (INITIAL_REWARD * COIN) >> period
        if reward_sat == 0:
            break
        period_sat = reward_sat * HALVING_INTERVAL
        total_sat += period_sat
        block_start = period * HALVING_INTERVAL
        block_end   = block_start + HALVING_INTERVAL - 1
        rows.append((period + 1, block_start, block_end, reward_sat, period_sat))

    premine_extra_sat = 0
    if PREMINE_BLOCK is not None and PREMINE_AMOUNT > 0:
        normal_sat = (INITIAL_REWARD * COIN)   # halvings == 0 at early block
        premine_extra_sat = (PREMINE_AMOUNT * COIN) - normal_sat
        total_sat += premine_extra_sat

    return rows, total_sat, premine_extra_sat


def print_report():
    rows, total_sat, premine_extra_sat = calculate()

    premine_tag = f"  [premine block {PREMINE_BLOCK}: {PREMINE_AMOUNT:,} coins]" \
                  if PREMINE_BLOCK is not None else ""
    print("=" * 80)
    print(f"  halving_interval={HALVING_INTERVAL:,}  initial_reward={INITIAL_REWARD}{premine_tag}")
    print("=" * 80)
    print(f"  {'#':<6} {'Blocks':<22} {'Reward BTC':<16} {'Reward sat':<16} {'Period supply'}")
    print("-" * 80)
    for period, b_start, b_end, reward_sat, period_sat in rows:
        block_range = f"{b_start:,} – {b_end:,}"
        print(f"  {period:<6} {block_range:<22} {reward_sat/COIN:<16.8f} {reward_sat:<16,} {period_sat/COIN:,.8f}")
    print("=" * 80)

    base_sat = total_sat - premine_extra_sat
    print(f"\n  Base supply:     {base_sat:>24,} sat  =  {base_sat/COIN:.8f} BTC")
    if premine_extra_sat:
        print(f"  Premine extra:   {premine_extra_sat:>24,} sat  =  {premine_extra_sat/COIN:.8f} BTC")
    print(f"  Total supply:    {total_sat:>24,} sat  =  {total_sat/COIN:.8f} BTC")
    print(f"\n  C++ test value (nSum): {total_sat}")
    print()


if __name__ == "__main__":
    print_report()
