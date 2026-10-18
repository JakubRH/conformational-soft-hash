# Conformational Soft Hash (CSH)

A fixed-length binary representation of a molecular conformer, designed to be
compared within one molecule and to fit a single blockchain storage slot.

> **This version supersedes the earlier one.** The first release of this
> repository reported that CSH outperformed existing shape descriptors and that
> its hashes could separate different molecules. Both claims were withdrawn
> after a corrected benchmark. The earlier code fitted its scaling and PCA on
> the same conformers it then evaluated, and twelve of the twenty-eight
> molecules were built from incorrect SMILES. The numbers below come from the
> corrected pipeline. What changed, and why, is set out in the revision note at
> the top of the preprint.

## What CSH does

A conformer is described by the distances between pairs of heavy atoms at least
three bonds apart, together with its torsion angles. That vector varies in
length with molecular size, so a scaling and a PCA are fitted to a reference
ensemble generated from the molecule's own SMILES, and the result is projected
onto 256 random hyperplanes by SimHash. The output is 256 bits, which fills one
32-byte Ethereum storage slot exactly.

Because the projection is fitted per molecule, **hashes of different molecules
share no frame of reference and must not be compared.** This is a property of
the design, not an implementation gap. The registry contract enforces it: every
record belongs to a collection keyed by molecule and transform version, and no
contract function compares hashes across collections.

## Validating the structures

Every molecule carries a reference molecular weight and the skeleton block of
its InChIKey, both checked against PubChem at the start of every run. The
weight alone is not enough: it confirms the molecular formula, so an isomer
passes it. That is how a naproxen structure with the methoxy group in the wrong
position of the naphthalene survived the first round of corrections. The
InChIKey skeleton encodes the full connectivity and caught it.

## Results

Spearman rho between each method and DM-RMSD, over all conformer pairs of each
molecule, with every method brought to a common budget of 256 bits.

| Method | Development set (28) | Validation set (12) |
|---|---:|---:|
| CSH | 0.508 | 0.637 |
| USR | 0.481 | 0.522 |
| USRCAT | 0.516 | 0.516 |
| 3DAPfp | 0.562 | 0.632 |
| E3FP | 0.216 | 0.181 |

Means over molecules the method scored; the baselines return a single hash for
every conformer of some near-rigid molecules, leaving the correlation undefined
there. On the development set CSH scores all 28, USRCAT 24, E3FP 24, and USR
and 3DAPfp 23 each.

Paired comparisons, computed only on molecules both methods score:

| Comparison | Development set | Validation set |
|---|---|---|
| CSH minus USR | +0.062, p = 0.035 | +0.115, p = 0.012 |
| CSH minus USRCAT | +0.036, p = 0.360 | +0.121, p = 0.016 |
| CSH minus 3DAPfp | +0.004, p = 0.867 | +0.004, p = 0.583 |
| CSH minus E3FP | +0.331, p < 0.001 | +0.456, p < 0.001 |

CSH is ahead of USR on both sets and of USRCAT on the validation set, and is
indistinguishable from 3DAPfp on either. 3DAPfp reaches that accuracy without
any per-molecule fitting, so unlike CSH it stays comparable across molecules;
its sixteen values also fit in 128 bits. The margin over USRCAT depends on the
preprocessing: when USRCAT is put through the same per-molecule pipeline that
CSH requires, the difference on the validation set falls to +0.045 and no
longer reaches significance.

## Registry

`ConformerRegistry.sol`, deployed on the Ethereum Sepolia testnet at
[0x42fEcFe9B797e83300Bf10F39557e8d7f9B9FED0](https://sepolia.etherscan.io/address/0x42fEcFe9B797e83300Bf10F39557e8d7f9B9FED0)
and verified there, so the source and the read functions are available from a
browser.

Eighty conformers of four molecules are registered, twenty each: ketamine,
where CSH leads every baseline; imatinib and atorvastatin, where 3DAPfp and
USRCAT respectively do better; and caffeine, whose heavy-atom conformers are
effectively identical and on which every baseline returns a single hash. The
four were chosen to span the range of outcomes rather than to show the method
at its best.

Each record holds the 256-bit hash, the full SHA-256 of the canonical feature
vector, the MMFF94 energy as metadata, and the block timestamp. Deduplication
uses the SHA-256, not the soft hash, since the latter is lossy by construction.

Measured cost with the Solidity optimiser at 200 runs: about 1.02 M gas to
deploy, 168 k to open a collection, and about 99.6 k per conformer in batches
of ten.

## Files

```
CSH_full.ipynb              benchmark, sanity checks, registry, demo data
csh_hash.py                 CSH implementation
ap3d.py                     3DAPfp, reimplemented from Awale et al. 2015
fig4.py                     pipeline diagram
ConformerRegistry.sol       registry contract (solc 0.8.20, optimiser 200 runs)
ConformerRegistry.abi.json  compiled ABI
ConformerRegistry.bin       compiled bytecode
table1_development.csv      per-molecule results, development set
table2_validation.csv       per-molecule results, validation set
registry_records.csv        what was written on chain
figure1_development.png     per-molecule results, development set
figure2_validation.png      per-molecule results, validation set
figure3_pipeline.png        the pipeline and the registry
README_run.md               how to run the notebook
```

## Running it

Put `CSH_full.ipynb`, `csh_hash.py` and `ap3d.py` in one directory. Beyond a
working RDKit environment you need:

```
pip install e3fp
```

Set `QUICK = False` and run sections 1 to 10; about 30 minutes. Section 11
writes to a blockchain and is off by default (`REGISTER = False`); leave it
that way unless the hashes are final, since those writes cannot be undone.

See `README_run.md` for the details.

## Citation

Hryc, J. (2026). Conformational Soft Hash: a compact binary representation of
molecular conformers with a blockchain-based registry. ChemRxiv preprint.

## Author

Jakub Hryc
ORCID: [0000-0002-6182-4500](https://orcid.org/0000-0002-6182-4500)

## License

MIT, see `LICENSE`.
