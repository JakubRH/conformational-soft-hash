"""Real-world benchmark: same-molecule recall + cross-molecule FP rate.

Uses the 64 unique real conformer hashes registered on Sepolia
(tamoxifen, imatinib, atorvastatin — 30 conformers each).

Ground truth:
  - Same-molecule pair = should be matched
  - Cross-molecule pair = should NOT be matched

Metrics per threshold T:
  - Within-recall (per molecule, then aggregated)
  - Cross-molecule FP rate
  - Mean query latency

Outputs:
  - benchmark_real_results.json
"""

import json
import sys
import time
from pathlib import Path
from collections import defaultdict

# Add parent dir for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal, ConformerEvent
from lsh import find_similar, hamming_distance


DATASET_FILE = Path(__file__).parent / "real_dataset.json"
RESULTS_FILE = Path(__file__).parent / "benchmark_real_results.json"

# Thresholds — chosen based on observed Hamming distribution
# (within mean ~19, between mean ~32)
THRESHOLDS = [3, 5, 8, 10, 12, 15, 18, 20, 22, 25]


def main():
    print("=" * 60)
    print("Real-world Benchmark — CSH on 3 flexible drugs")
    print("=" * 60)

    # Load dataset
    with open(DATASET_FILE) as f:
        dataset = json.load(f)

    print(f"Dataset entries:   {len(dataset)}")
    
    # Group by molecule for ground truth
    by_molecule = defaultdict(list)  # mol_name -> list of (hash, conformer_id)
    for entry in dataset:
        by_molecule[entry["molecule"]].append(entry["csh_hash"])
    
    molecule_names = list(by_molecule.keys())
    print(f"Molecules: {molecule_names}")
    for name, hashes in by_molecule.items():
        print(f"  {name}: {len(hashes)} conformers")
    
    # Build hash -> molecule lookup for ground truth
    hash_to_molecule = {}
    for mol_name, hashes in by_molecule.items():
        for h in hashes:
            hash_to_molecule[h] = mol_name
    
    # All unique hashes (queries = each unique conformer once)
    # Note: some hashes are shared between conformers within same molecule
    # We use the unique set, ground truth is "same molecule"
    unique_hashes = list(set(hash_to_molecule.keys()))
    print(f"\nUnique hashes: {len(unique_hashes)}")
    
    # Verify all are in DB
    with SessionLocal() as session:
        db_hashes = set(
            row[0] for row in session.query(ConformerEvent.csh_hash).all()
        )
    missing = set(unique_hashes) - db_hashes
    if missing:
        print(f"WARNING: {len(missing)} hashes from dataset are NOT in DB!")
        return
    print(f"✓ All {len(unique_hashes)} hashes confirmed in DB")
    
    # Benchmark
    print(f"\nBenchmarking {len(THRESHOLDS)} thresholds...\n")
    
    results = []
    with SessionLocal() as session:
        for T in THRESHOLDS:
            # Per-molecule stats
            mol_stats = {mol: {"tp": 0, "fn": 0} for mol in molecule_names}
            total_fp = 0
            total_tn = 0
            latencies = []
            
            for query_hash in unique_hashes:
                query_mol = hash_to_molecule[query_hash]
                
                # LSH query
                t0 = time.perf_counter()
                lsh_results = find_similar(session, query_hash, max_hamming=T)
                t1 = time.perf_counter()
                latencies.append((t1 - t0) * 1000)
                
                # Returned hashes (excluding self if appears)
                returned = {ev.csh_hash for ev, _ in lsh_results 
                           if ev.csh_hash != query_hash}
                
                # Filter only those from our real dataset (ignore 600 synthetic)
                returned_real = returned & set(unique_hashes)
                
                # Ground truth: same-molecule pairs
                same_mol_hashes = {h for h in unique_hashes
                                   if h != query_hash and hash_to_molecule[h] == query_mol}
                cross_mol_hashes = {h for h in unique_hashes
                                    if h != query_hash and hash_to_molecule[h] != query_mol}
                
                # Per-molecule TP / FN
                tp = len(returned_real & same_mol_hashes)
                fn = len(same_mol_hashes - returned_real)
                mol_stats[query_mol]["tp"] += tp
                mol_stats[query_mol]["fn"] += fn
                
                # FP / TN (cross-molecule)
                fp = len(returned_real & cross_mol_hashes)
                tn = len(cross_mol_hashes - returned_real)
                total_fp += fp
                total_tn += tn
            
            # Aggregate per-molecule recalls
            mol_recalls = {}
            for mol, stats in mol_stats.items():
                denom = stats["tp"] + stats["fn"]
                mol_recalls[mol] = stats["tp"] / denom if denom > 0 else 0
            
            # Overall recall (micro-averaged)
            total_tp = sum(s["tp"] for s in mol_stats.values())
            total_fn = sum(s["fn"] for s in mol_stats.values())
            overall_recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
            
            fp_rate = total_fp / (total_fp + total_tn) if (total_fp + total_tn) > 0 else 0
            
            result = {
                "threshold": T,
                "overall_recall": overall_recall,
                "per_molecule_recall": mol_recalls,
                "cross_fp_rate": fp_rate,
                "total_tp": total_tp,
                "total_fn": total_fn,
                "total_fp": total_fp,
                "total_tn": total_tn,
                "latency_ms_mean": sum(latencies) / len(latencies),
                "latency_ms_median": sorted(latencies)[len(latencies) // 2],
            }
            results.append(result)
            
            # Print
            mol_str = "  ".join(
                f"{mol[:4]}={r:.2f}" for mol, r in mol_recalls.items()
            )
            print(f"  T={T:2d}  overall={overall_recall:.3f}  "
                  f"FP={fp_rate:.3f}  "
                  f"({mol_str})  "
                  f"latency={result['latency_ms_mean']:.1f}ms")
    
    # Save results
    output = {
        "config": {
            "dataset_file": str(DATASET_FILE),
            "n_unique_hashes": len(unique_hashes),
            "molecules": {mol: len(hashes) for mol, hashes in by_molecule.items()},
            "thresholds": THRESHOLDS,
        },
        "results": results,
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✓ Results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()

