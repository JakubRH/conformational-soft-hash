"""Generate paper-ready plots from benchmark_real_results.json.

Three figures:
  - recall_per_molecule.png: per-molecule recall vs threshold
  - fp_vs_recall.png: trade-off curve (FP rate vs overall recall)
  - synthetic_vs_real.png: comparison with synthetic benchmark
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib

matplotlib.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 12,
    "axes.titlesize": 13,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.dpi": 100,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

REAL_RESULTS = Path(__file__).parent / "benchmark_real_results.json"
SYNTHETIC_RESULTS = Path(__file__).parent / "benchmark_results.json"


def plot_recall_per_molecule(data):
    """Per-molecule recall vs threshold."""
    results = data["results"]
    T = [r["threshold"] for r in results]
    
    molecules = list(results[0]["per_molecule_recall"].keys())
    colors = {"tamoxifen": "#2E86AB", "imatinib": "#A23B72", "atorvastatin": "#F18F01"}
    markers = {"tamoxifen": "o", "imatinib": "s", "atorvastatin": "^"}
    
    fig, ax = plt.subplots(figsize=(7, 4.5))
    
    for mol in molecules:
        recalls = [r["per_molecule_recall"][mol] for r in results]
        ax.plot(T, recalls, marker=markers[mol], linewidth=2.5,
                markersize=8, color=colors[mol], label=mol.capitalize())
    
    # Overall recall as gray dashed
    overall = [r["overall_recall"] for r in results]
    ax.plot(T, overall, "k--", linewidth=2, alpha=0.6, label="Overall (mean)")
    
    ax.set_xlabel("Hamming distance threshold $T$")
    ax.set_ylabel("Within-molecule recall")
    ax.set_ylim(-0.02, 0.70)
    ax.set_xticks(T)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    ax.set_title(f"CSH same-molecule recall on real conformers\n"
                 f"(3 drugs × 30 conformers, {data['config']['n_unique_hashes']} unique hashes)")
    
    plt.tight_layout()
    out = Path(__file__).parent / "recall_per_molecule.png"
    plt.savefig(out)
    print(f"Saved: {out}")
    plt.close()


def plot_fp_vs_recall(data):
    """Trade-off: overall recall vs cross-molecule FP rate."""
    results = data["results"]
    T = [r["threshold"] for r in results]
    recalls = [r["overall_recall"] for r in results]
    fp_rates = [r["cross_fp_rate"] for r in results]
    
    fig, ax = plt.subplots(figsize=(7, 4.5))
    
    # Plot trade-off curve
    ax.plot(fp_rates, recalls, "o-", color="#2E86AB",
            linewidth=2.5, markersize=10)
    
    # Annotate each point with threshold
    for t, r, fp in zip(T, recalls, fp_rates):
        ax.annotate(f"T={t}", (fp, r),
                    textcoords="offset points",
                    xytext=(8, 5), fontsize=9, color="#444")
    
    ax.set_xlabel("Cross-molecule false positive rate")
    ax.set_ylabel("Same-molecule recall")
    ax.set_xlim(-0.001, max(fp_rates) * 1.2 + 0.005)
    ax.set_ylim(-0.02, 0.70)
    ax.grid(True, alpha=0.3)
    ax.set_title("CSH trade-off: same-molecule recall vs cross-molecule FP\n"
                 "(real conformer data, 3 flexible drugs)")
    
    # Highlight optimal region (low FP, decent recall)
    ax.axvspan(-0.001, 0.005, alpha=0.1, color="green",
               label="Optimal: FP < 0.5%")
    ax.legend(loc="lower right")
    
    plt.tight_layout()
    out = Path(__file__).parent / "fp_vs_recall.png"
    plt.savefig(out)
    print(f"Saved: {out}")
    plt.close()


def plot_synthetic_vs_real(real_data):
    """Side-by-side: synthetic benchmark vs real benchmark."""
    if not SYNTHETIC_RESULTS.exists():
        print(f"  (skipping synthetic comparison — {SYNTHETIC_RESULTS.name} not found)")
        return
    
    with open(SYNTHETIC_RESULTS) as f:
        synth_data = json.load(f)
    
    fig, ax = plt.subplots(figsize=(7, 4.5))
    
    # Synthetic
    synth_T = [r["threshold"] for r in synth_data["results"]]
    synth_recall = [r["recall"] for r in synth_data["results"]]
    ax.plot(synth_T, synth_recall, "o-", color="#2E86AB",
            linewidth=2.5, markersize=8, label="Synthetic dataset (controlled H)")
    
    # Real
    real_T = [r["threshold"] for r in real_data["results"]]
    real_recall = [r["overall_recall"] for r in real_data["results"]]
    ax.plot(real_T, real_recall, "s-", color="#A23B72",
            linewidth=2.5, markersize=8, label="Real conformers (3 drugs)")
    
    ax.set_xlabel("Hamming distance threshold $T$")
    ax.set_ylabel("Same-molecule / matching recall")
    ax.set_ylim(-0.05, 1.05)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")
    ax.set_title("LSH banding recall: synthetic vs real conformer data\n"
                 "(synthetic = controlled Hamming, real = natural distribution)")
    
    plt.tight_layout()
    out = Path(__file__).parent / "synthetic_vs_real.png"
    plt.savefig(out)
    print(f"Saved: {out}")
    plt.close()


def main():
    with open(REAL_RESULTS) as f:
        real_data = json.load(f)
    
    print(f"Loaded results from {REAL_RESULTS}\n")
    
    plot_recall_per_molecule(real_data)
    plot_fp_vs_recall(real_data)
    plot_synthetic_vs_real(real_data)
    
    print(f"\n✓ All plots saved.")


if __name__ == "__main__":
    main()
