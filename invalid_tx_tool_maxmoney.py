#!/usr/bin/env python3
"""
Utility for decoding, modifying and encoding Bitcoin transactions.
Usage:
    python3 tx_tool.py decode <hex>
    python3 tx_tool.py set_output <hex> <vout_index> <amount_satoshis>
"""

import struct
import sys
import json


class ByteReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, n: int) -> bytes:
        chunk = self.data[self.pos:self.pos + n]
        if len(chunk) < n:
            raise ValueError(f"Not enough data: need {n}, remaining {len(self.data) - self.pos}")
        self.pos += n
        return chunk

    def read_varint(self) -> int:
        b = self.read(1)[0]
        if b < 0xfd:
            return b
        elif b == 0xfd:
            return struct.unpack('<H', self.read(2))[0]
        elif b == 0xfe:
            return struct.unpack('<I', self.read(4))[0]
        else:
            return struct.unpack('<Q', self.read(8))[0]

    def remaining(self) -> int:
        return len(self.data) - self.pos


def varint_encode(n: int) -> bytes:
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return b'\xfd' + struct.pack('<H', n)
    elif n <= 0xffffffff:
        return b'\xfe' + struct.pack('<I', n)
    else:
        return b'\xff' + struct.pack('<Q', n)


def decode_tx(hex_str: str) -> dict:
    """Decodes a transaction from hex into a dict."""
    data = bytes.fromhex(hex_str)
    r = ByteReader(data)

    tx = {}

    # Version
    tx['version'] = struct.unpack('<i', r.read(4))[0]

    # Inputs
    vin_count = r.read_varint()
    tx['vin'] = []
    for _ in range(vin_count):
        inp = {}
        inp['txid'] = r.read(32)[::-1].hex()   # reversed (little-endian -> big-endian)
        inp['vout'] = struct.unpack('<I', r.read(4))[0]
        script_len = r.read_varint()
        inp['scriptSig'] = r.read(script_len).hex()
        inp['sequence'] = struct.unpack('<I', r.read(4))[0]
        tx['vin'].append(inp)

    # Outputs
    vout_count = r.read_varint()
    tx['vout'] = []
    for i in range(vout_count):
        out = {}
        out['value_sat'] = struct.unpack('<q', r.read(8))[0]
        out['value_btc'] = out['value_sat'] / 1e8
        script_len = r.read_varint()
        out['scriptPubKey'] = r.read(script_len).hex()
        tx['vout'].append(out)

    # Locktime
    tx['locktime'] = struct.unpack('<I', r.read(4))[0]

    if r.remaining() != 0:
        raise ValueError(f"Trailing data: {r.remaining()} bytes remaining")

    return tx


def encode_tx(tx: dict) -> bytes:
    """Encodes a transaction from a dict into bytes."""
    out = b''

    # Version
    out += struct.pack('<i', tx['version'])

    # Inputs
    out += varint_encode(len(tx['vin']))
    for inp in tx['vin']:
        out += bytes.fromhex(inp['txid'])[::-1]  # big-endian -> little-endian
        out += struct.pack('<I', inp['vout'])
        script = bytes.fromhex(inp['scriptSig'])
        out += varint_encode(len(script))
        out += script
        out += struct.pack('<I', inp['sequence'])

    # Outputs
    out += varint_encode(len(tx['vout']))
    for o in tx['vout']:
        out += struct.pack('<q', o['value_sat'])
        script = bytes.fromhex(o['scriptPubKey'])
        out += varint_encode(len(script))
        out += script

    # Locktime
    out += struct.pack('<I', tx['locktime'])

    return out


def set_output_amount(hex_str: str, vout_index: int, new_amount_sat: int) -> str:
    """Changes the output amount and returns the new hex."""
    tx = decode_tx(hex_str)
    old = tx['vout'][vout_index]['value_sat']
    tx['vout'][vout_index]['value_sat'] = new_amount_sat
    tx['vout'][vout_index]['value_btc'] = new_amount_sat / 1e8
    new_hex = encode_tx(tx).hex()
    print(f"  Output {vout_index}: {old} sat -> {new_amount_sat} sat")
    return new_hex


def print_tx(tx: dict):
    print(f"  version  : {tx['version']}")
    print(f"  locktime : {tx['locktime']}")
    print(f"  inputs   : {len(tx['vin'])}")
    for i, inp in enumerate(tx['vin']):
        print(f"    [{i}] txid={inp['txid']} vout={inp['vout']} seq=0x{inp['sequence']:08x}")
        print(f"         scriptSig={inp['scriptSig']}")
    print(f"  outputs  : {len(tx['vout'])}")
    for i, o in enumerate(tx['vout']):
        print(f"    [{i}] {o['value_sat']} sat ({o['value_btc']:.8f} BTC)")
        print(f"         scriptPubKey={o['scriptPubKey']}")


# ─────────────────────────────────────────────
# TEST: verify that encode(decode(tx)) == tx
# ─────────────────────────────────────────────

TX1_ORIG = (
    "01000000010001000000000000000000000000000000000000000000000000000000000000000000006e"
    "493046022100e1eadba00d9296c743cb6ecc703fd9ddc9b3cd12906176a226ae4c18d6b00796022100"
    "a71aef7d2874deff681ba6080f1b278bac7bb99c61b08a85f4311970ffe7f63f012321030c0588dc44"
    "d92bdcbf8e72093466766fdc265ead8db64517b0c542275b70fffbacffffffff010140075af0750700"
    "015100000000"
)

TX2_ORIG = (
    "01000000010001000000000000000000000000000000000000000000000000000000000000000000006d"
    "483045022027deccc14aa6668e78a8c9da3484fbcd4f9dcc9bb7d1b85146314b21b9ae4d86022100d0"
    "b43dece8cfb07348de0ca8bc5b86276fa88f7f2138381128b7c36ab2e42264012321029bb13463ddd5"
    "d2cc05da6e84e37536cb9525703cfd8f43afdb414988987a92f6acffffffff020040075af075070001"
    "510001000000000000015100000000"
)

NEW_MAX_MONEY = 42_000_000 * 100_000_000  # 4_200_000_000_000_000 sat


def run_tests():
    print("=" * 60)
    print("TEST 1: decode -> encode must reproduce the original")
    print("=" * 60)

    for name, orig in [("TX1", TX1_ORIG), ("TX2", TX2_ORIG)]:
        orig_clean = orig.replace('\n', '').replace(' ', '')
        decoded = decode_tx(orig_clean)
        re_encoded = encode_tx(decoded).hex()
        ok = (re_encoded == orig_clean)
        print(f"\n{name}: {'OK' if ok else 'FAIL'}")
        if not ok:
            print(f"  expected : {orig_clean}")
            print(f"  got      : {re_encoded}")
        print_tx(decoded)

    print("\n" + "=" * 60)
    print("TEST 2: replacing amounts for new MAX_MONEY =", NEW_MAX_MONEY, "sat (46M BTC)")
    print("=" * 60)

    print("\nTX1 — output 0 = NEW_MAX_MONEY + 1:")
    tx1_new = set_output_amount(TX1_ORIG.replace('\n','').replace(' ',''), 0, NEW_MAX_MONEY + 1)
    print(f"  {tx1_new}")
    tx1_check = decode_tx(tx1_new)
    assert tx1_check['vout'][0]['value_sat'] == NEW_MAX_MONEY + 1, "TX1 check failed!"
    print("  Check OK")

    print("\nTX2 — output 0 = NEW_MAX_MONEY (output 1 = 1 sat, total > MAX_MONEY):")
    tx2_new = set_output_amount(TX2_ORIG.replace('\n','').replace(' ',''), 0, NEW_MAX_MONEY)
    print(f"  {tx2_new}")
    tx2_check = decode_tx(tx2_new)
    total = sum(o['value_sat'] for o in tx2_check['vout'])
    assert tx2_check['vout'][0]['value_sat'] == NEW_MAX_MONEY, "TX2 check failed!"
    print(f"  Check OK, total outputs: {total} sat")

    print("\n" + "=" * 60)
    print("JSON entries for tx_invalid.json:")
    print("=" * 60)
    print(f'\n["MAX_MONEY + 1 output"],')
    print(f'[[["0000000000000000000000000000000000000000000000000000000000000100", 0, '
          f'"HASH160 0x14 0x32afac281462b822adbec5094b8d4d337dd5bd6a EQUAL"]],')
    print(f'"{tx1_new}", "BADTX"],')
    print(f'\n["MAX_MONEY output + 1 output"],')
    print(f'[[["0000000000000000000000000000000000000000000000000000000000000100", 0, '
          f'"HASH160 0x14 0xb558cbf4930954aa6a344363a15668d7477ae716 EQUAL"]],')
    print(f'"{tx2_new}", "BADTX"],')


if __name__ == '__main__':
    if len(sys.argv) == 1:
        run_tests()
    elif sys.argv[1] == 'decode' and len(sys.argv) == 3:
        tx = decode_tx(sys.argv[2])
        print_tx(tx)
    elif sys.argv[1] == 'set_output' and len(sys.argv) == 5:
        result = set_output_amount(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
        print(result)
    else:
        print(__doc__)
