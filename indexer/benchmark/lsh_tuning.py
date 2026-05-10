"""LSH banding parameter tuning on real molecular conformer data.

Tests multiple (B, r) configurations on tamoxifen, imatinib, atorvastatin
to find the best banding for realistic Hamming distance distributions.

Each config splits the 64-bit hash differently:
  - 16x4: 16 bands of 4 bits (most permissive, highest recall, more candidates)
  - 8x8:  8 bands of 8 bits (current default, balanced)
  - 4x16: 4 bands of 16 bits (restrictive, fewer candidates)
  - 2x32: 2 bands of 32 bits (very restrictive)

For each config, measures:
  - Within-molecule recall (true positive rate for same-molecule pairs)
  - Cross-molecule FP rate (false positive rate for different-molecule pairs)
  - Mean candidate count per query (computational cost)
"""

import sys
from pathlib import Path
import json

# Need RDKit env (glycosasa-gpu), so we import csh from parent dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from conformational_soft_hash import ConformationalSoftHash

from rdkit import Chem
from rdkit.Chem import AllChem
import numpy as np


# ─── Configuration ────────────────────────────────────────────────────────────

MOLECULES = {
    "tamoxifen":   "CC/C(=C(/c1ccccc1)\\c2ccc(cc2)OCCN(C)C)/c3ccccc3",
    "imatinib":    "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1",
    "atorvastatin": "CC(C)c1c(C(=O)Nc2ccccc2)c(c3ccccc3)c(c4ccc(F)cc4)n1CC[C@@H](O)C[C@@H](O)CC(=O)O",
}

N_CONFORMERS = 30
THRESHOLDS = [10, 15, 20, 25]

LSH_CONFIGS = [
    (16, 4),   # B × r
    (8, 8),
    (4, 16),
    (2, 32),
]


# ─── LSH banding (parametrized) ───────────────────────────────────────────────

def hash_to_bands(hash_hex: str, num_bands: int, bits_per_band: int) -> list[int]:
    """Split hex hash into B bands of r bits each.
    
    Args:
        hash_hex: e.g. "99b5489a3fc34282" (16 hex chars = 64 bits)
        num_bands: B
        bits_per_band: r
    
    Returns:
        List of B integers, each in [0, 2^r - 1]
    """
    assert num_bands * bits_per_band == 64, "B * r must = 64"
    
    # Convert hex to single 64-bit integer
    value = int(hash_hex, 16)
    
    # Split
    bands = []
    mask = (1 << bits_per_band) - 1
    for i in range(num_bands):
        shift = i * bits_per_band
        bands.append((value >> shift) & mask)
    return bands


def lsh_candidates(query_hash: str, all_hashes: list[str],
                   num_bands: int, bits_per_band: int) -> set:
    """Return set of hash candidates that share at least one band with query.
    
    This simulates the LSH banding step (without exact verification).
    """
    query_bands = hash_to_bands(query_hash, num_bands, bits_per_band)
    
    # Build inverted index: (band_idx, band_value) -> set of hashes
    # (in real implementation this would be persistent SQL)
    candidates = set()
    for h in all_hashes:
        if h == query_hash:
            continue
        h_bands = hash_to_bands(h, num_bands, bits_per_band)
        for i in range(num_bands):
            if h_bands[i] == query_bands[i]:
                candidates.add(h)
                break  # one matching band is enough
    return candidates


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Hamming distance between two 64-bit hex hashes."""
    a = int(hash_a, 16)
    b = int(hash_b, 16)
    return bin(a ^ b).count("1")


# ─── Generate hashes ──────────────────────────────────────────────────────────

def generate_real_hashes() -> dict:
    """Generate real conformer hashes for all molecules.
    
    Returns:
        dict mapping molecule_name -> list of 30 LSH hex strings
    """
    print("Generating real conformer hashes...\n")
    csh = ConformationalSoftHash()
    
    results = {}
    for name, smiles in MOLECULES.items():
        print(f"  Processing {name}...")
        mol = Chem.MolFromSmiles(smiles)
        mol = Chem.AddHs(mol)
        
        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        AllChem.EmbedMultipleConfs(mol, numConfs=N_CONFORMERS, params=params)
        AllChem.MMFFOptimizeMoleculeConfs(mol)
        
        confs = csh.hash_all_conformers(mol)
        results[name] = [c["lsh_hash"] for c in confs]
        print(f"    Got {len(results[name])} hashes")
    
    return results


# ─── Tuning evaluation ────────────────────────────────────────────────────────

def evaluate_config(hashes_by_mol: dict, num_bands: int, bits_per_band: int,
                    thresholds: list[int]) -> dict:
    """Evaluate one LSH config across all molecules and thresholds."""
    
    # Flatten: list of (hash, molecule_name) tuples
    all_hashes = []
    for name, hash_list in hashes_by_mol.items():
        for h in hash_list:
            all_hashes.append((h, name))
    
    all_hash_strs = [h for h, _ in all_hashes]
    
    # Per-threshold metrics
    metrics = {T: {"tp": 0, "fp": 0, "fn": 0, "tn": 0,
                    "candidates_total": 0, "queries": 0}
               for T in thresholds}
    
    for query_hash, query_mol in all_hashes:
        # LSH candidate retrieval
        candidates = lsh_candidates(query_hash, all_hash_strs,
                                     num_bands, bits_per_band)
        
        for T in thresholds:
            metrics[T]["candidates_total"] += len(candidates)
            metrics[T]["queries"] += 1
            
            # For each OTHER hash, check ground truth and LSH+exact
            for other_hash, other_mol in all_hashes:
                if other_hash == query_hash:
                    continue
                
                d = hamming_distance(query_hash, other_hash)
                # Ground truth: same molecule = "should match"
                same_mol = (query_mol == other_mol)
                # LSH says: candidate AND distance <= T
                lsh_says_match = (other_hash in candidates) and (d <= T)
                
                if same_mol and lsh_says_match:
                    metrics[T]["tp"] += 1
                elif same_mol and not lsh_says_match:
                    metrics[T]["fn"] += 1
                elif not same_mol and lsh_says_match:
                    metrics[T]["fp"] += 1
                else:
                    metrics[T]["tn"] += 1
    
    # Compute rates
    results = []
    for T in thresholds:
        m = metrics[T]
        recall = m["tp"] / (m["tp"] + m["fn"]) if (m["tp"] + m["fn"]) > 0 else 0
        # FP rate vs cross-molecule pairs
        fp_rate = m["fp"] / (m["fp"] + m["tn"]) if (m["fp"] + m["tn"]) > 0 else 0
        mean_candidates = m["candidates_total"] / m["queries"]
        
        results.append({
            "threshold": T,
            "tp": m["tp"], "fp": m["fp"], "fn": m["fn"], "tn": m["tn"],
            "within_recall": recall,
            "cross_fp_rate": fp_rate,
            "mean_candidates": mean_candidates,
        })
    
    return results


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("LSH Banding Parameter Tuning")
    print("=" * 70)
    print(f"Molecules: {list(MOLECULES.keys())}")
    print(f"Conformers per molecule: {N_CONFORMERS}")
    print(f"Total hashes: {len(MOLECULES) * N_CONFORMERS}")
    print(f"Configs to test: {LSH_CONFIGS}")
    print()
    
    # Generate hashes once (reuse for all configs)
    hashes_by_mol = generate_real_hashes()
    
    print("\n" + "=" * 70)
    print("Evaluating LSH configurations")
    print("=" * 70)
    
    all_results = {}
    for B, r in LSH_CONFIGS:
        config_name = f"{B}x{r}"
        print(f"\nConfig {config_name}: {B} bands × {r} bits per band")
        print(f"  Possible band values: {2**r}")
        
        config_results = evaluate_config(hashes_by_mol, B, r, THRESHOLDS)
        all_results[config_name] = config_results
        
        print(f"  {'T':>3} | {'recall':>7} | {'cross-FP':>9} | "
              f"{'mean candidates':>16}")
        print(f"  {'---':>3} | {'------':>7} | {'--------':>9} | "
              f"{'---------------':>16}")
        for r_metrics in config_results:
            print(f"  {r_metrics['threshold']:>3} | "
                  f"{r_metrics['within_recall']:>7.3f} | "
                  f"{r_metrics['cross_fp_rate']:>9.3f} | "
                  f"{r_metrics['mean_candidates']:>16.1f}")
    
    # Save results
    output_file = Path(__file__).parent / "lsh_tuning_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "config": {
                "molecules": list(MOLECULES.keys()),
                "n_conformers": N_CONFORMERS,
                "thresholds": THRESHOLDS,
                "lsh_configs": LSH_CONFIGS,
            },
            "results": all_results,
        }, f, indent=2)
    
    print(f"\n{'='*70}")
    print(f"Results saved to: {output_file}")
    print(f"{'='*70}")
    print("\nNext step: analyze trade-offs and pick best config for paper.")


if __name__ == "__main__":
    main()
