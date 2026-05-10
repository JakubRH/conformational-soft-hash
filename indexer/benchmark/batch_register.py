"""Batch-register synthetic conformers from JSON dataset to Sepolia.

Strategy:
  - Read dataset and resume state (which entries are already registered)
  - Submit transactions sequentially with manual nonce management
  - Don't wait for each tx to confirm — submit fast, let Sepolia mine them
  - Save progress after each successful submission
  - Skip entries that are already on-chain (idempotent)

Usage:
  python batch_register.py            # register all not-yet-registered
  python batch_register.py --dry-run  # show what would be submitted
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from web3 import Web3

# Add parent dir to path so we can import config and database
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from database import SessionLocal, ConformerEvent


# ─── Configuration ────────────────────────────────────────────────────────────

GAS_PRICE_GWEI = 0.1    # Sepolia is cheap; this is conservative
GAS_LIMIT = 500_000     # registerConformer uses ~250k gas


def load_abi():
    with open(config.CONTRACT_ARTIFACT) as f:
        return json.load(f)["abi"]


def load_dataset(dataset_file: Path):
    with open(dataset_file) as f:
        return json.load(f)


def load_progress(progress_file: Path) -> set:
    """Set of csh_hashes already submitted (saved to disk)."""
    if not progress_file.exists():
        return set()
    with open(progress_file) as f:
        return set(json.load(f))


def save_progress(progress_file: Path, submitted: set):
    with open(progress_file, "w") as f:
        json.dump(sorted(submitted), f, indent=2)


def already_on_chain() -> set:
    """Set of csh_hashes already in our local indexer DB.

    Useful for picking up after a crash where the tx was sent but
    the script died before saving progress.
    """
    with SessionLocal() as session:
        return set(
            row[0] for row in session.query(ConformerEvent.csh_hash).all()
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=str, default="synthetic_dataset.json",
                        help="Dataset JSON file (relative to this script)")
    parser.add_argument("--progress", type=str, default=None,
                        help="Progress file (auto-generated from dataset name if None)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be submitted, don't send tx")
    parser.add_argument("--dedupe", action="store_true",
                        help="Skip duplicate hashes within dataset (keep first)")
    args = parser.parse_args()

    # Resolve paths
    dataset_file = Path(__file__).parent / args.dataset
    if args.progress:
        progress_file = Path(__file__).parent / args.progress
    else:
        # Auto-generate: synthetic_dataset.json -> synthetic_progress.json
        progress_file = Path(__file__).parent / args.dataset.replace(".json", "_progress.json")

    print(f"Dataset:           {dataset_file}")
    print(f"Progress file:     {progress_file}")

    # Load private key directly (web3 needs raw key, not just signer)
    private_key = os.getenv("SEPOLIA_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("SEPOLIA_PRIVATE_KEY not in env (check .env)")

    # Connect
    w3 = Web3(Web3.HTTPProvider(config.SEPOLIA_RPC_URL))
    if not w3.is_connected():
        raise RuntimeError("Cannot connect to Sepolia")

    account = w3.eth.account.from_key(private_key)
    print(f"Account:           {account.address}")
    balance = w3.eth.get_balance(account.address)
    print(f"Balance:           {w3.from_wei(balance, 'ether'):.6f} ETH")

    # Load dataset and progress
    dataset = load_dataset(dataset_file)
    submitted = load_progress(progress_file)

    # Optionally dedupe within-dataset (keep only first occurrence of each hash)
    if args.dedupe:
        seen_hashes = set()
        dedupe_dataset = []
        n_dropped = 0
        for entry in dataset:
            if entry["csh_hash"] not in seen_hashes:
                seen_hashes.add(entry["csh_hash"])
                dedupe_dataset.append(entry)
            else:
                n_dropped += 1
        if n_dropped > 0:
            print(f"  Dedupe: dropped {n_dropped} within-dataset duplicate(s)")
        dataset = dedupe_dataset
    on_chain = already_on_chain()

    # Skip entries already submitted OR already on chain
    skip = submitted | on_chain
    pending = [e for e in dataset if e["csh_hash"] not in skip]

    print(f"\nDataset entries:   {len(dataset)}")
    print(f"Already submitted: {len(submitted)}")
    print(f"Already on chain:  {len(on_chain)}")
    print(f"To submit now:     {len(pending)}")

    estimated_cost = len(pending) * GAS_LIMIT * GAS_PRICE_GWEI * 1e-9
    print(f"Estimated cost:    {estimated_cost:.6f} ETH")

    if args.dry_run:
        print("\n[DRY RUN] Not submitting transactions.")
        print(f"First 3 to submit:")
        for e in pending[:3]:
            print(f"  {e['molecule_name']} hash={e['csh_hash'][:20]}...")
        return

    if not pending:
        print("\n✓ Nothing to submit, all done.")
        return

    # Need enough balance
    if balance < int(estimated_cost * 1.5 * 1e18):
        raise RuntimeError(
            f"Balance too low. Have {w3.from_wei(balance, 'ether'):.4f} ETH, "
            f"need ~{estimated_cost:.4f} ETH."
        )

    # Get contract
    abi = load_abi()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(config.V2_CONTRACT_ADDRESS),
        abi=abi,
    )

    # Get current nonce ONCE, then increment manually
    current_nonce = w3.eth.get_transaction_count(account.address, "pending")
    print(f"\nStarting nonce:    {current_nonce}")
    print(f"Submitting {len(pending)} transactions...\n")

    start_time = time.time()
    submitted_this_run = 0
    failed = 0

    for i, entry in enumerate(pending, start=1):
        # Build transaction
        try:
            tx = contract.functions.registerConformer(
                entry["molecule_name"],
                entry["csh_hash"],          # bytes32 (full 64-hex string OK)
                entry["sha256_id"],
                entry["energy_x1000"],
            ).build_transaction({
                "from": account.address,
                "nonce": current_nonce,
                "gas": GAS_LIMIT,
                "gasPrice": w3.to_wei(GAS_PRICE_GWEI, "gwei"),
                "chainId": 11155111,
            })

            # Sign
            signed = w3.eth.account.sign_transaction(tx, private_key)

            # Send (don't wait for receipt)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

            current_nonce += 1
            submitted.add(entry["csh_hash"])
            submitted_this_run += 1

            # Progress feedback
            if i % 10 == 0 or i == len(pending):
                elapsed = time.time() - start_time
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(pending) - i) / rate if rate > 0 else 0
                print(f"  {i}/{len(pending)} submitted "
                      f"(latest tx: {tx_hash.hex()[:20]}...) "
                      f"rate={rate:.1f}/s eta={eta:.0f}s")

            # Save progress periodically
            if i % 50 == 0:
                save_progress(progress_file, submitted)

            # Tiny pause to not overwhelm Alchemy
            time.sleep(0.05)

        except Exception as e:
            failed += 1
            print(f"  [ERR] {entry['molecule_name']}: {e}")
            # If too many failures, abort
            if failed > 10:
                print("\nToo many failures, aborting.")
                break

    # Final save
    save_progress(progress_file, submitted)

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Submitted {submitted_this_run} transactions in {elapsed:.0f}s")
    print(f"Failed: {failed}")
    print(f"Total submitted across all runs: {len(submitted)}")
    print(f"{'='*60}")
    print(f"\nNext steps:")
    print(f"1. Wait ~2-5 minutes for Sepolia to mine all transactions")
    print(f"2. Run: python ../sync.py")
    print(f"3. Verify: python -c 'from database import SessionLocal, "
          f"event_count; \\\nprint(event_count(SessionLocal()))'")


if __name__ == "__main__":
    main()
