import hashlib
import binascii
import struct
import array
import os
import time
import sys
import optparse

import argon2


def GetBitwebPoWHash(data_block):
    """
    Bitweb PoW: single Argon2id round
    - salt: data_block
    - memory: 1 MB — GPU cannot parallelize effectively
    - time_cost: 3 passes — recommended by Argon2 authors for PoW
    - parallelism: 1 — prevents GPU thread splitting
    """
    salt = data_block
    return argon2.low_level.hash_secret_raw(
        secret=data_block,
        salt=salt,
        time_cost=3,
        memory_cost=1024,  # 1 MB (1024)
        parallelism=1,
        hash_len=32,
        type=argon2.low_level.Type.ID,
    )


def GetDpowcoinYespowerHash(data_block):
    """
    DPowCoin dual PoW: cheap Yespower hash only.
    Used as a fast filter — computed before expensive Argon2id.
    """
    try:
        import dpowcoin_yespower
    except ImportError:
        sys.exit("Cannot run dpowcoin algorithm: module dpowcoin_yespower not found")
    return dpowcoin_yespower.getPoWHash(data_block)[::-1]


def GetDpowcoinArgon2idHash(data_block):
    """
    DPowCoin dual PoW: expensive Argon2id hash only.
    Only called after Yespower check passes.
    """
    data_sha512   = hashlib.sha512(hashlib.sha512(data_block).digest()).digest()
    data_argon2id = argon2.low_level.hash_secret_raw(
        secret=data_block, salt=data_sha512,
        time_cost=2, memory_cost=4096, parallelism=2,
        hash_len=32, type=argon2.low_level.Type.ID,
    )
    return argon2.low_level.hash_secret_raw(
        secret=data_block, salt=data_argon2id,
        time_cost=2, memory_cost=32768, parallelism=2,
        hash_len=32, type=argon2.low_level.Type.ID,
    )[::-1]


def main():
    options = get_args()
    algorithm = get_algorithm(options)

    input_script     = create_input_script(options.timestamp)
    output_script    = create_output_script(options.pubkey, options.testnet4)
    tx               = create_transaction(input_script, output_script, options)
    hash_merkle_root = hashlib.sha256(hashlib.sha256(tx).digest()).digest()
    print_block_info(options, hash_merkle_root)

    block_header = create_block_header(hash_merkle_root, options.time, options.bits, options.nonce)
    genesis_hash, nonce, sha256_hash, yespower_or_scrypt_header_hash = generate_hash(block_header, algorithm, options.nonce, options.bits)
    announce_found_genesis(genesis_hash, nonce, sha256_hash, yespower_or_scrypt_header_hash, algorithm)


def get_args():
    parser = optparse.OptionParser()
    parser.add_option("-t", "--time",      dest="time",      default=1231006505, type="int",
                      help="unix time for genesis block")
    parser.add_option("-z", "--timestamp", dest="timestamp",
                      default="The Times 03/Jan/2009 Chancellor on brink of second bailout for banks",
                      type="string", help="pszTimestamp for coinbase")
    parser.add_option("-n", "--nonce",     dest="nonce",     default=0, type="int",
                      help="starting nonce")
    parser.add_option("-a", "--algorithm", dest="algorithm", default="sha256",
                      help="PoW algorithm: [sha256|scrypt|dpowcoin|bitweb]")
    parser.add_option("-p", "--pubkey",    dest="pubkey",
                      default="04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f",
                      type="string", help="pubkey for output script")
    parser.add_option("-v", "--value",     dest="value",     default=5000000000, type="int",
                      help="output value in satoshis (50 coins = 5000000000)")
    parser.add_option("-b", "--bits",      dest="bits",      type="int",
                      help="target in compact representation")

    # testnet4 flag: uses a non-standard 33-byte zeroed pubkey script
    # matching: CScript() << "000...00"_hex (33 bytes) << OP_CHECKSIG
    # output_script = 0x21 + 33 bytes + 0xac = 35 bytes total
    # without this flag: standard 65-byte uncompressed pubkey
    # output_script = 0x41 + 65 bytes + 0xac = 67 bytes total
    parser.add_option("--testnet4",        dest="testnet4",  default=False, action="store_true",
                      help="use testnet4 output script format (33-byte pubkey, 35-byte script total)")

    (options, args) = parser.parse_args()

    if not options.bits:
        if options.algorithm in ("scrypt", "dpowcoin"):
            options.bits = 0x1e0ffff0
        elif options.algorithm == "bitweb":
            options.bits = 0x1f1fffff  # Argon2id — low starting difficulty
        else:
            options.bits = 0x1d00ffff  # sha256 standard
    return options


def get_algorithm(options):
    supported_algorithms = ["sha256", "scrypt", "dpowcoin", "bitweb"]
    if options.algorithm in supported_algorithms:
        return options.algorithm
    else:
        sys.exit("Error: Given algorithm must be one of: " + str(supported_algorithms))


def create_input_script(psz_timestamp):
    ts_bytes = psz_timestamp.encode('utf-8')
    ts_len   = len(ts_bytes)
    prefix   = '04ffff001d0104'
    if ts_len < 0x4c:
        script_hex = prefix + format(ts_len, '02x') + ts_bytes.hex()
    else:
        script_hex = prefix + '4c' + format(ts_len, '02x') + ts_bytes.hex()
    return binascii.unhexlify(script_hex)


def create_output_script(pubkey, testnet4=False):
    """
    Standard (testnet4=False):
        output_script = OP_PUSHDATA(65) + pubkey_bytes(65) + OP_CHECKSIG
        = 0x41 + 65 bytes + 0xac = 67 bytes
        pubkey must be 130 hex chars (65 bytes uncompressed)

    Testnet4 (testnet4=True):
        Matches C++: CScript() << "000...00"_hex (33 bytes) << OP_CHECKSIG
        = 0x21 + 33 bytes + 0xac = 35 bytes
        pubkey must be 66 hex chars (33 bytes)
    """
    pubkey_bytes    = binascii.unhexlify(pubkey.encode())
    pubkey_len      = len(pubkey_bytes)
    script_len_byte = format(pubkey_len, '02x')
    OP_CHECKSIG     = 'ac'
    return binascii.unhexlify((script_len_byte + pubkey + OP_CHECKSIG).encode())


def create_transaction(input_script, output_script, options):
    """
    Build coinbase transaction using struct.pack directly.
    output_script size is dynamic — works for both standard (67 bytes)
    and testnet4 (35 bytes) or any other custom script size.

    Layout (bytes):
      4  version        LE uint32
      1  num_inputs     uint8
      32 prev_output    32x zero bytes
      4  prev_out_idx   BE uint32 = 0xFFFFFFFF (all-FF, endianness irrelevant)
      1  input_script_len uint8
      N  input_script
      4  sequence       BE uint32 = 0xFFFFFFFF (all-FF, endianness irrelevant)
      1  num_outputs    uint8
      8  out_value      LE int64
      1  output_script_len uint8
      M  output_script
      4  locktime       uint32 = 0
    """
    return (
        struct.pack('<I', 1)               +  # version
        struct.pack('B', 1)                +  # num_inputs
        struct.pack('<qqqq', 0, 0, 0, 0)   +  # prev_output (32 zero bytes)
        struct.pack('>I', 0xFFFFFFFF)      +  # prev_out_idx
        struct.pack('B', len(input_script))+  # input_script_len
        input_script                       +  # input_script
        struct.pack('>I', 0xFFFFFFFF)      +  # sequence
        struct.pack('B', 1)                +  # num_outputs
        struct.pack('<q', options.value)   +  # out_value
        struct.pack('B', len(output_script)) +  # output_script_len
        output_script                      +  # output_script
        struct.pack('<I', 0)                  # locktime
    )


def create_block_header(hash_merkle_root, time, bits, nonce):
    """
    Build 80-byte block header using struct.pack directly.

    Layout (bytes):
      4  version         LE uint32
      32 hash_prev_block 32x zero bytes
      32 hash_merkle_root
      4  time            LE uint32
      4  bits            LE uint32
      4  nonce           LE uint32
    """
    return (
        struct.pack('<I', 1)             +  # version
        struct.pack('<qqqq', 0, 0, 0, 0) +  # hash_prev_block (32 zero bytes)
        hash_merkle_root                 +  # hash_merkle_root
        struct.pack('<I', time)          +  # time
        struct.pack('<I', bits)          +  # bits
        struct.pack('<I', nonce)            # nonce
    )


def generate_hash(data_block, algorithm, start_nonce, bits):
    print('Searching for genesis hash..')
    nonce        = start_nonce
    last_updated = time.time()
    target       = (bits & 0xffffff) * 2 ** (8 * ((bits >> 24) - 3))
    max_nonce    = 0xFFFFFFFF

    while True:
        if algorithm == 'dpowcoin':
            # Dual PoW: cheap Yespower first as a filter,
            # expensive Argon2id only computed if Yespower passes.
            # Hash rate and sha256 are only computed when Argon2id is reached.
            yespower_header_hash = GetDpowcoinYespowerHash(data_block)
            if int(binascii.hexlify(yespower_header_hash), 16) < target:
                argon2id_header_hash = GetDpowcoinArgon2idHash(data_block)
                last_updated = calculate_hashrate(nonce, last_updated, algorithm)  # только для Argon2id
                if int(binascii.hexlify(argon2id_header_hash), 16) < target:
                    sha256_hash = hashlib.sha256(hashlib.sha256(data_block).digest()).digest()[::-1]  # только при успехе
                    return (argon2id_header_hash, nonce, sha256_hash, yespower_header_hash)
        else:
            last_updated = calculate_hashrate(nonce, last_updated, algorithm)
            sha256_hash, header_hash, yespower_or_scrypt_header_hash = generate_hashes_from_block(data_block, algorithm)
            if is_genesis_hash(header_hash, yespower_or_scrypt_header_hash, target):
                if algorithm == 'bitweb':
                    return (header_hash, nonce, sha256_hash, yespower_or_scrypt_header_hash)
                return (sha256_hash, nonce, sha256_hash, yespower_or_scrypt_header_hash)

        nonce     += 1
        data_block = data_block[0:len(data_block) - 4] + struct.pack('<I', nonce)

        if nonce == max_nonce:
            print("All nonces exhausted. Starting next round...")
            nonce        = start_nonce
            last_updated = time.time()
            print("Update time to:", last_updated)


def generate_hashes_from_block(data_block, algorithm):
    sha256_hash  = hashlib.sha256(hashlib.sha256(data_block).digest()).digest()[::-1]
    header_hash  = b""
    yespower_or_scrypt_header_hash = b""

    if algorithm == 'bitweb':
        raw          = GetBitwebPoWHash(data_block)[::-1]
        header_hash  = raw
        yespower_or_scrypt_header_hash = raw

    elif algorithm == 'scrypt':
        import scrypt
        h            = scrypt.hash(data_block, data_block, 1024, 1, 1, 32)[::-1]
        header_hash  = h
        yespower_or_scrypt_header_hash = h

    elif algorithm == 'sha256':
        header_hash  = sha256_hash
        yespower_or_scrypt_header_hash = sha256_hash

    return sha256_hash, header_hash, yespower_or_scrypt_header_hash


def is_genesis_hash(header_hash, yespower_or_scrypt_header_hash, target):
    return (int(binascii.hexlify(header_hash), 16) < target) and \
           (int(binascii.hexlify(yespower_or_scrypt_header_hash), 16) < target)


def calculate_hashrate(nonce, last_updated, algorithm):
    interval = 10 if algorithm in ("bitweb", "dpowcoin") else 50
    if nonce % interval == (interval - 1):
        now     = time.time()
        elapsed = now - last_updated
        if elapsed > 0:
            hashrate = round(interval / elapsed)
            sys.stdout.write("\r%s hash/s (nonce: %s)" % (str(hashrate), str(nonce)))
            sys.stdout.flush()
        return now
    return last_updated


def print_block_info(options, hash_merkle_root):
    print("algorithm: "     + options.algorithm)
    print("testnet4 mode: " + str(options.testnet4))
    print("merkle hash: "   + binascii.hexlify(hash_merkle_root[::-1]).decode())
    print("pszTimestamp: "  + options.timestamp)
    print("pubkey: "        + options.pubkey)
    print("time: "          + str(options.time))
    print("bits: "          + str(hex(options.bits)))
    if options.algorithm == "bitweb":
        print("--- Argon2id params ---")
        print("memory:      1 MB (1024 KB)")
        print("time_cost:   3 passes")
        print("parallelism: 1 thread")
        print("salt:        block_header")
        print("type:        Argon2id")
        print("note:        genesis search will be slow — this is expected")


def announce_found_genesis(genesis_hash, nonce, sha256_hash, yespower_or_scrypt_header_hash, algorithm):
    print("\ngenesis hash found!")
    print("nonce: " + str(nonce))

    if algorithm == 'sha256':
        print("genesis hash (sha256):   " + binascii.hexlify(sha256_hash).decode())

    elif algorithm == 'scrypt':
        print("genesis hash (scrypt):   " + binascii.hexlify(yespower_or_scrypt_header_hash).decode())
        print("genesis hash (sha256):   " + binascii.hexlify(sha256_hash).decode())

    elif algorithm == 'bitweb':
        print("genesis hash (argon2id): " + binascii.hexlify(genesis_hash).decode())
        print("genesis hash (sha256):   " + binascii.hexlify(sha256_hash).decode())

    elif algorithm == 'dpowcoin':
        print("genesis hash (argon2id): " + binascii.hexlify(genesis_hash).decode())
        print("genesis hash (yespower): " + binascii.hexlify(yespower_or_scrypt_header_hash).decode())
        print("genesis hash (sha256):   " + binascii.hexlify(sha256_hash).decode())
# GOGOGO!
main()
