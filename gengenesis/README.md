## Genesis Block Proof of Work for multiple Hash Algorithms Bitcoin, Litecoin, Dpowcoin(dualpowalgo), Bitweb(argon2id) for python 3.13.x


## setup

```js

sudo pip install dpowcoin-yespower (Only for dpowcoin)

sudo pip install argon2-cffi (Bitweb and Dpowcoin)

Instead pip for Ubuntu / Debian
sudo apt install python3-argon2 (Bitweb and Dpowcoin)


cd genesis-block

```

## help

```js 
Usage: gen.py [options]
    
    Options:
      -h, --help show this help message and exit
      -t TIME, --time=TIME  the (unix) time when the genesisblock is created
      -z TIMESTAMP, --timestamp=TIMESTAMP
         the pszTimestamp found in the coinbase of the genesisblock
      -n NONCE, --nonce=NONCE
         the first value of the nonce that will be incremented
         when searching the genesis hash
      -a ALGORITHM, --algorithm=ALGORITHM
         the PoW algorithm: [sha256(Default)|scrypt|dpowcoin(dualpowalgo)|bitweb(argon2id)]
      -p PUBKEY, --pubkey=PUBKEY
         the pubkey found in the output script
      -v VALUE, --value=VALUE
         the value in coins for the output, full value (exp. in bitcoin 5000000000 - To get other coins value: Block Value * 100000000)
      -b BITS, --bits=BITS
         the target in compact representation, associated to a difficulty of 1
      --testnet4
	     need arg for correct genesis coinsbase tx at testnet4 if it smaller than standart
```



## Genesis Block Proof of Work for SHA256 Algorithms.

```js
Bitcoin Mainnet

python3 gen.py -z "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks" -a sha256 -b 0x1d00ffff -p "04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f" -v 5000000000 -t 1231006505 -n 2083236893

algorithm: sha256
testnet4 mode: False
merkle hash: 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b
pszTimestamp: The Times 03/Jan/2009 Chancellor on brink of second bailout for banks
pubkey: 04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f
time: 1231006505
bits: 0x1d00ffff
Searching for genesis hash..

genesis hash found!
nonce: 2083236893
genesis hash (sha256):   000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
```

```js
Bitcoin Testnet4

python3 gen.py -z "03/May/2024 000000000000000000001ebd58c244970b3aa9d783bb001011fbe8ea8e98e00e" -a sha256 -b 0x1d00ffff -p "000000000000000000000000000000000000000000000000000000000000000000" -v 5000000000 -t 1714777860 -n 393743547 --testnet4

algorithm: sha256
testnet4 mode: True
merkle hash: 7aa0a7ae1e223414cb807e40cd57e667b718e42aaf9306db9102fe28912b7b4e
pszTimestamp: 03/May/2024 000000000000000000001ebd58c244970b3aa9d783bb001011fbe8ea8e98e00e
pubkey: 000000000000000000000000000000000000000000000000000000000000000000
time: 1714777860
bits: 0x1d00ffff
Searching for genesis hash..

genesis hash found!
nonce: 393743547
genesis hash (sha256):   00000000da84f2bafbbc53dee25a72ae507ff4914b867c565be350b0da8bf043
```

## Genesis Block Proof of Work for Bitweb (argon2id) Algorithm.
```js
Bitweb Mainnet

python3 gen.py -z "Bitweb Core Blockchain Restart 1775999888" -a bitweb -b 0x1f0fffff -p "04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f" -v 5000000000 -t 1775999888 -n 199888899

algorithm: bitweb
testnet4 mode: False
merkle hash: 14dee9b42e7c1893b5c472bd6c8bcb2fe51f797a97369561716d3997b00c08f6
pszTimestamp: Bitweb Core Blockchain Restart 1775999888
pubkey: 04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f
time: 1775999888
bits: 0x1f0fffff
--- Argon2id params ---
memory:      1 MB (1024 KB)
time_cost:   3 passes
parallelism: 1 thread
salt:        block_header
type:        Argon2id
note:        genesis search will be slow — this is expected
Searching for genesis hash..
4797 hash/s (nonce: 199888899)
genesis hash found!
nonce: 199888899
genesis hash (argon2id): 0001139508ab9c40c1fecc9a34d076ea9114b77279f2c4f54f3f2b3f2422f511
genesis hash (sha256):   111692c1b9b390c407ab74d7f924d4fa0f7589974ab61af96392feca11f209e6
```

```js
Bitweb Testnet4

python3 gen.py -z "1775999890 TestNet4 Genesis" -a bitweb -b 0x1f0fffff -p "000000000000000000000000000000000000000000000000000000000000000000" -v 5000000000 -t 1775999890 -n 99880088 --testnet4

algorithm: bitweb
testnet4 mode: True
merkle hash: 45dc81c6f9bd42e76a06fa810a9704e9a0e0415c50850b68d55a0648f6880616
pszTimestamp: 1775999890 TestNet4 Genesis
pubkey: 000000000000000000000000000000000000000000000000000000000000000000
time: 1775999890
bits: 0x1f0fffff
--- Argon2id params ---
memory:      1 MB (1024 KB)
time_cost:   3 passes
parallelism: 1 thread
salt:        block_header
type:        Argon2id
note:        genesis search will be slow — this is expected
Searching for genesis hash..

genesis hash found!
nonce: 99880088
genesis hash (argon2id): 0000231c8e92626337d38ea9444e0834b3f5a6e9fcbc5aa1ecfbcc42fd65e849
genesis hash (sha256):   b80f3f587edbe596c082d4f28a2b3590c10723822b6ff100726e37eac83510a3
```

## Genesis Block Proof of Work for Litecoin (scrypt) Algorithm.
```js
Litecoin Mainnet

python3 gen.py -z "NY Times 05/Oct/2011 Steve Jobs, Apple’s Visionary, Dies at 56" -a scrypt -b 0x1e0ffff0 -p "040184710fa689ad5023690c80f3a49c8f13f8d45b8c857fbcbc8bc4a8e4d3eb4b10f4d4604fa08dce601aaf0f470216fe1b51850b4acf21b179c45070ac7b03a9" -v 5000000000 -t 1317972665 -n 2084524493

algorithm: scrypt
testnet4 mode: False
merkle hash: 97ddfbbae6be97fd6cdf3e7ca13232a3afff2353e29badfab7f73011edd4ced9
pszTimestamp: NY Times 05/Oct/2011 Steve Jobs, Apple’s Visionary, Dies at 56
pubkey: 040184710fa689ad5023690c80f3a49c8f13f8d45b8c857fbcbc8bc4a8e4d3eb4b10f4d4604fa08dce601aaf0f470216fe1b51850b4acf21b179c45070ac7b03a9
time: 1317972665
bits: 0x1e0ffff0
Searching for genesis hash..

genesis hash found!
nonce: 2084524493
genesis hash (scrypt):   0000050c34a64b415b6b15b37f2216634b5b1669cb9a2e38d76f7213b0671e00
genesis hash (sha256):   12a765e31ffd4059bada1e25190f6e98c99d9714d334efa41a195a7e7e04bfe2
```

## Genesis Block Proof of Work for dpowcoin (Dual Pow Algo) Algorithms.

```js
Dpowcoin

python3 gen.py -z "One POW? Why not two? 17/04/2024" -a dpowcoin -b 0x1f1fffff -p "04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f" -v 5000000000 -t 1713510000 -n 8808588

algorithm: dpowcoin
testnet4 mode: False
merkle hash: 10f5376e5169449acf540bb89615fb337319bb5e31de16f792665bf6e3518eb3
pszTimestamp: One POW? Why not two? 17/04/2024
pubkey: 04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3f4cef38c4f35504e51ec112de5c384df7ba0b8d578a4c702b6bf11d5f
time: 1713510000
bits: 0x1f1fffff
Searching for genesis hash..

genesis hash found!
nonce: 8808588
genesis hash (argon2id): 001043a357bc3002a94531cd4c8f3fc317d4bcb120b003fb00a5fc8b2486d528
genesis hash (yespower): 001d5853581df9cb0a71cdcb88702578f0a9297a9ee78f366dc57ba92f670e48
genesis hash (sha256):   d86f8a0582e779830f182befeaaabc8c73a159b6b06530910758daf17ce31e36
```
