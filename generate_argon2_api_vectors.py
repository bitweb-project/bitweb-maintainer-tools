#!/usr/bin/env python3
"""
generate_argon2_api_vectors.py

Generates test vectors for the full Argon2 C API:
  - argon2d_hash_raw / argon2i_hash_raw / argon2id_hash_raw
  - argon2d_hash_encoded / argon2i_hash_encoded / argon2id_hash_encoded  (via verify)
  - argon2_hash  (generic, both raw and encoded output paths)
  - argon2_ctx / argon2d_ctx / argon2i_ctx / argon2id_ctx

Output: argon2_api_test_vectors.json

Usage:
    pip install argon2-cffi
    python3 generate_argon2_api_vectors.py
"""

import json
import secrets
import argon2.low_level as ll

# Reproducible RNG seed
SEED = 0xDEADBEEF

# Parameter sets exercised across all three Argon2 types.
# Keep m_cost small so the C++ test suite runs quickly.
PARAM_SETS = [
    # (t_cost, m_cost_kib, parallelism, hash_len)
    (1,  64, 1, 32),
    (2, 128, 1, 32),
    (3, 256, 1, 32),
    (1,  64, 1, 16),  # short hash
    (1,  64, 1, 64),  # long hash
    (2, 128, 2, 32),  # parallelism = 2  (m_cost must be >= 8 * lanes)
    (1,  64, 4, 32),  # parallelism = 4
]

# Number of random (data, salt) pairs generated per (type × param_set) combination.
VECTORS_PER_BUCKET = 4

ARGON2_TYPE_MAP = {
    "argon2d":  ll.Type.D,
    "argon2i":  ll.Type.I,
    "argon2id": ll.Type.ID,
}


def rand_bytes(rng: secrets.SystemRandom, lo: int, hi: int) -> bytes:
    n = rng.randint(lo, hi)
    return bytes(rng.getrandbits(8) for _ in range(n))


def build_raw_vectors(rng: secrets.SystemRandom) -> list[dict]:
    """
    Vectors for _hash_raw and _ctx tests.
    Each vector: type, params, data/salt (hex), expected raw hash (hex).
    """
    vectors = []
    for type_name, ll_type in ARGON2_TYPE_MAP.items():
        for (t, m, p, hlen) in PARAM_SETS:
            for _ in range(VECTORS_PER_BUCKET):
                data = rand_bytes(rng, 1, 128)
                salt = rand_bytes(rng, 8, 64)
                raw = ll.hash_secret_raw(
                    secret=data,
                    salt=salt,
                    time_cost=t,
                    memory_cost=m,
                    parallelism=p,
                    hash_len=hlen,
                    type=ll_type,
                )
                vectors.append({
                    "type":          type_name,
                    "t_cost":        t,
                    "m_cost":        m,
                    "parallelism":   p,
                    "hash_len":      hlen,
                    "data":          data.hex(),
                    "salt":          salt.hex(),
                    "expected_hash": raw.hex(),
                })
    return vectors


def build_encoded_vectors(rng: secrets.SystemRandom) -> list[dict]:
    """
    Vectors for _hash_encoded and _verify tests.
    Each vector: type, params, data/salt (hex), encoded string (str).
    The encoded string is the canonical Argon2 PHC string (starts with $argon2…).
    """
    vectors = []
    for type_name, ll_type in ARGON2_TYPE_MAP.items():
        # Use a representative subset of param sets for encoded tests
        for (t, m, p, hlen) in PARAM_SETS[:5]:
            for _ in range(VECTORS_PER_BUCKET):
                data = rand_bytes(rng, 1, 128)
                salt = rand_bytes(rng, 8, 64)
                enc_bytes = ll.hash_secret(
                    secret=data,
                    salt=salt,
                    time_cost=t,
                    memory_cost=m,
                    parallelism=p,
                    hash_len=hlen,
                    type=ll_type,
                )
                encoded = enc_bytes.decode("ascii")
                vectors.append({
                    "type":        type_name,
                    "t_cost":      t,
                    "m_cost":      m,
                    "parallelism": p,
                    "hash_len":    hlen,
                    "data":        data.hex(),
                    "salt":        salt.hex(),
                    "encoded":     encoded,
                })
    return vectors


def build_generic_api_vectors(rng: secrets.SystemRandom) -> list[dict]:
    """
    Vectors that exercise argon2_hash() – the generic function that can
    write both a raw hash and an encoded string in a single call.
    Each vector records both raw hash and encoded string so the C++ test
    can verify both output paths independently.
    """
    vectors = []
    for type_name, ll_type in ARGON2_TYPE_MAP.items():
        for (t, m, p, hlen) in [(1, 64, 1, 32), (2, 128, 1, 32), (1, 64, 2, 32)]:
            for _ in range(VECTORS_PER_BUCKET):
                data = rand_bytes(rng, 1, 128)
                salt = rand_bytes(rng, 8, 64)
                raw = ll.hash_secret_raw(
                    secret=data, salt=salt,
                    time_cost=t, memory_cost=m, parallelism=p,
                    hash_len=hlen, type=ll_type,
                )
                enc_bytes = ll.hash_secret(
                    secret=data, salt=salt,
                    time_cost=t, memory_cost=m, parallelism=p,
                    hash_len=hlen, type=ll_type,
                )
                vectors.append({
                    "type":          type_name,
                    "t_cost":        t,
                    "m_cost":        m,
                    "parallelism":   p,
                    "hash_len":      hlen,
                    "data":          data.hex(),
                    "salt":          salt.hex(),
                    "expected_hash": raw.hex(),
                    "encoded":       enc_bytes.decode("ascii"),
                })
    return vectors


def build_error_param_vectors() -> list[dict]:
    """
    Fixed inputs used by the C++ error-handling tests.
    These don't need hash output — the test deliberately passes bad params.
    We just record a valid (data, salt) pair to use as inputs.
    """
    return [
        {"data": "deadbeef", "salt": "0102030405060708"},
    ]


def main() -> None:
    rng = secrets.SystemRandom()
    rng.seed(SEED)

    raw_vecs     = build_raw_vectors(rng)
    encoded_vecs = build_encoded_vectors(rng)
    generic_vecs = build_generic_api_vectors(rng)
    error_vecs   = build_error_param_vectors()

    output = {
        "raw_vectors":     raw_vecs,
        "encoded_vectors": encoded_vecs,
        "generic_vectors": generic_vecs,
        "error_inputs":    error_vecs,
    }

    out_path = "argon2_api_test_vectors.json"
    with open(out_path, "w", newline="\n") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    total = len(raw_vecs) + len(encoded_vecs) + len(generic_vecs)
    print(f"Generated {len(raw_vecs)} raw, {len(encoded_vecs)} encoded, "
          f"{len(generic_vecs)} generic vectors  →  {out_path}")
    print(f"Total vectors: {total}")
    print(f"  raw breakdown:     {len(raw_vecs)} "
          f"({len(raw_vecs)//3} per type × 3 types)")
    print(f"  encoded breakdown: {len(encoded_vecs)} "
          f"({len(encoded_vecs)//3} per type × 3 types)")
    print(f"  generic breakdown: {len(generic_vecs)} "
          f"({len(generic_vecs)//3} per type × 3 types)")


if __name__ == "__main__":
    main()
