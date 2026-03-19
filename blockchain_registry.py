"""
blockchain_registry.py
======================
Connects the CSH pipeline to the ConformationalRegistry smart contract.

Workflow:
    1. Generate conformers with RDKit
    2. Compute CSH hash with our pipeline
    3. Register hash on Ethereum testnet (Sepolia)
    4. Verify registration on-chain

Requirements:
    pip install web3
    pip install py-solc-x

Usage:
    python blockchain_registry.py
"""

import json
import hashlib
import numpy as np
from web3 import Web3

# ── Connect to Ethereum testnet ───────────────────────────────────────────────

def connect_to_testnet(rpc_url: str = "https://rpc.sepolia.org") -> Web3:
    """
    Connect to Sepolia testnet (free, no real ETH needed).
    For local testing use Hardhat: http://127.0.0.1:8545
    """
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if w3.is_connected():
        print(f"Connected to Ethereum node")
        print(f"Chain ID: {w3.eth.chain_id}")
        print(f"Latest block: {w3.eth.block_number}")
    else:
        raise ConnectionError("Could not connect to Ethereum node")
    return w3


# ── Contract ABI (interface) ──────────────────────────────────────────────────
# This tells web3.py how to talk to our smart contract

CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "string",  "name": "moleculeName", "type": "string"},
            {"internalType": "bytes32", "name": "cshHash",      "type": "bytes32"},
            {"internalType": "string",  "name": "sha256Id",     "type": "string"},
            {"internalType": "int256",  "name": "energyX1000",  "type": "int256"}
        ],
        "name": "registerConformer",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "cshHash", "type": "bytes32"}],
        "name": "isRegistered",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "cshHash", "type": "bytes32"}],
        "name": "getConformer",
        "outputs": [
            {
                "components": [
                    {"internalType": "string",  "name": "moleculeName", "type": "string"},
                    {"internalType": "bytes32", "name": "cshHash",      "type": "bytes32"},
                    {"internalType": "string",  "name": "sha256Id",     "type": "string"},
                    {"internalType": "int256",  "name": "energy",       "type": "int256"},
                    {"internalType": "address", "name": "registrant",   "type": "address"},
                    {"internalType": "uint256", "name": "timestamp",    "type": "uint256"},
                    {"internalType": "bool",    "name": "exists",       "type": "bool"}
                ],
                "internalType": "struct ConformationalRegistry.ConformerRecord",
                "name": "",
                "type": "tuple"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalRegistered",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]


# ── CSH hash → bytes32 conversion ─────────────────────────────────────────────

def csh_hex_to_bytes32(csh_hex: str) -> bytes:
    """
    Converts our 8-char CSH hex hash to bytes32 (Solidity format).
    Pads with zeros on the right to fill 32 bytes.

    Example:
        '662221b2' → b'\\x66\\x22\\x21\\xb2' + 28 zero bytes
    """
    raw = bytes.fromhex(csh_hex)
    return raw.ljust(32, b'\x00')


# ── Main registry interface ───────────────────────────────────────────────────

class ConformationalRegistryClient:
    """
    Python client for the ConformationalRegistry smart contract.

    Example
    -------
    >>> client = ConformationalRegistryClient(w3, contract_address, private_key)
    >>> tx_hash = client.register("Ibuprofen", "662221b2", sha256_id, -18910)
    >>> print(client.is_registered("662221b2"))
    True
    """

    def __init__(self, w3: Web3, contract_address: str, private_key: str):
        self.w3 = w3
        self.account = w3.eth.account.from_key(private_key)
        self.contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=CONTRACT_ABI
        )
        print(f"Using account: {self.account.address}")

    def register(
        self,
        molecule_name: str,
        csh_hex: str,
        sha256_id: str,
        energy: float
    ) -> str:
        """
        Register a conformer hash on-chain.

        Parameters
        ----------
        molecule_name : str
            Human-readable name (e.g. "Ibuprofen conformer 0")
        csh_hex : str
            CSH hash from Python pipeline (hex string)
        sha256_id : str
            SHA-256 exact ID (first 32 chars)
        energy : float
            MMFF94 energy in kcal/mol

        Returns
        -------
        str : transaction hash
        """
        csh_bytes32 = csh_hex_to_bytes32(csh_hex)
        energy_int = int(energy * 1000)  # Solidity has no floats

        # Build transaction
        tx = self.contract.functions.registerConformer(
            molecule_name,
            csh_bytes32,
            sha256_id[:32],
            energy_int
        ).build_transaction({
            'from':     self.account.address,
            'nonce':    self.w3.eth.get_transaction_count(self.account.address),
            'gas':      200000,
            'gasPrice': self.w3.eth.gas_price,
        })

        # Sign and send
        signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)

        print(f"Registered on-chain!")
        print(f"  TX hash:   {tx_hash.hex()}")
        print(f"  Block:     {receipt['blockNumber']}")
        print(f"  Gas used:  {receipt['gasUsed']}")
        return tx_hash.hex()

    def is_registered(self, csh_hex: str) -> bool:
        """Check if a CSH hash is already registered."""
        csh_bytes32 = csh_hex_to_bytes32(csh_hex)
        return self.contract.functions.isRegistered(csh_bytes32).call()

    def get_conformer(self, csh_hex: str) -> dict:
        """Retrieve full record for a CSH hash."""
        csh_bytes32 = csh_hex_to_bytes32(csh_hex)
        record = self.contract.functions.getConformer(csh_bytes32).call()
        return {
            "molecule_name": record[0],
            "csh_hash":      record[1].hex(),
            "sha256_id":     record[2],
            "energy":        record[3] / 1000.0,
            "registrant":    record[4],
            "timestamp":     record[5],
            "exists":        record[6],
        }

    def total_registered(self) -> int:
        """Get total number of registered conformers."""
        return self.contract.functions.totalRegistered().call()


# ── Demo (local Hardhat node) ─────────────────────────────────────────────────

def demo_local():
    """
    Demo using local Hardhat node.
    Run first: npx hardhat node
    Then deploy contract and paste address below.
    """
    # Local Hardhat node
    w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545"))

    # Hardhat default test account (has 10000 ETH, safe for testing)
    PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    CONTRACT_ADDRESS = "YOUR_DEPLOYED_CONTRACT_ADDRESS"  # paste after deployment

    client = ConformationalRegistryClient(w3, CONTRACT_ADDRESS, PRIVATE_KEY)

    # Example CSH hash from our pipeline
    csh_hex    = "662221b2960088ac"
    sha256_id  = "dbb7c9b1c0b1df23a24747e87ecf9a17"
    energy     = -18.910

    print("\nRegistering Ibuprofen conformer 0...")
    tx = client.register("Ibuprofen_conf_0", csh_hex, sha256_id, energy)

    print(f"\nIs registered? {client.is_registered(csh_hex)}")
    print(f"Total on-chain: {client.total_registered()}")

    record = client.get_conformer(csh_hex)
    print(f"\nOn-chain record:")
    for k, v in record.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    demo_local()
