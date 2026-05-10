"""Generate real-world conformer dataset for blockchain registration.

Uses RDKit + ConformationalSoftHash to produce 30 conformers each for:
  - tamoxifen
  - imatinib
  - atorvastatin

Output format matches synthetic_dataset.json (compatible with batch_register.py).

CSH produces 16-hex (64-bit) hashes; we pad to 64-hex (256-bit / bytes32)
for the contract by appending zeros.
"""

import hashlib
import json
import sys
from pathlib import Path

# CSH module is in repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from conformational_soft_hash import ConformationalSoftHash

from rdkit import Chem
from rdkit.Chem import AllChem


# ─── Configuration ────────────────────────────────────────────────────────────

MOLECULES = [
    ("tamoxifen",   "CC/C(=C(/c1ccccc1)\\c2ccc(cc2)OCCN(C)C)/c3ccccc3"),
    ("imatinib",    "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1"),
    ("atorvastatin", "CC(C)c1c(C(=O)Nc2ccccc2)c(c3ccccc3)c(c4ccc(F)cc4)n1CC[C@@H](O)C[C@@H](O)CC(=O)O"),
]
N_CONFORMERS = 30
SEED = 42

OUTPUT_FILE = Path(__file__).parent / "real_dataset.json"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def csh_to_bytes32(csh_hash: str) -> str:
    """Convert 16-hex CSH hash to 64-hex bytes32 format (with zero padding).
    
    Contract uses bytes32 (256 bits); CSH is 64 bits (16 hex chars).
    We put CSH bits in the LOW 8 bytes, pad zeros above.
    """
    assert len(csh_hash) == 16, f"Expected 16 hex chars, got {len(csh_hash)}"
    padding = "0" * (64 - 16)
    return "0x" + csh_hash + padding


# ─── Generation ───────────────────────────────────────────────────────────────

def generate():
    print("Generating real conformer dataset...\n")
    csh = ConformationalSoftHash()
    entries = []
    
    for fam_id, (mol_name, smiles) in enumerate(MOLECULES):
        print(f"  [{fam_id}] {mol_name}")
        mol = Chem.MolFromSmiles(smiles)
        mol = Chem.AddHs(mol)
        
        params = AllChem.ETKDGv3()
        params.randomSeed = SEED
        AllChem.EmbedMultipleConfs(mol, numConfs=N_CONFORMERS, params=params)
        AllChem.MMFFOptimizeMoleculeConfs(mol)
        
        results = csh.hash_all_conformers(mol)
        print(f"      Got {len(results)} conformers")
        
        for var_id, r in enumerate(results):
            csh_hash_64 = r["lsh_hash"]                  # 16 hex chars
            csh_hash_bytes32 = csh_to_bytes32(csh_hash_64)  # 0x + 64 hex
            
            # SHA-256 ID: deterministic, used for exact dedup on contract
            sha256_id = r["sha256_id"][:32]   # 32 chars (matches synthetic format)
            
            # Energy as int (multiply by 1000, clamp to int range)
            energy_x1000 = int(r["energy"] * 1000)
            
            entries.append({
                "csh_hash": csh_hash_bytes32,
                "molecule_name": f"{mol_name}_conf{var_id:02d}",
                "sha256_id": sha256_id,
                "energy_x1000": energy_x1000,
                # Provenance for ground truth
                "family_id": fam_id,
                "variant_id": var_id,
                "molecule": mol_name,
                "csh_hash_raw_64bit": csh_hash_64,  # for reference
            })
    
    # Sanity check: detect duplicate hashes (would fail registration)
    all_hashes = [e["csh_hash"] for e in entries]
    n_unique = len(set(all_hashes))
    n_total = len(all_hashes)
    
    print(f"\n  Total entries:    {n_total}")
    print(f"  Unique hashes:    {n_unique}")
    print(f"  Duplicates:       {n_total - n_unique}")
    
    if n_unique != n_total:
        # Find which ones duplicate
        from collections import Counter
        counts = Counter(all_hashes)
        dups = [h for h, c in counts.items() if c > 1]
        print(f"\n  WARNING: {len(dups)} hash(es) appear in multiple conformers")
        print(f"  These will fail blockchain registration ('already registered')")
        print(f"  We'll filter them in batch_register.py — keeping first occurrence")
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(entries, f, indent=2)
    
    estimated_cost = n_unique * 0.000023
    print(f"\n  Saved to: {OUTPUT_FILE}")
    print(f"  Estimated registration cost: {estimated_cost:.6f} ETH "
          f"({n_unique} unique hashes)")


if __name__ == "__main__":
    generate()
