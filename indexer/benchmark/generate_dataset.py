"""Generate a synthetic dataset for fuzzy search benchmarking.

Strategy:
  - Create N_FAMILIES "molecule families", each with one base hash and
    several variants at controlled Hamming distances.
  - Add NOISE_COUNT random unrelated hashes.
  - Save as JSON for batch registration.

Each entry has:
  - csh_hash: 0x + 64 hex chars (full 32-byte padding for bytes32 contract)
  - molecule_name: synthetic identifier
  - sha256_id: synthetic SHA-256 (deterministic from csh_hash)
  - energy_x1000: synthetic energy
  - family_id: which family (for ground truth)
  - true_hamming_to_base: distance to the family's base (for ground truth)
"""

import hashlib
import json
import random
from pathlib import Path


# ─── Configuration ────────────────────────────────────────────────────────────

N_FAMILIES = 50              # synthetic "molecules"
VARIANTS_PER_FAMILY = 9      # conformers per molecule (plus base = 10)
NOISE_COUNT = 100            # unrelated random hashes
HASH_BITS = 64               # CSH is 64-bit
SEED = 42                    # for reproducibility

# Variant Hamming distances — distribution mimicking real conformer ensembles:
# many similar (close to base), a few distant (large conformational changes).
# These are *target* Hammings; actual may differ slightly due to bit flipping.
VARIANT_HAMMINGS = [1, 2, 3, 4, 5, 8, 12, 18, 25]
assert len(VARIANT_HAMMINGS) == VARIANTS_PER_FAMILY

OUTPUT_FILE = Path(__file__).parent / "synthetic_dataset.json"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def random_64bit() -> int:
    """Generate a uniformly random 64-bit integer."""
    return random.getrandbits(HASH_BITS)


def flip_n_bits(value: int, n: int) -> int:
    """Flip exactly n random bits in the 64-bit value."""
    bit_positions = random.sample(range(HASH_BITS), n)
    for pos in bit_positions:
        value ^= (1 << pos)
    return value


def to_csh_hash_string(value: int) -> str:
    """Convert 64-bit int to bytes32-padded hex string (32 bytes total).

    The contract uses bytes32 (256 bits), but CSH is only 64 bits.
    We put the 64-bit value in the LOW 8 bytes, pad with zeros above.
    Output: 0x + 64 hex chars.
    """
    hex_64 = f"{value:016x}"          # 16 hex chars = 64 bits
    padding = "0" * (64 - 16)         # pad to 64 hex chars total
    return "0x" + hex_64 + padding


def hamming(a: int, b: int) -> int:
    """Hamming distance between two 64-bit integers."""
    return bin(a ^ b).count("1")


def make_sha256_id(csh_hash: str, family_id: int, variant_id: int) -> str:
    """Deterministic synthetic SHA-256 ID."""
    payload = f"{csh_hash}|fam{family_id}|var{variant_id}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


# ─── Generation ───────────────────────────────────────────────────────────────

def generate_dataset():
    random.seed(SEED)
    entries = []

    print(f"Generating {N_FAMILIES} families × {VARIANTS_PER_FAMILY + 1} "
          f"+ {NOISE_COUNT} noise = "
          f"{N_FAMILIES * (VARIANTS_PER_FAMILY + 1) + NOISE_COUNT} hashes")

    # Family entries
    for fam_id in range(N_FAMILIES):
        base_value = random_64bit()
        base_hash = to_csh_hash_string(base_value)

        # Base entry (variant_id = 0)
        entries.append({
            "csh_hash": base_hash,
            "molecule_name": f"synthmol_{fam_id:03d}_base",
            "sha256_id": make_sha256_id(base_hash, fam_id, 0),
            "energy_x1000": random.randint(-50_000, 50_000),
            "family_id": fam_id,
            "variant_id": 0,
            "true_hamming_to_base": 0,
        })

        # Variants
        for var_id, target_h in enumerate(VARIANT_HAMMINGS, start=1):
            variant_value = flip_n_bits(base_value, target_h)
            variant_hash = to_csh_hash_string(variant_value)
            actual_h = hamming(base_value, variant_value)

            entries.append({
                "csh_hash": variant_hash,
                "molecule_name": f"synthmol_{fam_id:03d}_var{var_id}",
                "sha256_id": make_sha256_id(variant_hash, fam_id, var_id),
                "energy_x1000": random.randint(-50_000, 50_000),
                "family_id": fam_id,
                "variant_id": var_id,
                "true_hamming_to_base": actual_h,
            })

    # Noise entries (unrelated to any family)
    for noise_id in range(NOISE_COUNT):
        noise_value = random_64bit()
        noise_hash = to_csh_hash_string(noise_value)
        entries.append({
            "csh_hash": noise_hash,
            "molecule_name": f"noise_{noise_id:03d}",
            "sha256_id": make_sha256_id(noise_hash, -1, noise_id),
            "energy_x1000": random.randint(-50_000, 50_000),
            "family_id": -1,         # -1 means "no family"
            "variant_id": -1,
            "true_hamming_to_base": -1,
        })

    # Sanity check: no duplicate hashes (would fail contract's require)
    all_hashes = [e["csh_hash"] for e in entries]
    if len(set(all_hashes)) != len(all_hashes):
        n_dups = len(all_hashes) - len(set(all_hashes))
        raise RuntimeError(
            f"Generated {n_dups} duplicate hash(es). "
            f"Try a different seed or smaller dataset."
        )

    with open(OUTPUT_FILE, "w") as f:
        json.dump(entries, f, indent=2)

    print(f"\n✓ Wrote {len(entries)} entries to {OUTPUT_FILE}")
    print(f"  - {N_FAMILIES} families × {VARIANTS_PER_FAMILY + 1} variants "
          f"= {N_FAMILIES * (VARIANTS_PER_FAMILY + 1)}")
    print(f"  - {NOISE_COUNT} noise entries")
    print(f"  - Estimated cost on Sepolia: "
          f"{len(entries) * 0.000023:.4f} ETH")


if __name__ == "__main__":
    generate_dataset()
