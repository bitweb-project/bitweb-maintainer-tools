#!/usr/bin/env python3
import json
import secrets
import argon2

T_COST = 3
M_COST = 1024   # KiB
PARALLELISM = 1
HASH_LEN = 32
NUM_VECTORS = 500
SEED = 0x42

def main():
    rng = secrets.SystemRandom()
    rng.seed(SEED)
    vectors = []

    for _ in range(NUM_VECTORS):
        data_len = rng.randint(1, 256)
        salt_len = rng.randint(8, 256)
        data = bytes(rng.getrandbits(8) for _ in range(data_len))
        salt = bytes(rng.getrandbits(8) for _ in range(salt_len))

        hash_raw = argon2.low_level.hash_secret_raw(
            secret=data,
            salt=salt,
            time_cost=T_COST,
            memory_cost=M_COST,
            parallelism=PARALLELISM,
            hash_len=HASH_LEN,
            type=argon2.low_level.Type.ID,
        )

        vectors.append({
            "data": data.hex(),
            "salt": salt.hex(),
            "expected_hash": hash_raw.hex()
        })

    with open("argon2id_vectors.json", "w", newline='\n') as f:
        json.dump(vectors, f, indent=2)
        f.write('\n')

if __name__ == "__main__":
    main()
