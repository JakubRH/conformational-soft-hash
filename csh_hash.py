#!/usr/bin/env python
# coding: utf-8
"""
==============================================================================
csh_hash.py — Canonical CSH pipeline v2 (single source of truth)
==============================================================================

THE PROBLEM THIS VERSION FIXES
------------------------------
The original pipeline fitted StandardScaler + PCA to *each molecule's own
conformer set*. That inflated benchmark performance and, more seriously, meant
two users computing the same geometry got different hashes — which breaks the
premise of a shared registry.

A first correction removed the fitted transform entirely (fixed scaling, frozen
projection). That restored reproducibility but destroyed sensitivity: without
centering, the projection is dominated by the constant part of the interatomic
distances, so conformers of one molecule collapsed onto one or two hashes.

v2 keeps both properties. The transform is still fitted — but to a CANONICAL
REFERENCE ENSEMBLE that is a deterministic function of the molecule, not of the
user's data. Same molecule -> same reference ensemble -> same transform -> same
hash, for everyone.

THE SPEC (frozen; changing any constant changes CSH)
----------------------------------------------------
1. REFERENCE ENSEMBLE. REF_N_CONFS conformers generated with ETKDGv3 at
   REF_SEED and MMFF94-optimised, from the molecule's SMILES. Deterministic.
   REF_SEED differs from any benchmark seed so the reference is never the data
   being evaluated.
2. CANONICAL ATOM ORDER. RDKit canonical graph ranks (chirality-aware, ties not
   broken by graph) as primary key; ties between symmetry-equivalent atoms
   broken by a rotation-invariant geometric key (sum of 3D distances to all
   atoms). Verified by the round-trip self-test.
3. HEAVY ATOMS. Hydrogen positions are largely an artefact of force-field
   relaxation rather than distinct conformational states, and using heavy atoms
   lets every method in the benchmark see exactly the same atoms. Set
   heavy=False for the all-atom variant.
4. CONFORMATION-CARRYING PAIRS ONLY. Atom pairs closer than MIN_TOPO bonds are
   excluded: 1-2 and 1-3 distances are fixed by topology and only add constants.
5. FEATURES: raw pairwise distances + (sin, cos) per rotatable torsion.
   No force-field energy — it is software-version dependent and would flip bits
   between users; it stays as registry metadata instead.
6. TRANSFORM: StandardScaler + PCA(PCA_DIMS), both fitted on the reference
   ensemble of step 1 and then applied unchanged to the conformer being hashed.
7. PROJECTION: 256 SimHash hyperplanes from numpy RandomState(PROJECTION_SEED).
   Publishing the seed and procedure IS publishing the projection.

KNOWN LIMITATIONS (state these in any write-up)
-----------------------------------------------
- The transform is molecule-specific. Hashes of the same molecule are directly
  comparable across users; hashes of different molecules are not on a common
  axis system. (The original published pipeline had this property too.)
- Reproducibility depends on the RDKit/MMFF version used to build the reference
  ensemble. The version should be recorded alongside a deposited hash.
- SimHash is scale-invariant: it encodes the direction of the deviation from the
  reference mean, not its magnitude.

Usage
-----
    from csh_hash import CSHHasher
    h = CSHHasher("CC(=O)Oc1ccccc1C(=O)O")   # builds the reference transform
    bits = h.hash_bits(mol, conf_id)
    hexs = h.hash_hex(mol, conf_id)
    vec  = h.feature_vector(mol, conf_id)    # transformed (post-PCA) vector

Self-test:
    python csh_hash.py
"""

import hashlib
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdMolTransforms
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# ── frozen spec constants ──
PROJECTION_SEED = 42     # SimHash hyperplanes
REF_SEED        = 7      # reference-ensemble conformer generation
REF_N_CONFS     = 50     # size of the reference ensemble
PCA_DIMS        = 32
N_BITS          = 256    # SimHash hyperplanes (one 32-byte Ethereum slot)
MIN_TOPO        = 3      # minimum topological (bond) distance for an atom pair


# ─────────────────────────────────────────────── canonical order (geo tie) ──
def canonicalize(mol, conf_id=0):
    """Atoms in canonical order: graph rank first, rotation-invariant
    geometric key (sum of 3D distances to all atoms) as tie-break."""
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False,
                                         includeChirality=True))
    pos = mol.GetConformer(conf_id).GetPositions()
    n = len(pos)
    dsum = [float(np.sum(np.linalg.norm(pos - pos[i], axis=1)))
            for i in range(n)]
    order = sorted(range(n), key=lambda i: (ranks[i], dsum[i]))
    return Chem.RenumberAtoms(mol, order)


def _torsion_sincos(mol, conf_id):
    """(sin, cos) per rotatable (non-ring) bond, in the deterministic bond
    order of the canonicalized molecule."""
    conf = mol.GetConformer(conf_id)
    out = []
    for bond in mol.GetBonds():
        if bond.IsInRing():
            continue
        i = bond.GetBeginAtomIdx()
        j = bond.GetEndAtomIdx()
        i_nb = [n.GetIdx() for n in mol.GetAtomWithIdx(i).GetNeighbors()
                if n.GetIdx() != j]
        j_nb = [n.GetIdx() for n in mol.GetAtomWithIdx(j).GetNeighbors()
                if n.GetIdx() != i]
        if not i_nb or not j_nb:
            continue
        a, d = min(i_nb), min(j_nb)
        try:
            ang = rdMolTransforms.GetDihedralDeg(conf, a, i, j, d)
        except Exception:
            out.extend([0.0, 0.0])
            continue
        r = np.deg2rad(ang)
        out.extend([np.sin(r), np.cos(r)])
    return np.asarray(out, dtype=np.float64)


def raw_feature_vector(mol, conf_id=0, heavy=False):
    """Untransformed features: [distances (topo >= MIN_TOPO), sin/cos torsions].
    All atoms, canonical order. This is the input to the reference transform."""
    work = Chem.RemoveHs(mol) if heavy else mol
    work = canonicalize(work, conf_id)
    pos = work.GetConformer(conf_id).GetPositions()
    n = len(pos)
    topo = Chem.GetDistanceMatrix(work)
    dists = [np.linalg.norm(pos[i] - pos[j])
             for i in range(n) for j in range(i + 1, n)
             if topo[i, j] >= MIN_TOPO]
    return np.concatenate([np.asarray(dists, dtype=np.float64),
                           _torsion_sincos(work, conf_id)])


# ─────────────────────────────────────────────────────────────── the hasher ──
class CSHHasher:
    """Builds the canonical reference transform for one molecule, then hashes
    any conformer of that molecule with it."""

    # The reference ensemble depends only on (smiles, ref_n_confs, heavy) and is
    # deterministic, so it is cached: a caller sweeping pca_dims or n_bits over
    # the same molecule would otherwise re-embed and re-minimise it every time.
    # Cached values are never mutated; feature_vector reads them only.
    _ref_cache = {}

    @classmethod
    def clear_reference_cache(cls):
        cls._ref_cache.clear()

    def __init__(self, smiles, ref_n_confs=REF_N_CONFS, pca_dims=PCA_DIMS,
                 heavy=True, n_bits=N_BITS):
        self.smiles = smiles
        self.heavy = heavy

        cache_key = (smiles, ref_n_confs, bool(heavy))
        if cache_key in CSHHasher._ref_cache:
            X, self.n_features = CSHHasher._ref_cache[cache_key]
        else:
            ref = Chem.MolFromSmiles(smiles)
            if ref is None:
                raise ValueError(f"invalid SMILES: {smiles}")
            ref = Chem.AddHs(ref)
            params = AllChem.ETKDGv3()
            params.randomSeed = REF_SEED
            AllChem.EmbedMultipleConfs(ref, numConfs=ref_n_confs, params=params)
            AllChem.MMFFOptimizeMoleculeConfs(ref)
            if ref.GetNumConformers() < 2:
                raise ValueError(f"reference ensemble failed for {smiles}")

            X = [raw_feature_vector(ref, c, heavy)
                 for c in range(ref.GetNumConformers())]
            self.n_features = min(len(x) for x in X)
            X = np.array([x[:self.n_features] for x in X])
            CSHHasher._ref_cache[cache_key] = (X, self.n_features)

        self.scaler = StandardScaler().fit(X)
        self.n_components = min(pca_dims, X.shape[0] - 1, X.shape[1])
        self.pca = PCA(n_components=self.n_components,
                       random_state=PROJECTION_SEED).fit(self.scaler.transform(X))
        self.n_bits = n_bits
        rng = np.random.RandomState(PROJECTION_SEED)
        self.projection = rng.randn(n_bits, self.n_components)

    # ── public API ──
    def feature_vector(self, mol, conf_id=0):
        """Transformed (post-PCA) vector for one conformer."""
        x = raw_feature_vector(mol, conf_id, self.heavy)[:self.n_features].reshape(1, -1)
        return self.pca.transform(self.scaler.transform(x))[0]

    def hash_bits(self, mol, conf_id=0):
        """CSH hash as a uint8 array of 0/1 (n_bits long)."""
        v = self.feature_vector(mol, conf_id)
        return (v @ self.projection.T > 0).astype(np.uint8)

    def hash_hex(self, mol, conf_id=0):
        """CSH hash as a hex string (registry format)."""
        return np.packbits(self.hash_bits(mol, conf_id),
                           bitorder="big").tobytes().hex()

    def spec_version(self):
        """String identifying the exact transform, for storage alongside a hash.
        Hashes are only comparable when this string matches."""
        return (f"csh2|{'heavy' if self.heavy else 'allatom'}|pca{self.n_components}"
                f"|bits{self.n_bits}|refseed{REF_SEED}|proj{PROJECTION_SEED}"
                f"|rdkit{Chem.rdBase.rdkitVersion}")

    def sha256_id(self, mol, conf_id=0):
        """Exact identifier: SHA-256 of the raw canonical feature vector.
        Returns the full 64-character digest; never truncate it."""
        v = raw_feature_vector(mol, conf_id, self.heavy)[:self.n_features]
        return hashlib.sha256(v.tobytes()).hexdigest()


def hamming(a, b):
    """Hamming distance between two hashes (hex strings or bit arrays)."""
    def to_bits(x):
        if isinstance(x, str):
            return np.unpackbits(np.frombuffer(bytes.fromhex(x), dtype=np.uint8))
        return np.asarray(x, dtype=np.uint8)
    return int(np.sum(to_bits(a) != to_bits(b)))


# ──────────────────────────────────────────────────────────────── self-test ──
if __name__ == "__main__":
    from scipy.spatial.distance import pdist
    from scipy.stats import spearmanr
    from rdkit import RDLogger
    RDLogger.DisableLog("rdApp.*")

    TEST_SEED = 42   # deliberately different from REF_SEED
    CASES = [("Aspirin",  "CC(=O)Oc1ccccc1C(=O)O"),
             ("Caffeine", "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
             ("Imatinib", "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1")]

    def embed(smiles, n):
        m = Chem.AddHs(Chem.MolFromSmiles(smiles))
        p = AllChem.ETKDGv3()
        p.randomSeed = TEST_SEED
        AllChem.EmbedMultipleConfs(m, numConfs=n, params=p)
        AllChem.MMFFOptimizeMoleculeConfs(m)
        return m

    print("=" * 72)
    print("CSH canonical pipeline v2 — self-test")
    print("=" * 72)

    # [1] round-trip: atom order of the input must not affect the hash
    print("\n[1] Round-trip (8 random atom permutations, per molecule):")
    for name, smi in CASES:
        h = CSHHasher(smi)
        m = embed(smi, 5)
        ref_bits = h.hash_bits(m, 0)
        rng = np.random.RandomState(0)
        ok = True
        for _ in range(8):
            perm = [int(x) for x in rng.permutation(m.GetNumAtoms())]
            ok &= np.array_equal(h.hash_bits(Chem.RenumberAtoms(m, perm), 0),
                                 ref_bits)
        print(f"    {name:<10}: {'PASS' if ok else 'FAIL'}")

    # [2] determinism: a second hasher built from the same SMILES must agree
    print("\n[2] Determinism (independently rebuilt transform):")
    for name, smi in CASES:
        m = embed(smi, 3)
        a = CSHHasher(smi).hash_hex(m, 0)
        b = CSHHasher(smi).hash_hex(m, 0)
        print(f"    {name:<10}: {'PASS' if a == b else 'FAIL'}  ({a})")

    # [3] sensitivity vs the reference geometric metric
    print("\n[3] Spearman rho vs all-atom DM-RMSD (30 conformers):")
    for name, smi in CASES:
        h = CSHHasher(smi)
        m = embed(smi, 30)
        nc = m.GetNumConformers()
        dv = [pdist(m.GetConformer(c).GetPositions()) for c in range(nc)]
        B = [h.hash_bits(m, c) for c in range(nc)]
        pairs = [(i, j) for i in range(nc) for j in range(i + 1, nc)]
        dm = np.array([np.sqrt(np.mean((dv[i] - dv[j]) ** 2)) for i, j in pairs])
        sim = np.array([np.mean(B[i] == B[j]) for i, j in pairs])
        # negated: higher is better, and a sign error stays visible
        rho = -spearmanr(dm, sim).statistic if np.std(sim) > 0 else float("nan")
        uniq = len(set(tuple(b) for b in B))
        print(f"    {name:<10}: rho = {rho:.3f}   unique hashes {uniq}/{nc}")

    print("\n[1] and [2] must PASS. [3] is reported, not asserted.")
