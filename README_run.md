# Running the CSH benchmark

Put these three files in one directory and run the notebook from there:

    CSH_full.ipynb      the benchmark
    csh_hash.py         canonical CSH implementation
    ap3d.py             3DAPfp (Awale, Jin & Reymond, J Cheminform 2015;7:3)

## Environment

Already in a working RDKit environment, so most of this is present:

    rdkit  numpy  scipy  pandas  scikit-learn  matplotlib

Two additions:

    pip install e3fp datasets

`e3fp` is the E3FP baseline used from section 4 onward; `datasets` is only
needed for section 12. The 3DCS split is read in streaming mode, so only the
records actually evaluated are downloaded.

`web3` is needed only for section 11 (blockchain registration), which is off by
default. Install it when that section is actually going to run.

If `e3fp` is missing the notebook still runs; the E3FP columns come out as nan.

## Order

1. Set `QUICK = False` in the config cell. Run sections 1-10. About 30 min.
   Produces `table1_development.csv` and `table2_control.csv`.

2. Optional external validation (section 12): set `RUN_3DCS = True`.
   Downloads the 3DCS rotation split from Hugging Face on first run.
   About 20 min for 100 molecules. Produces `table3_3dcs.csv`.

3. Section 11 (blockchain) last, and only once the hashes are final.
   Writes to a public chain cannot be undone. `REGISTER = False` by default and
   should stay that way for now: the deployed contract keys records on the CSH
   hash alone, while a CSH hash is only meaningful together with its molecule
   and transform version. The contract needs that key change before anything is
   registered.

## Notes

- Section 12 fits the CSH transform on ETKDG+MMFF reference ensembles while
  testing on xTB-relaxed scan conformers. That mismatch is deliberate — it is
  what makes the test external — but it is also the most likely reason for CSH
  to underperform there, and should be reported as such either way.
- On highly symmetric molecules the torsion-angle reference treats a rotation
  by 180 degrees as a large change even when the resulting structure is nearly
  identical. Aligned RMSD accounts for symmetry; the angle does not. Where the
  two disagree strongly, check the molecule for a symmetric substituent.
