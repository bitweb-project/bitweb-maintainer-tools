#!/usr/bin/env python3
"""
PSBT (Partially Signed Bitcoin Transaction) decoder/encoder.

Usage:
    python3 psbt_tool.py decode <base64>
    python3 psbt_tool.py set_witness_value <base64> <input_index> <amount_satoshis>
    python3 psbt_tool.py set_output_value <base64> <output_index> <amount_satoshis>

Examples:
    python3 psbt_tool.py decode cHNidP8B...
    python3 psbt_tool.py set_witness_value cHNidP8B... 0 4300000000000001
    python3 psbt_tool.py set_output_value cHNidP8B... 0 4300000000000001

Consistency note:
    The original Bitcoin test used 22_000_000 BTC (22 * 1e14 sat) —
    just a round number > MAX_MONEY (21M). For a fork with MAX_MONEY = 42M
    use 43_000_000 * 1e8 = 4_300_000_000_000_000 sat (43 * 1e14).
"""

import base64
import struct
import sys
import json


COIN = 100_000_000


# ─────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def read_varint(data: bytes, pos: int):
    b = data[pos]
    if b < 0xfd:
        return b, pos + 1
    elif b == 0xfd:
        return struct.unpack_from('<H', data, pos + 1)[0], pos + 3
    elif b == 0xfe:
        return struct.unpack_from('<I', data, pos + 1)[0], pos + 5
    else:
        return struct.unpack_from('<Q', data, pos + 1)[0], pos + 9


def write_varint(n: int) -> bytes:
    if n < 0xfd:
        return bytes([n])
    elif n <= 0xffff:
        return b'\xfd' + struct.pack('<H', n)
    elif n <= 0xffffffff:
        return b'\xfe' + struct.pack('<I', n)
    else:
        return b'\xff' + struct.pack('<Q', n)


def read_kv(data: bytes, pos: int):
    """Reads one PSBT key-value pair. Returns (key, value, new_pos)."""
    key_len, pos = read_varint(data, pos)
    if key_len == 0:
        return None, None, pos  # map separator
    key = data[pos:pos + key_len]
    pos += key_len
    val_len, pos = read_varint(data, pos)
    val = data[pos:pos + val_len]
    pos += val_len
    return key, val, pos


def write_kv(key: bytes, val: bytes) -> bytes:
    return write_varint(len(key)) + key + write_varint(len(val)) + val


# ─────────────────────────────────────────────────────────────────────────────
# Raw transaction parser (for unsigned_tx from global map)
# ─────────────────────────────────────────────────────────────────────────────

def parse_tx(data: bytes):
    pos = 0
    version = struct.unpack_from('<i', data, pos)[0]; pos += 4
    vin_count, pos = read_varint(data, pos)
    inputs = []
    for _ in range(vin_count):
        txid = data[pos:pos+32][::-1].hex(); pos += 32
        vout = struct.unpack_from('<I', data, pos)[0]; pos += 4
        script_len, pos = read_varint(data, pos)
        script = data[pos:pos+script_len].hex(); pos += script_len
        seq = struct.unpack_from('<I', data, pos)[0]; pos += 4
        inputs.append({'txid': txid, 'vout': vout, 'scriptSig': script, 'sequence': seq})
    vout_count, pos = read_varint(data, pos)
    outputs = []
    for _ in range(vout_count):
        value = struct.unpack_from('<q', data, pos)[0]; pos += 8
        script_len, pos = read_varint(data, pos)
        script = data[pos:pos+script_len].hex(); pos += script_len
        outputs.append({'value_sat': value, 'value_coin': value / COIN, 'scriptPubKey': script})
    locktime = struct.unpack_from('<I', data, pos)[0]
    return {'version': version, 'vin': inputs, 'vout': outputs, 'locktime': locktime}


def parse_txout(data: bytes):
    """Parses CTxOut (witness UTXO): 8-byte value + scriptPubKey."""
    value = struct.unpack_from('<q', data, 0)[0]
    script_len, pos = read_varint(data, 8)
    script = data[pos:pos + script_len].hex()
    return {'value_sat': value, 'value_coin': value / COIN, 'scriptPubKey': script}


def encode_txout(value_sat: int, scriptpubkey_hex: str) -> bytes:
    script = bytes.fromhex(scriptpubkey_hex)
    return struct.pack('<q', value_sat) + write_varint(len(script)) + script


# ─────────────────────────────────────────────────────────────────────────────
# PSBT parser — returns structure + map list for re-assembly
# ─────────────────────────────────────────────────────────────────────────────

PSBT_MAGIC = b'psbt\xff'

# Global map key types
PSBT_GLOBAL_UNSIGNED_TX = 0x00

# Input map key types
PSBT_IN_WITNESS_UTXO    = 0x01
PSBT_IN_NON_WITNESS_UTXO = 0x00

# Output map key types
PSBT_OUT_REDEEM_SCRIPT  = 0x00


def decode_psbt(b64: str) -> dict:
    """Fully decodes a PSBT from base64."""
    data = base64.b64decode(b64)

    if data[:5] != PSBT_MAGIC:
        raise ValueError("Missing PSBT magic bytes psbt\\xff")

    pos = 5
    result = {'global': {}, 'inputs': [], 'outputs': [], '_raw': data}

    # ── Global map ──
    while True:
        key, val, pos = read_kv(data, pos)
        if key is None:
            break
        key_type = key[0]
        if key_type == PSBT_GLOBAL_UNSIGNED_TX:
            result['global']['unsigned_tx'] = parse_tx(val)
            result['global']['unsigned_tx_raw'] = val.hex()
        else:
            result['global'].setdefault('unknown', {})[key.hex()] = val.hex()

    n_inputs  = len(result['global']['unsigned_tx']['vin'])
    n_outputs = len(result['global']['unsigned_tx']['vout'])

    # ── Input maps ──
    for i in range(n_inputs):
        inp = {}
        while True:
            key, val, pos = read_kv(data, pos)
            if key is None:
                break
            key_type = key[0]
            if key_type == PSBT_IN_WITNESS_UTXO and len(key) == 1:
                inp['witness_utxo'] = parse_txout(val)
                inp['witness_utxo_raw'] = val.hex()
            elif key_type == PSBT_IN_NON_WITNESS_UTXO and len(key) == 1:
                inp['non_witness_utxo'] = parse_tx(val)
                inp['non_witness_utxo_raw'] = val.hex()
            else:
                inp.setdefault('unknown', {})[key.hex()] = val.hex()
        result['inputs'].append(inp)

    # ── Output maps ──
    for i in range(n_outputs):
        out = {}
        while True:
            key, val, pos = read_kv(data, pos)
            if key is None:
                break
            out.setdefault('unknown', {})[key.hex()] = val.hex()
        result['outputs'].append(out)

    return result


def encode_psbt(result: dict) -> bytes:
    """Re-assembles PSBT from structure back into bytes."""
    out = bytearray(PSBT_MAGIC)

    # ── Global map ──
    tx_raw = bytes.fromhex(result['global']['unsigned_tx_raw'])
    out += write_kv(bytes([PSBT_GLOBAL_UNSIGNED_TX]), tx_raw)
    for key_hex, val_hex in result['global'].get('unknown', {}).items():
        out += write_kv(bytes.fromhex(key_hex), bytes.fromhex(val_hex))
    out += b'\x00'  # map separator

    # ── Input maps ──
    for inp in result['inputs']:
        if 'non_witness_utxo_raw' in inp:
            out += write_kv(bytes([PSBT_IN_NON_WITNESS_UTXO]), bytes.fromhex(inp['non_witness_utxo_raw']))
        if 'witness_utxo_raw' in inp:
            out += write_kv(bytes([PSBT_IN_WITNESS_UTXO]), bytes.fromhex(inp['witness_utxo_raw']))
        for key_hex, val_hex in inp.get('unknown', {}).items():
            out += write_kv(bytes.fromhex(key_hex), bytes.fromhex(val_hex))
        out += b'\x00'

    # ── Output maps ──
    for o in result['outputs']:
        for key_hex, val_hex in o.get('unknown', {}).items():
            out += write_kv(bytes.fromhex(key_hex), bytes.fromhex(val_hex))
        out += b'\x00'

    return bytes(out)


# ─────────────────────────────────────────────────────────────────────────────
# Modification operations
# ─────────────────────────────────────────────────────────────────────────────

def op_decode(b64: str):
    """Decodes and pretty-prints a PSBT."""
    psbt = decode_psbt(b64)
    tx = psbt['global']['unsigned_tx']

    print("═" * 60)
    print("GLOBAL")
    print("═" * 60)
    print(f"  tx version : {tx['version']}")
    print(f"  locktime   : {tx['locktime']}")
    print(f"  inputs     : {len(tx['vin'])}")
    for i, v in enumerate(tx['vin']):
        print(f"    [{i}] txid={v['txid']} vout={v['vout']}")
    print(f"  outputs    : {len(tx['vout'])}")
    for i, v in enumerate(tx['vout']):
        print(f"    [{i}] {v['value_sat']} sat ({v['value_coin']:.8f})")

    print()
    print("═" * 60)
    print("INPUTS")
    print("═" * 60)
    for i, inp in enumerate(psbt['inputs']):
        print(f"  [{i}]")
        if 'witness_utxo' in inp:
            u = inp['witness_utxo']
            print(f"    witness_utxo  value : {u['value_sat']} sat ({u['value_coin']:.8f})")
            print(f"    witness_utxo  script: {u['scriptPubKey']}")
        if 'non_witness_utxo' in inp:
            print(f"    non_witness_utxo: (full tx, {len(inp['non_witness_utxo_raw'])//2} bytes)")
        if inp.get('unknown'):
            for k, v in inp['unknown'].items():
                print(f"    unknown key {k}: {v}")

    print()
    print("═" * 60)
    print("OUTPUTS")
    print("═" * 60)
    for i, o in enumerate(psbt['outputs']):
        if o.get('unknown'):
            for k, v in o['unknown'].items():
                print(f"  [{i}] key {k}: {v}")
        else:
            print(f"  [{i}] (empty map)")


def op_set_witness_value(b64: str, input_index: int, new_value_sat: int) -> str:
    """Changes witness_utxo.value for the given input, returns new base64."""
    psbt = decode_psbt(b64)
    inp = psbt['inputs'][input_index]

    if 'witness_utxo' not in inp:
        raise ValueError(f"Input {input_index} has no witness_utxo")

    old = inp['witness_utxo']['value_sat']
    script = inp['witness_utxo']['scriptPubKey']

    # Rebuild witness_utxo_raw with the new value
    inp['witness_utxo_raw'] = encode_txout(new_value_sat, script).hex()
    inp['witness_utxo']['value_sat'] = new_value_sat
    inp['witness_utxo']['value_coin'] = new_value_sat / COIN

    new_bytes = encode_psbt(psbt)
    new_b64 = base64.b64encode(new_bytes).decode()

    print(f"  Input {input_index} witness_utxo value:")
    print(f"    Old  : {old} sat ({old/COIN:.8f})")
    print(f"    New : {new_value_sat} sat ({new_value_sat/COIN:.8f})")
    print(f"\n  New PSBT base64:")
    print(f"  {new_b64}")

    # Verify
    psbt2 = decode_psbt(new_b64)
    check = psbt2['inputs'][input_index]['witness_utxo']['value_sat']
    assert check == new_value_sat, f"Verification failed: {check} != {new_value_sat}"
    print(f"\n  ✓ Verify OK: {check} sat")

    return new_b64


def op_set_output_value(b64: str, output_index: int, new_value_sat: int) -> str:
    """Changes the value of an output in unsigned_tx, returns new base64."""
    psbt = decode_psbt(b64)
    tx = psbt['global']['unsigned_tx']
    vout = tx['vout']

    old = vout[output_index]['value_sat']
    vout[output_index]['value_sat'] = new_value_sat
    vout[output_index]['value_coin'] = new_value_sat / COIN

    # Rebuild unsigned_tx_raw
    raw = _encode_tx_raw(tx)
    psbt['global']['unsigned_tx_raw'] = raw.hex()

    new_bytes = encode_psbt(psbt)
    new_b64 = base64.b64encode(new_bytes).decode()

    print(f"  Output {output_index} value:")
    print(f"    Old  : {old} sat ({old/COIN:.8f})")
    print(f"    New : {new_value_sat} sat ({new_value_sat/COIN:.8f})")
    print(f"\n  New PSBT base64:")
    print(f"  {new_b64}")

    psbt2 = decode_psbt(new_b64)
    check = psbt2['global']['unsigned_tx']['vout'][output_index]['value_sat']
    assert check == new_value_sat, f"Verification failed: {check} != {new_value_sat}"
    print(f"\n  ✓ Verify OK: {check} sat")

    return new_b64


def _encode_tx_raw(tx: dict) -> bytes:
    """Re-encodes unsigned_tx back into bytes."""
    out = struct.pack('<i', tx['version'])
    out += write_varint(len(tx['vin']))
    for inp in tx['vin']:
        out += bytes.fromhex(inp['txid'])[::-1]
        out += struct.pack('<I', inp['vout'])
        script = bytes.fromhex(inp['scriptSig'])
        out += write_varint(len(script)) + script
        out += struct.pack('<I', inp['sequence'])
    out += write_varint(len(tx['vout']))
    for o in tx['vout']:
        out += struct.pack('<q', o['value_sat'])
        script = bytes.fromhex(o['scriptPubKey'])
        out += write_varint(len(script)) + script
    out += struct.pack('<I', tx['locktime'])
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Consistency: MAX_MONEY -> recommended test value mapping
# ─────────────────────────────────────────────────────────────────────────────

def print_consistency_hint(max_money_coins: int):
    """
    Original Bitcoin: MAX_MONEY = 21M, used 22 * 1e14 (just a round number > MAX_MONEY).
    Pattern: (MAX_MONEY_coins / 1M + 1) * 1e14
    """
    suggestion = (max_money_coins // 1_000_000 + 1) * 100_000_000_000_000
    print(f"\n  Recommended value for MAX_MONEY={max_money_coins}M coins:")
    print(f"  {suggestion} sat = {suggestion/COIN:.0f} coins")
    print(f"  (pattern: round number > MAX_MONEY, like original 22M > 21M)")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(__doc__)

        # Run built-in demo
        print("\n" + "═" * 60)
        print("DEMO: decoding original PSBT from rpc_psbt.py")
        print("═" * 60)
        orig = "cHNidP8BAHECAAAAAfA00BFgAm6tp86RowwH6BMImQNL5zXUcTT97XoLGz0BAAAAAAD/////AgD5ApUAAAAAFgAUKNw0x8HRctAgmvoevm4u1SbN7XL87QKVAAAAABYAFPck4gF7iL4NL4wtfRAKgQbghiTUAAAAAAABAR8AgIFq49AHABYAFJUDtxf2PHo641HEOBOAIvFMNTr2AAAA"
        op_decode(orig)

        print("\n" + "═" * 60)
        print("DEMO: replacing witness_utxo value for MAX_MONEY = 42M")
        print("═" * 60)
        # Pattern: 22M for 21M -> 43M for 42M (next round number above MAX_MONEY)
        new_val = 43 * 100_000_000_000_000  # 43_000_000 coins = 43 * 1e14 sat
        print(f"  Using {new_val} sat = {new_val/COIN:.0f} coins (43M > MAX_MONEY 42M)")
        op_set_witness_value(orig, 0, new_val)
        print_consistency_hint(46)
        return

    cmd = sys.argv[1]
    b64 = sys.argv[2]

    if cmd == 'decode':
        op_decode(b64)

    elif cmd == 'set_witness_value':
        if len(sys.argv) != 5:
            print("Usage: psbt_tool.py set_witness_value <base64> <input_index> <amount_sat>")
            sys.exit(1)
        op_set_witness_value(b64, int(sys.argv[3]), int(sys.argv[4]))

    elif cmd == 'set_output_value':
        if len(sys.argv) != 5:
            print("Usage: psbt_tool.py set_output_value <base64> <output_index> <amount_sat>")
            sys.exit(1)
        op_set_output_value(b64, int(sys.argv[3]), int(sys.argv[4]))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
