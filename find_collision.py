#!/usr/bin/env python3
import sys
sys.path.insert(0, 'test/functional')

from test_framework.blockfilter import bip158_basic_element_hash

genesis_blockhash = "fff478736711da54031b170a3a95739bb06bd0f66518eb82876d1a4b39a261b6"
genesis_coinbase_spk = bytes.fromhex("4104678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5fac")

target_hash = bip158_basic_element_hash(genesis_coinbase_spk, 1, genesis_blockhash)
print(f"target_hash = {target_hash}")

for suffix in range(0x1000000):
    candidate = bytes.fromhex("0014") + suffix.to_bytes(20, 'big')
    if candidate == genesis_coinbase_spk:
        continue
    if bip158_basic_element_hash(candidate, 1, genesis_blockhash) == target_hash:
        print(f'false_positive_spk = bytes.fromhex("{candidate.hex()}")')
        break
