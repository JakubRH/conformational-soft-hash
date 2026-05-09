"""Benchmark fuzzy similarity search on the synthetic dataset.

Measures, for each Hamming threshold T:
  - Recall: fraction of true similar pairs found by LSH banding
  - Precision: fraction of returned pairs that are truly similar
  - Latency: mean query time in milliseconds

For our implementation, precision is always 100% (we exact-verify in
find_similar). The interesting metric is recall: does LSH banding miss
any true similar pairs?

Outputs:
  - benchmark_results.json: raw numbers
  - benchmark_results.png: precision-recall and latency plots
"""

import json
import sys
import time
from pathlib import Path

# Add parent dir for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal, ConformerEvent
from lsh import find_similar, hamming_distance


# ─── Configuration ────────────────────────────────────────────────────────────

DATASET_FILE = Path(__file__).parent / "synthetic_dataset.json"
RESULTS_FILE = Path(__file__).parent / "benchmark_results.json"

# Hamming thresholds to test
THRESHOLDS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]

# How many queries to run per threshold (use all family bases by default)
N_QUERIES = 50  # one per family


# ─── Ground truth computation ─────────────────────────────────────────────────

def compute_ground_truth(queries: list[dict], all_hashes: list[str]) -> dict:
    """For each query, compute Hamming distance to every entry in all_hashes.

    Returns:
        {query_hash: {target_hash: hamming_distance}}
    """
    print(f"Computing ground truth: {len(queries)} queries × "
          f"{len(all_hashes)} targets = "
          f"{len(queries) * len(all_hashes)} pairs...")

    ground_truth = {}
    start = time.time()

    for i, query in enumerate(queries):
        q_hash = query["csh_hash"]
        distances = {}
        for target_hash in all_hashes:
            if target_hash == q_hash:
                continue  # don't compare to self
            distances[target_hash] = hamming_distance(q_hash, target_hash)
        ground_truth[q_hash] = distances

        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(queries)} done...")

    elapsed = time.time() - start
    print(f"Ground truth ready in {elapsed:.1f}s")
    return ground_truth


# ─── Benchmark ────────────────────────────────────────────────────────────────

def benchmark_threshold(
    session,
    queries: list[dict],
    ground_truth: dict,
    threshold: int,
) -> dict:
    """Run LSH search for all queries at given threshold, measure metrics."""

    total_true_positive = 0    # found AND in ground truth ≤ T
    total_false_negative = 0   # in ground truth ≤ T but NOT found
    total_false_positive = 0   # found but NOT in ground truth ≤ T (should be 0)
    latencies = []

    for query in queries:
        q_hash = query["csh_hash"]
        gt = ground_truth[q_hash]

        # True similar pairs from ground truth
        true_similar = {h for h, d in gt.items() if d <= threshold}

        # LSH search
        t0 = time.perf_counter()
        results = find_similar(session, q_hash, max_hamming=threshold)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000)  # ms

        # Returned hashes (excluding self if it appears)
        returned = {ev.csh_hash for ev, _ in results if ev.csh_hash != q_hash}

        true_positive = len(returned & true_similar)
        false_negative = len(true_similar - returned)
        false_positive = len(returned - true_similar)

        total_true_positive += true_positive
        total_false_negative += false_negative
        total_false_positive += false_positive

    # Aggregate metrics
    if total_true_positive + total_false_negative == 0:
        recall = 1.0  # nothing to find
    else:
        recall = total_true_positive / (total_true_positive + total_false_negative)

    if total_true_positive + total_false_positive == 0:
        precision = 1.0  # nothing returned
    else:
        precision = total_true_positive / (total_true_positive + total_false_positive)

    return {
        "threshold": threshold,
        "true_positive": total_true_positive,
        "false_negative": total_false_negative,
        "false_positive": total_false_positive,
        "recall": recall,
        "precision": precision,
        "latency_ms_mean": sum(latencies) / len(latencies),
        "latency_ms_min": min(latencies),
        "latency_ms_max": max(latencies),
    }


def main():
    print("=" * 60)
    print("CSH V2 Indexer — Fuzzy Search Benchmark")
    print("=" * 60)

    # Load dataset
    with open(DATASET_FILE) as f:
        dataset = json.load(f)

    # Pick queries: one base hash per family (50 queries total)
    queries = [e for e in dataset if e["variant_id"] == 0][:N_QUERIES]
    print(f"Queries: {len(queries)} (family bases)")

    # All hashes in dataset (targets to search against)
    all_hashes = [e["csh_hash"] for e in dataset]
    print(f"Targets: {len(all_hashes)} (full dataset)")

    # Verify all targets are in DB
    with SessionLocal() as session:
        db_hashes = set(
            row[0] for row in session.query(ConformerEvent.csh_hash).all()
        )
    missing = set(all_hashes) - db_hashes
    if missing:
        print(f"WARNING: {len(missing)} hashes from dataset are NOT in DB!")
        print(f"  Did you run sync.py after batch_register?")
        return
    print(f"✓ All {len(all_hashes)} hashes confirmed in DB")

    # Ground truth
    print()
    ground_truth = compute_ground_truth(queries, all_hashes)

    # Run benchmark for each threshold
    print(f"\nBenchmarking {len(THRESHOLDS)} thresholds...\n")
    results = []

    with SessionLocal() as session:
        for T in THRESHOLDS:
            metrics = benchmark_threshold(session, queries, ground_truth, T)
            results.append(metrics)
            print(f"  T={T:2d}  recall={metrics['recall']:.3f}  "
                  f"precision={metrics['precision']:.3f}  "
                  f"latency={metrics['latency_ms_mean']:.1f}ms  "
                  f"(TP={metrics['true_positive']}, "
                  f"FN={metrics['false_negative']}, "
                  f"FP={metrics['false_positive']})")

    # Save raw results
    output = {
        "config": {
            "n_queries": len(queries),
            "n_targets": len(all_hashes),
            "thresholds": THRESHOLDS,
            "lsh_bands": 8,
            "lsh_bits_per_band": 8,
        },
        "results": results,
    }
    with open(RESULTS_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
