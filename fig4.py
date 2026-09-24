#!/usr/bin/env python3
"""Redraw Figure 4: the CSH pipeline and the collection-scoped registry.

Two things differ from the superseded version beyond the bit count. The scaling
and projection are fitted on a reference ensemble built from the molecule
itself, not on a global one, and that per-molecule fit is what makes hashes
comparable only within a molecule. The registry therefore scopes every record
to a collection identified by the molecule and the transform version.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BLUE, PURPLE, ORANGE, GREEN = "#5899dc", "#8574ef", "#e9af48", "#48c97c"
GREY = "#4a4a4a"

fig, ax = plt.subplots(figsize=(9.2, 11.6), dpi=300)
ax.set_xlim(0, 100)
ax.set_ylim(0, 132)
ax.axis("off")


def box(x, y, w, h, colour, title, sub=None, fs=13, subfs=9.5, alpha=1.0):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.6",
        facecolor=colour, edgecolor="none", alpha=alpha))
    ty = y + h / 2 + (1.6 if sub else 0)
    ax.text(x + w / 2, ty, title, ha="center", va="center",
            fontsize=fs, fontweight="bold", color="white")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 2.6, sub, ha="center", va="center",
                fontsize=subfs, color="white")


def arrow(x, y0, y1, style="-", colour=GREY):
    ax.add_patch(FancyArrowPatch(
        (x, y0), (x, y1), arrowstyle="-|>", mutation_scale=15,
        linewidth=1.6, color=colour, linestyle=style,
        shrinkA=0, shrinkB=0))


ax.text(50, 128.5, "Conformational Soft Hash: pipeline and registry",
        ha="center", fontsize=15, fontweight="bold", color="#222222")

# ------------------------------------------------------------- main pipeline
X, W = 26, 48
box(X, 114, W, 9.5, BLUE, "3D conformer",
    "RDKit ETKDGv3 + MMFF94, heavy atoms")
arrow(50, 113.4, 109.4)

box(X, 99.5, W, 9.5, PURPLE, "Feature vector",
    "all pairwise distances + torsions + energy")
arrow(50, 98.9, 94.9)

box(X, 85, W, 9.5, PURPLE, "Scale + PCA",
    "32 components, fitted per molecule")
arrow(50, 84.4, 80.4)

box(X, 70.5, W, 9.5, ORANGE, "CSH hash",
    "SimHash, 256 bits = one 32-byte slot")
arrow(50, 69.9, 65.9)

box(X, 56, W, 9.5, ORANGE, "SHA-256 identifier",
    "exact identity and deduplication")
arrow(50, 55.4, 51.4)

box(X, 41.5, W, 9.5, GREEN, "Registry collection",
    "keyed by (molecule, transform version)")

# ------------------------------------- reference ensemble feeding the fit
ax.add_patch(FancyBboxPatch(
    (1.5, 83.5), 21, 12.5, boxstyle="round,pad=0.6,rounding_size=1.6",
    facecolor=PURPLE, edgecolor="none", alpha=0.72))
ax.text(12, 92.6, "Reference ensemble", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color="white")
ax.text(12, 88.2, "50 conformers built\nfrom SMILES with a\nfixed seed",
        ha="center", va="center", fontsize=8.2, color="white")
ax.add_patch(FancyArrowPatch(
    (23.0, 89.8), (25.4, 89.8), arrowstyle="-|>", mutation_scale=13,
    linewidth=1.5, color=GREY))
ax.text(12, 82.2, "fitted here, not globally",
        ha="center", va="top", fontsize=8.5, style="italic", color="#666666")

# the consequence, called out beside the hash
ax.text(77.5, 75.2,
        "Because the projection is fitted\n"
        "to one molecule, hashes of two\n"
        "molecules share no frame of\n"
        "reference and their Hamming\n"
        "distance is not interpretable.",
        ha="left", va="center", fontsize=8.5, color="#666666")
ax.plot([74.5, 74.5], [69.5, 81], color="#cccccc", linewidth=1)

# ------------------------------------------------------------- on-chain record
ax.add_patch(FancyArrowPatch(
    (50, 40.9), (50, 33.5), arrowstyle="-|>", mutation_scale=15,
    linewidth=1.6, color=GREEN, linestyle=(0, (4, 3))))
ax.text(50, 37.2, "on-chain record", ha="center", va="center",
        fontsize=9.5, style="italic", color="#444444",
        bbox=dict(facecolor="white", edgecolor="none", pad=1.5))

fields = [("molecule", "Ketamine"), ("transform", "csh2 | heavy |\npca32 | bits256"),
          ("cshHash", "bytes32"), ("sha256Id", "bytes32"),
          ("energy", "kcal/mol × 1000"), ("timestamp", "block time")]
fw, gap = 14.2, 1.4
total = len(fields) * fw + (len(fields) - 1) * gap
x0 = (100 - total) / 2
for i, (k, v) in enumerate(fields):
    x = x0 + i * (fw + gap)
    ax.add_patch(FancyBboxPatch(
        (x, 23), fw, 9.2, boxstyle="round,pad=0.5,rounding_size=1.2",
        facecolor=GREEN, edgecolor="none"))
    ax.text(x + fw / 2, 29.4, k, ha="center", va="center",
            fontsize=8.5, fontweight="bold", color="white")
    ax.text(x + fw / 2, 26.0, v, ha="center", va="center",
            fontsize=6.8, color="white", linespacing=1.35)

ax.text(x0, 20.6, "Ethereum registry (Sepolia)", ha="left", va="top",
        fontsize=11, fontweight="bold", color="#2f9e63")

# ------------------------------------------------------------- scoping note
ax.text(50, 15.5,
        "Conformers are always registered into a collection. No contract "
        "function compares hashes\nacross collections, so the scope of the "
        "representation is enforced by the registry itself.",
        ha="center", va="top", fontsize=9, color="#555555")

plt.tight_layout()
fig.savefig("figure3_pipeline.png", dpi=300, facecolor="white",
            bbox_inches="tight")
print("wrote figure3_pipeline.png")
