"""One-shot scan: fetch all ConformerRegistered events from contract V2.

Run this once to verify the indexer can connect to Sepolia and read events.
Should print all historical registrations from deployment block to now.
"""

import json
from web3 import Web3
import config


def load_abi():
    """Load contract ABI from Hardhat artifact."""
    with open(config.CONTRACT_ARTIFACT) as f:
        artifact = json.load(f)
    return artifact["abi"]


def main():
    print("=" * 60)
    print("CSH V2 Indexer — One-shot historical scan")
    print("=" * 60)

    # Connect to Sepolia
    w3 = Web3(Web3.HTTPProvider(config.SEPOLIA_RPC_URL))
    if not w3.is_connected():
        raise RuntimeError("Cannot connect to Sepolia RPC")

    chain_id = w3.eth.chain_id
    latest_block = w3.eth.block_number
    print(f"\nConnected to chain ID: {chain_id} (Sepolia = 11155111)")
    print(f"Latest block: {latest_block}")
    print(f"Scanning from block: {config.DEPLOYMENT_BLOCK}")
    print(f"Block range: {latest_block - config.DEPLOYMENT_BLOCK} blocks")

    # Load contract
    abi = load_abi()
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(config.V2_CONTRACT_ADDRESS),
        abi=abi,
    )

    # Fetch events from deployment block to latest.
    # Alchemy free tier limits eth_getLogs to 10 blocks per request, so we
    # chunk the range into smaller windows. With ~6500 blocks at 10 per call,
    # this is ~650 RPC calls — slow but works on free tier.
    print("\nFetching ConformerRegistered events (chunked, 10 blocks per call)...")

    CHUNK_SIZE = 10  # Alchemy free tier limit
    events = []
    from_block = config.DEPLOYMENT_BLOCK
    total_chunks = (latest_block - from_block) // CHUNK_SIZE + 1

    chunk_num = 0
    while from_block <= latest_block:
        to_block = min(from_block + CHUNK_SIZE - 1, latest_block)
        chunk_num += 1

        chunk_events = contract.events.ConformerRegistered.get_logs(
            from_block=from_block,
            to_block=to_block,
        )

        if chunk_events:
            print(f"  Chunk {chunk_num}/{total_chunks} "
                  f"(blocks {from_block}-{to_block}): "
                  f"{len(chunk_events)} event(s)")
            events.extend(chunk_events)

        # Print progress every 50 chunks (~500 blocks)
        if chunk_num % 50 == 0:
            print(f"  Progress: chunk {chunk_num}/{total_chunks} "
                  f"({100 * chunk_num // total_chunks}%) "
                  f"- {len(events)} event(s) so far")

        from_block = to_block + 1

    print(f"\nFound {len(events)} event(s)\n")
    print("=" * 60)

    for i, event in enumerate(events, start=1):
        args = event["args"]
        print(f"\nEvent #{i}")
        print(f"  Block:        {event['blockNumber']}")
        print(f"  Tx hash:      {event['transactionHash'].hex()}")
        print(f"  CSH hash:     {args['cshHash'].hex()}")
        print(f"  Registrant:   {args['registrant']}")
        print(f"  Timestamp:    {args['timestamp']}")
        print(f"  Mol name:     {args['moleculeName']}")
        print(f"  SHA256 ID:    {args['sha256Id']}")
        print(f"  Energy x1000: {args['energyX1000']}")

    print("\n" + "=" * 60)
    print(f"Scan complete. {len(events)} event(s) processed.")


if __name__ == "__main__":
    main()

