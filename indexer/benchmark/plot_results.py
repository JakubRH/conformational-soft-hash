"""Generate paper-ready plots from benchmark_results.json.

Produces:
  - recall_precision.png: recall and precision vs threshold
  - latency.png: query latency vs threshold
  - confusion.png: TP / FN / FP breakdown
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib

# Use a clean, paper-friendly style
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

RESULTS_FILE = Path(__file__).parent / "benchmark_results.json"


def load_results():
    with open(RESULTS_FILE) as f:
        return json.load(f)


def plot_recall_precision(data):
    """Recall and precision vs threshold."""
    results = data["results"]
    T = [r["threshold"] for r in results]
    recall = [r["recall"] for r in results]
    precision = [r["precision"] for r in results]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(T, recall, "o-", color="#2E86AB", linewidth=2.5,
            markersize=8, label="Recall")
    ax.plot(T, precision, "s--", color="#A23B72", linewidth=2,
            markersize=7, label="Precision")

    ax.set_xlabel("Hamming distance threshold $T$")
    ax.set_ylabel("Metric value")
    ax.set_ylim(-0.05, 1.05)
    ax.set_xticks(T)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower left")
    ax.set_title(f"LSH banding fuzzy search: recall and precision\n"
                 f"({data['config']['n_queries']} queries × "
                 f"{data['config']['n_targets']} targets, "
                 f"{data['config']['lsh_bands']}×"
                 f"{data['config']['lsh_bits_per_band']} banding)")

    plt.tight_layout()
    out = Path(__file__).parent / "recall_precision.png"
    plt.savefig(out)
    print(f"Saved: {out}")
    plt.close()


def plot_latency(data):
    """Query latency vs threshold."""
    results = data["results"]
    T = [r["threshold"] for r in results]
    mean = [r["latency_ms_mean"] for r in results]
    lo = [r["latency_ms_min"] for r in results]
    hi = [r["latency_ms_max"] for r in results]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.fill_between(T, lo, hi, alpha=0.2, color="#F18F01",
                     label="Min–max range")
    ax.plot(T, mean, "o-", color="#F18F01", linewidth=2.5,
            markersize=8, label="Mean latency")

    ax.set_xlabel("Hamming distance threshold $T$")
    ax.set_ylabel("Query latency (ms)")
    ax.set_xticks(T)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left")
    ax.set_title(f"LSH fuzzy search: query latency\n"
                 f"({data['config']['n_queries']} queries × "
                 f"{data['config']['n_targets']} targets)")

    plt.tight_layout()
    out = Path(__file__).parent / "latency.png"
    plt.savefig(out)
    print(f"Saved: {out}")
    plt.close()


def plot_confusion(data):
    """TP / FN / FP per threshold (stacked or grouped bars)."""
    results = data["results"]
    T = [r["threshold"] for r in results]
    tp = [r["true_positive"] for r in results]
    fn = [r["false_negative"] for r in results]
    fp = [r["false_positive"] for r in results]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    width = 0.6
    x = list(range(len(T)))

    ax.bar(x, tp, width, label="True Positive",
           color="#2E86AB")
    ax.bar(x, fn, width, bottom=tp, label="False Negative",
           color="#E63946")
    # FP should always be 0 for our impl, but plot for completeness
    ax.bar(x, fp, width, bottom=[a + b for a, b in zip(tp, fn)],
           label="False Positive", color="#F4A261")

    ax.set_xticks(x)
    ax.set_xticklabels([str(t) for t in T])
    ax.set_xlabel("Hamming distance threshold $T$")
    ax.set_ylabel("Number of pairs")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_title("LSH fuzzy search: classification breakdown")

    plt.tight_layout()
    out = Path(__file__).parent / "confusion.png"
    plt.savefig(out)
    print(f"Saved: {out}")
    plt.close()


def main():
    data = load_results()
    print(f"Loaded results from {RESULTS_FILE}")
    print(f"Configuration: {data['config']}\n")

    plot_recall_precision(data)
    plot_latency(data)
    plot_confusion(data)

    print(f"\n✓ All plots saved.")


if __name__ == "__main__":
    main()
