"""
Conformational Soft Hash (CSH) — Proof of Concept
===================================================
Pipeline:
    Molecule + 3D geometry
        → Distance matrix
        → Laplacian graph spectrum (eigenvalues)
        → LSH projection (soft, noise-tolerant)
        → Hex hash string

Key properties:
    - Rotation/translation invariant (distance matrix)
    - Noise-tolerant (LSH, not SHA-256)
    - Similar conformers → similar hashes (soft collision)
    - Ready for blockchain registry (hash as unique ID)

Author: Jakub Hryc (prototype pipeline)
"""

import hashlib
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms
from scipy.linalg import eigvalsh
from sklearn.random_projection import GaussianRandomProjection
from dataclasses import dataclass
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


# ── Configuration ──────────────────────────────────────────────────────────────

@dataclass
class CSHConfig:
    """
    Parameters controlling the hash pipeline.
    Tweak these for your benchmark experiments.
    """
    n_eigenvalues: int = 20        # top-k eigenvalues of Laplacian
    n_lsh_bits: int = 64           # bits in the final hash
    noise_tolerance: float = 0.05  # Angstrom — below this, structure is "same"
    energy_weight: float = 0.1     # how much force-field energy shifts the hash
    random_seed: int = 42


# ── Step 1: Invariant geometric representation ─────────────────────────────────

def build_distance_matrix(conformer) -> np.ndarray:
    """
    Builds pairwise Euclidean distance matrix.
    Invariant to rotation and translation by construction.
    """
    positions = conformer.GetPositions()  # (n_atoms, 3)
    n = len(positions)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = np.linalg.norm(positions[i] - positions[j])
            D[i, j] = d
            D[j, i] = d
    return D


def laplacian_spectrum(D: np.ndarray, mol, cfg: CSHConfig) -> np.ndarray:
    """
    Computes the spectrum of the weighted graph Laplacian.
    Nodes = atoms, edge weights = 1/distance (bonded atoms only).

    This encodes global molecular shape while respecting
    chemical topology — better than raw distance matrix eigenvalues.
    """
    n = D.shape[0]

    # Adjacency matrix: bonded pairs weighted by 1/d
    A = np.zeros((n, n))
    for bond in mol.GetBonds():
        i = bond.GetBeginAtomIdx()
        j = bond.GetEndAtomIdx()
        if D[i, j] > 1e-6:
            w = 1.0 / D[i, j]
            A[i, j] = w
            A[j, i] = w

    # Degree matrix
    deg = np.diag(A.sum(axis=1))

    # Laplacian L = D_deg - A
    L = deg - A

    # Eigenvalues (sorted ascending; λ_0 = 0 for connected graph)
    eigenvalues = eigvalsh(L)

    # Take top-k (skip λ_0 = 0, use the rest)
    k = min(cfg.n_eigenvalues, len(eigenvalues) - 1)
    spectrum = eigenvalues[1:k + 1]

    # Pad if molecule is small
    if len(spectrum) < cfg.n_eigenvalues:
        spectrum = np.pad(spectrum, (0, cfg.n_eigenvalues - len(spectrum)))

    return spectrum


# ── Step 2: Energy feature ─────────────────────────────────────────────────────

def get_mmff_energy(mol, conf_id: int = 0) -> float:
    """
    MMFF94 force-field energy of the conformer.
    Returns 0.0 if calculation fails (e.g. missing params).
    """
    try:
        mol_h = Chem.AddHs(mol)
        ff = AllChem.MMFFGetMoleculeForceField(
            mol_h,
            AllChem.MMFFGetMoleculeProperties(mol_h),
            confId=conf_id
        )
        if ff is None:
            return 0.0
        return ff.CalcEnergy()
    except Exception:
        return 0.0


# ── Step 3: Feature vector ─────────────────────────────────────────────────────

def build_feature_vector(mol, conf_id: int, cfg: CSHConfig) -> np.ndarray:
    """
    Combines spectral geometry + energy into a single feature vector.
    """
    conformer = mol.GetConformer(conf_id)
    D = build_distance_matrix(conformer)
    spectrum = laplacian_spectrum(D, mol, cfg)

    energy = get_mmff_energy(mol, conf_id)
    energy_feature = np.array([energy * cfg.energy_weight])

    # Normalize spectrum to [0, 1] for stable quantization
    s_min, s_max = spectrum.min(), spectrum.max()
    if s_max - s_min > 1e-9:
        spectrum_norm = (spectrum - s_min) / (s_max - s_min)
    else:
        spectrum_norm = spectrum

    return np.concatenate([spectrum_norm, energy_feature])


# ── Step 4: LSH — the "soft" part ──────────────────────────────────────────────

class ConformationalLSH:
    """
    Locality-Sensitive Hashing for molecular conformations.

    Similar conformers (low RMSD) → identical or near-identical hash bits.
    Dissimilar conformers (high RMSD) → different hashes.

    Uses random projection (p-stable LSH for L2 distance).
    """

    def __init__(self, input_dim: int, cfg: CSHConfig):
        self.cfg = cfg
        rng = np.random.RandomState(cfg.random_seed)

        # Random projection matrix: (n_bits, input_dim)
        self.projections = rng.randn(cfg.n_lsh_bits, input_dim)

        # Random offsets for bucketing
        self.offsets = rng.uniform(0, 1, cfg.n_lsh_bits)

        # Bandwidth (controls sensitivity vs. stability tradeoff)
        # Smaller r → more sensitive; larger r → more stable
        self.r = cfg.noise_tolerance * 10

    def project(self, feature_vector: np.ndarray) -> np.ndarray:
        """Returns n_lsh_bits binary values (0 or 1)."""
        projections = self.projections @ feature_vector
        bits = ((projections / self.r) + self.offsets).astype(int) % 2
        return bits.astype(np.uint8)

    def bits_to_hex(self, bits: np.ndarray) -> str:
        """Converts bit array to hex string for blockchain storage."""
        # Pack bits into bytes
        n_bytes = (len(bits) + 7) // 8
        byte_array = np.packbits(bits, bitorder='big')[:n_bytes]
        return byte_array.tobytes().hex()


# ── Step 5: Main hash function ─────────────────────────────────────────────────

class ConformationalSoftHash:
    """
    Main class. Call hash_conformer() for each structure.

    Example
    -------
    >>> csh = ConformationalSoftHash()
    >>> mol = Chem.MolFromSmiles("CC(=O)Oc1ccccc1C(=O)O")  # Aspirin
    >>> mol = Chem.AddHs(mol)
    >>> AllChem.EmbedMultipleConfs(mol, numConfs=5)
    >>> results = csh.hash_all_conformers(mol)
    """

    def __init__(self, cfg: Optional[CSHConfig] = None):
        self.cfg = cfg or CSHConfig()
        self._lsh = None  # initialized lazily on first call

    def _init_lsh(self, feature_dim: int):
        if self._lsh is None:
            self._lsh = ConformationalLSH(feature_dim, self.cfg)

    def hash_conformer(self, mol, conf_id: int = 0) -> dict:
        """
        Full pipeline for a single conformer.

        Returns
        -------
        dict with:
            'lsh_hash'    : hex string (for blockchain / similarity search)
            'sha256_id'   : deterministic unique ID (for exact deduplication)
            'feature_vec' : numpy array (for downstream ML)
            'energy'      : MMFF94 energy
            'conf_id'     : conformer index
        """
        fvec = build_feature_vector(mol, conf_id, self.cfg)
        self._init_lsh(len(fvec))

        bits = self._lsh.project(fvec)
        lsh_hex = self._lsh.bits_to_hex(bits)

        # SHA-256 for exact deduplication (brittle but useful for identity check)
        sha_input = fvec.tobytes()
        sha256_id = hashlib.sha256(sha_input).hexdigest()

        energy = get_mmff_energy(mol, conf_id)

        return {
            "lsh_hash": lsh_hex,
            "sha256_id": sha256_id,
            "feature_vec": fvec,
            "energy": energy,
            "conf_id": conf_id,
        }

    def hash_all_conformers(self, mol) -> list[dict]:
        """Hashes all conformers in a molecule object."""
        results = []
        for conf_id in range(mol.GetNumConformers()):
            results.append(self.hash_conformer(mol, conf_id))
        return results

    def hamming_distance(self, hash_a: str, hash_b: str) -> int:
        """
        Bit-level distance between two LSH hashes.
        Low distance → similar conformers.
        """
        ba = bytes.fromhex(hash_a)
        bb = bytes.fromhex(hash_b)
        dist = 0
        for x, y in zip(ba, bb):
            dist += bin(x ^ y).count('1')
        return dist

    def collision_probability(self, hash_a: str, hash_b: str) -> float:
        """
        Fraction of bits that match. Range [0, 1].
        1.0 = identical hash (soft collision).
        """
        n_bits = len(hash_a) * 4  # hex → bits
        hamming = self.hamming_distance(hash_a, hash_b)
        return 1.0 - hamming / n_bits


# ── Demo / quick benchmark ─────────────────────────────────────────────────────

def demo_aspirin():
    """
    Generates 10 conformers of aspirin, hashes them,
    and shows pairwise collision probabilities.
    """
    print("=" * 60)
    print("Conformational Soft Hash — Demo (Aspirin)")
    print("=" * 60)

    smiles = "CC(=O)Oc1ccccc1C(=O)O"
    mol = Chem.MolFromSmiles(smiles)
    mol = Chem.AddHs(mol)

    # Generate conformers
    params = AllChem.ETKDGv3()
    params.randomSeed = 42
    conf_ids = AllChem.EmbedMultipleConfs(mol, numConfs=10, params=params)
    AllChem.MMFFOptimizeMoleculeConfs(mol)

    print(f"Generated {mol.GetNumConformers()} conformers\n")

    csh = ConformationalSoftHash()
    results = csh.hash_all_conformers(mol)

    print(f"{'Conf':>5} | {'LSH Hash':>18} | {'Energy (kcal/mol)':>18}")
    print("-" * 50)
    for r in results:
        print(f"{r['conf_id']:>5} | {r['lsh_hash'][:16]}... | {r['energy']:>18.3f}")

    print("\nPairwise collision probabilities (first 5 conformers):")
    print(f"{'':>8}", end="")
    for j in range(5):
        print(f"  Conf{j:>2}", end="")
    print()
    for i in range(5):
        print(f"Conf{i:>2}  ", end="")
        for j in range(5):
            p = csh.collision_probability(results[i]["lsh_hash"], results[j]["lsh_hash"])
            print(f"  {p:.3f} ", end="")
        print()

    print("\n✓ Diagonal = 1.000 (identical conformer hashes itself perfectly)")
    print("✓ Off-diagonal values show soft similarity between conformers")
    print("\nBlockchain-ready hash (LSH hex, 64 bits):")
    print(f"  Conformer 0: {results[0]['lsh_hash']}")
    print(f"  Conformer 1: {results[1]['lsh_hash']}")
    print(f"  SHA-256 ID (exact dedup): {results[0]['sha256_id'][:32]}...")

    return results, csh


if __name__ == "__main__":
    demo_aspirin()
