#!/usr/bin/env python3
'''
Simple script to check the status of all Bitweb Core DNS seeds.
Seeds are available from https://github.com/bitweb-project/bitweb/blob/master/src/kernel/chainparams.cpp
'''
import subprocess

SEEDS_PER_NETWORK={
    'mainnet': [
        "seed.bitwebcore.net",
        "seed1.bitwebcore.net",
        "seed2.bitwebcore.net",
        "seed3.bitwebcore.net",
        "seed4.bitwebcore.net",
        "seed5.bitwebcore.net",
        "seed6.bitwebcore.net",
        "bitwebseed.dpowcore.org",
        "bitwebseed1.dpowcore.org",
    ],
    'testnet': [
        "testnet3seed.bitwebcore.net",
        "testnet3seed1.bitwebcore.net",
        "testnet3seed2.bitwebcore.net",
        "testnet3seed3.bitwebcore.net",
        "testnet3seed4.bitwebcore.net",
        "testnet3seed5.bitwebcore.net",
        "testnet3seed6.bitwebcore.net",
        "bitwebtest3seed.dpowcore.org",
        "bitwebtest3seed1.dpowcore.org",
    ],
    'testnet4': [
        "testnet4seed.bitwebcore.net",
        "testnet4seed1.bitwebcore.net",
        "testnet4seed2.bitwebcore.net",
        "testnet4seed3.bitwebcore.net",
        "testnet4seed4.bitwebcore.net",
        "testnet4seed5.bitwebcore.net",
        "testnet4seed6.bitwebcore.net",
        "bitwebtest4seed.dpowcore.org",
        "bitwebtest4seed1.dpowcore.org",
    ],
    'signet': [
        "testnet4seed.bitwebcore.net",
        "testnet4seed1.bitwebcore.net",
        "testnet4seed2.bitwebcore.net",
        "testnet4seed3.bitwebcore.net",
        "testnet4seed4.bitwebcore.net",
        "testnet4seed5.bitwebcore.net",
        "testnet4seed6.bitwebcore.net",
        "bitwebtest4seed.dpowcore.org",
        "bitwebtest4seed1.dpowcore.org",
    ],
}

def check_seed(x):
    p = subprocess.run(["host",x], capture_output=True, universal_newlines=True)
    out = p.stdout

    # Parse matching lines
    addresses = []
    for line in out.splitlines():
        if "has address" in line or "has IPv6 address" in line:
            addresses.append(line)

    if addresses:
        print(f"\x1b[94mOK\x1b[0m   {x} ({len(addresses)} results)")
    else:
        print(f"\x1b[91mFAIL\x1b[0m {x}")

if __name__ == '__main__':
    for (network, seeds) in SEEDS_PER_NETWORK.items():
        print(f"\x1b[90m* \x1b[97m{network}\x1b[0m")

        for hostname in seeds:
            check_seed(hostname)

        print()
