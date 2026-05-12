"""Adversarial analysis: cross-molecule hash collision rate.

Tests whether different molecules can produce identical or near-identical
CSH hashes — which would mean publishing a hash leaks information about
the underlying molecule.

Setup: 28 drug molecules from V1 benchmark, 5 conformers each (140 hashes).
Measure pairwise Hamming distance distribution for cross-molecule pairs.

Strong result if cross-molecule mean H is far from zero (e.g., > 25).
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

# CSH module in repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from conformational_soft_hash import ConformationalSoftHash

from rdkit import Chem
from rdkit.Chem import AllChem
import numpy as np


# 28 molecules from V1 paper (Table 1)
MOLECULES = {
    "aspirin":      "CC(=O)Oc1ccccc1C(=O)O",
    "paracetamol":  "CC(=O)Nc1ccc(O)cc1",
    "caffeine":     "Cn1cnc2c1c(=O)n(C)c(=O)n2C",
    "phenol":       "Oc1ccccc1",
    "aniline":      "Nc1ccccc1",
    "ibuprofen":    "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
    "diazepam":     "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21",
    "naproxen":     "COc1ccc2cc(C(C)C(=O)O)ccc2c1",
    "ketoprofen":   "CC(C(=O)O)c1cccc(C(=O)c2ccccc2)c1",
    "lorazepam":    "OC1N=C(c2ccccc2Cl)c2cc(Cl)ccc2NC1=O",
    "warfarin":     "CC(=O)CC(c1ccccc1)C1=C(O)c2ccccc2OC1=O",
    "metformin":    "CN(C)C(=N)NC(=N)N",
    "lidocaine":    "CCN(CC)CC(=O)Nc1c(C)cccc1C",
    "propranolol":  "CC(C)NCC(O)COc1cccc2ccccc12",
    "atenolol":     "CC(C)NCC(O)COc1ccc(CC(N)=O)cc1",
    "tamoxifen":    "CC/C(=C(/c1ccccc1)\\c2ccc(cc2)OCCN(C)C)/c3ccccc3",
    "imatinib":     "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1",
    "amlodipine":   "CCOC(=O)C1=C(COCCN)NC(C)=C(C(=O)OC)C1c1ccccc1Cl",
    "sildenafil":   "CCCc1nn(C)c2c1nc(-c1cc(S(=O)(=O)N3CCN(C)CC3)ccc1OCC)[nH]c2=O",
    "valsartan":    "CCCCC(=O)N(Cc1ccc(-c2ccccc2-c2nnn[nH]2)cc1)C(C(C)C)C(=O)O",
    "losartan":     "CCCCc1nc(Cl)c(CO)n1Cc1ccc(-c2ccccc2-c2nnn[nH]2)cc1",
    "celecoxib":    "Cc1ccc(-c2cc(C(F)(F)F)nn2-c2ccc(S(N)(=O)=O)cc2)cc1",
    "atorvastatin": "CC(C)c1c(C(=O)Nc2ccccc2)c(c3ccccc3)c(c4ccc(F)cc4)n1CC[C@@H](O)C[C@@H](O)CC(=O)O",
    "haloperidol":  "OC1(CCN(CCCC(=O)c2ccc(F)cc2)CC1)c1ccc(Cl)cc1",
    "risperidone":  "CC1=C(CCN2CCC(c3noc4cc(F)ccc34)CC2)C(=O)N2CCCCC2=N1",
    "ciprofloxacin": "O=C(O)c1cn(C2CC2)c2cc(N3CCNCC3)c(F)cc2c1=O",
}

N_CONFORMERS = 5
OUTPUT_FILE = Path(__file__).parent / "adversarial_collisions_results.json"


def main():
    print("=" * 60)
    print("Adversarial Analysis: Cross-Molecule Hash Collisions")
    print("=" * 60)
    print(f"Molecules: {len(MOLECULES)}")
    print(f"Conformers per molecule: {N_CONFORMERS}")
    print(f"Total hashes: {len(MOLECULES) * N_CONFORMERS}")
    print()

    csh = ConformationalSoftHash()
    all_hashes = []  # list of (hash, molecule_name)

    # Generate
    print("Generating hashes...")
    for name, smiles in MOLECULES.items():
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"  [SKIP] {name}: SMILES parse error")
            continue
        mol = Chem.AddHs(mol)

        params = AllChem.ETKDGv3()
        params.randomSeed = 42
        conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=N_CONFORMERS, params=params)
        if len(conf_ids) == 0:
            print(f"  [SKIP] {name}: embedding failed")
            continue

        try:
            AllChem.MMFFOptimizeMoleculeConfs(mol)
        except Exception as e:
            print(f"  [WARN] {name}: MMFF failed, using embedded: {e}")

        results = csh.hash_all_conformers(mol)
        for r in results:
            all_hashes.append((r["lsh_hash"], name))

        print(f"  {name:20s} {len(results)} hashes")

    print(f"\nTotal hashes generated: {len(all_hashes)}")

    # Pairwise distances
    print("\nComputing pairwise Hamming distances...")
    within_distances = []
    cross_distances = []

    for i in range(len(all_hashes)):
        h_i, mol_i = all_hashes[i]
        for j in range(i + 1, len(all_hashes)):
            h_j, mol_j = all_hashes[j]
            d = csh.hamming_distance(h_i, h_j)
            if mol_i == mol_j:
                within_distances.append(d)
            else:
                cross_distances.append(d)

    print(f"  Within-molecule pairs: {len(within_distances)}")
    print(f"  Cross-molecule pairs:  {len(cross_distances)}")

    # Statistics
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    if within_distances:
        print(f"\nWithin-molecule Hamming:")
        print(f"  Mean: {np.mean(within_distances):.1f}")
        print(f"  Std:  {np.std(within_distances):.1f}")
        print(f"  Min:  {min(within_distances)}  Max: {max(within_distances)}")

    print(f"\nCross-molecule Hamming:")
    print(f"  Mean: {np.mean(cross_distances):.1f}")
    print(f"  Std:  {np.std(cross_distances):.1f}")
    print(f"  Min:  {min(cross_distances)}  Max: {max(cross_distances)}")

    # Collision analysis: how many cross-molecule pairs are "too close"?
    print("\nCross-molecule collision rate at various thresholds:")
    print(f"  {'H ≤':>6} | {'Pairs':>8} | {'% of cross-pairs':>17}")
    print("  " + "-" * 38)
    n_cross = len(cross_distances)
    collisions_at = {}
    for thresh in [0, 3, 5, 8, 10, 15, 20]:
        count = sum(1 for d in cross_distances if d <= thresh)
        pct = 100 * count / n_cross
        collisions_at[thresh] = {"count": count, "pct": pct}
        print(f"  {thresh:>6} | {count:>8} | {pct:>16.2f}%")

    # Save results
    output = {
        "config": {
            "n_molecules": len(MOLECULES),
            "n_conformers_per_molecule": N_CONFORMERS,
            "total_hashes": len(all_hashes),
        },
        "within_molecule": {
            "n_pairs": len(within_distances),
            "mean": float(np.mean(within_distances)) if within_distances else None,
            "std": float(np.std(within_distances)) if within_distances else None,
            "min": int(min(within_distances)) if within_distances else None,
            "max": int(max(within_distances)) if within_distances else None,
        },
        "cross_molecule": {
            "n_pairs": len(cross_distances),
            "mean": float(np.mean(cross_distances)),
            "std": float(np.std(cross_distances)),
            "min": int(min(cross_distances)),
            "max": int(max(cross_distances)),
        },
        "cross_collisions_at_threshold": collisions_at,
        "all_within_distances": within_distances,
        "all_cross_distances": cross_distances,
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Results saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
