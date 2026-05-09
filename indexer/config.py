"""Configuration for the CSH V2 indexer."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Find project root (parent of indexer/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOTENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(DOTENV_PATH)

# Sepolia RPC endpoint (Alchemy)
SEPOLIA_RPC_URL = os.getenv("SEPOLIA_RPC_URL")
if not SEPOLIA_RPC_URL:
    raise ValueError(f"SEPOLIA_RPC_URL not set. Check {DOTENV_PATH}")

# Contract address
V2_CONTRACT_ADDRESS = os.getenv("V2_CONTRACT_ADDRESS")
if not V2_CONTRACT_ADDRESS:
    raise ValueError(f"V2_CONTRACT_ADDRESS not set. Check {DOTENV_PATH}")

# Path to compiled contract artifact (from Hardhat)
CONTRACT_ARTIFACT = (
    PROJECT_ROOT
    / "hardhat"
    / "artifacts"
    / "contracts"
    / "ConformationalRegistryV2.sol"
    / "ConformationalRegistryV2.json"
)

# Block number where V2 contract was deployed.
# We'll scan from this block forward when bootstrapping the indexer.
# To be filled in after first run (or fetched from deployment tx).
DEPLOYMENT_BLOCK = int(os.getenv("V2_DEPLOYMENT_BLOCK", "0"))


if __name__ == "__main__":
    # Self-check
    print(f"PROJECT_ROOT:        {PROJECT_ROOT}")
    print(f"DOTENV_PATH:         {DOTENV_PATH}")
    print(f"SEPOLIA_RPC_URL:     {SEPOLIA_RPC_URL[:50]}...")
    print(f"V2_CONTRACT_ADDRESS: {V2_CONTRACT_ADDRESS}")
    print(f"CONTRACT_ARTIFACT:   {CONTRACT_ARTIFACT}")
    print(f"  exists: {CONTRACT_ARTIFACT.exists()}")
    print(f"DEPLOYMENT_BLOCK:    {DEPLOYMENT_BLOCK}")
