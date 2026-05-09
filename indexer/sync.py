"""Synchronize the database with on-chain ConformerRegistered events.

Strategy:
  1. Read last_indexed_block from database
  2. Scan blocks (last+1, latest) in 10-block chunks
  3. For each event, INSERT OR IGNORE into conformer_events
  4. After each chunk, update last_indexed_block

This is idempotent: running twice does nothing the second time.
Safe to interrupt — picks up from last successful chunk.
"""

import json
import time
from web3 import Web3

import config
from database import (
    SessionLocal, ConformerEvent, IndexerState,
    init_db, get_state, event_count,
)


CHUNK_SIZE = 10  # Alchemy free tier limit


def load_abi():
    with open(config.CONTRACT_ARTIFACT) as f:
        return json.load(f)["abi"]


def event_to_record(event) -> dict:
    """Convert a web3 event log entry into a database row dict."""
    args = event["args"]
    return {
        "csh_hash": "0x" + args["cshHash"].hex(),
        "registrant": args["registrant"],
        "timestamp": args["timestamp"],
        "molecule_name": args["moleculeName"],
        "sha256_id": args["sha256Id"],
        "energy_x1000": args["energyX1000"],
        "block_number": event["blockNumber"],
        "tx_hash": "0x" + event["transactionHash"].hex(),
    }


def insert_event(session, record: dict) -> bool:
    """Insert one event. Returns True if new, False if already exists."""
    existing = session.query(ConformerEvent).filter_by(
        csh_hash=record["csh_hash"]
    ).first()
    if existing:
        return False
    session.add(ConformerEvent(**record))
    return True


def sync():
    print("=" * 60)
    print("CSH V2 Indexer — Sync")
    print("=" * 60)

    init_db()

    # Connect to Sepolia
    w3 = Web3(Web3.HTTPProvider(config.SEPOLIA_RPC_URL))
    if not w3.is_connected():
        raise RuntimeError("Cannot connect to Sepolia RPC")

    abi = load_abi()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(config.V2_CONTRACT_ADDRESS),
        abi=abi,
    )

    latest_block = w3.eth.block_number

    with SessionLocal() as session:
        state = get_state(session, default_start_block=config.DEPLOYMENT_BLOCK)
        existing_count = event_count(session)

        print(f"\nLatest on-chain block:  {latest_block}")
        print(f"Last indexed block:     {state.last_indexed_block}")
        print(f"Events already in DB:   {existing_count}")

        from_block = state.last_indexed_block + 1
        if from_block > latest_block:
            print("\n✓ Already up to date.")
            return

        total_blocks = latest_block - from_block + 1
        total_chunks = (total_blocks + CHUNK_SIZE - 1) // CHUNK_SIZE
        print(f"Blocks to scan:         {total_blocks}")
        print(f"Chunks needed:          {total_chunks}")
        print()

        # Scan in chunks
        new_events = 0
        chunk_num = 0
        start_time = time.time()

        while from_block <= latest_block:
            to_block = min(from_block + CHUNK_SIZE - 1, latest_block)
            chunk_num += 1

            chunk_events = contract.events.ConformerRegistered.get_logs(
                from_block=from_block,
                to_block=to_block,
            )

            for ev in chunk_events:
                record = event_to_record(ev)
                is_new = insert_event(session, record)
                if is_new:
                    new_events += 1
                    print(f"  + Block {ev['blockNumber']}: "
                          f"{record['molecule_name']} "
                          f"(hash {record['csh_hash'][:18]}...)")

            # Persist progress after each chunk (resilient to interruption)
            state.last_indexed_block = to_block
            session.commit()

            # Progress log every 100 chunks
            if chunk_num % 100 == 0:
                elapsed = time.time() - start_time
                rate = chunk_num / elapsed
                eta = (total_chunks - chunk_num) / rate if rate > 0 else 0
                print(f"  ... chunk {chunk_num}/{total_chunks} "
                      f"({100 * chunk_num // total_chunks}%) "
                      f"- {new_events} new event(s) "
                      f"- ETA {eta:.0f}s")

            from_block = to_block + 1

        elapsed = time.time() - start_time
        print()
        print("=" * 60)
        print(f"✓ Sync complete in {elapsed:.0f}s")
        print(f"  New events:   {new_events}")
        print(f"  Total in DB:  {event_count(session)}")
        print(f"  Last block:   {state.last_indexed_block}")
        print("=" * 60)


if __name__ == "__main__":
    sync()
