// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title ConformationalRegistry
 * @notice Tamper-proof registry for molecular conformer hashes.
 *
 * Use case: A pharmaceutical company can register the CSH hash of a
 * conformer to prove they explored that conformational state on a
 * specific date — without revealing the 3D structure itself.
 *
 * This provides:
 *   - Proof-of-conformational-search (timestamped, immutable)
 *   - IP protection (structure stays private, only hash is public)
 *   - Reproducibility (anyone can verify a hash exists on-chain)
 *
 * @author Jakub Hryc
 */
contract ConformationalRegistry {

    // ── Data structures ───────────────────────────────────────────────────────

    struct ConformerRecord {
        string  moleculeName;   // human-readable name (e.g. "Imatinib")
        bytes32 cshHash;        // CSH hash (64-bit, padded to 32 bytes)
        string  sha256Id;       // SHA-256 exact ID for deduplication
        int256  energy;         // MMFF94 energy * 1000 (no floats in Solidity)
        address registrant;     // Ethereum address of the registering party
        uint256 timestamp;      // block timestamp (Unix time)
        bool    exists;         // guard for existence checks
    }

    // ── Storage ───────────────────────────────────────────────────────────────

    // Primary registry: CSH hash → record
    mapping(bytes32 => ConformerRecord) private registry;

    // All registered hashes (for enumeration)
    bytes32[] public allHashes;

    // Count per registrant
    mapping(address => uint256) public registrantCount;

    // ── Events ────────────────────────────────────────────────────────────────

    event ConformerRegistered(
        bytes32 indexed cshHash,
        string  moleculeName,
        address indexed registrant,
        uint256 timestamp
    );

    // ── Core functions ────────────────────────────────────────────────────────

    /**
     * @notice Register a conformer hash on-chain.
     * @param moleculeName  Human-readable molecule name
     * @param cshHash       CSH hash from Python pipeline (as bytes32)
     * @param sha256Id      SHA-256 exact ID (first 32 chars)
     * @param energyX1000   MMFF94 energy multiplied by 1000 (to avoid floats)
     */
    function registerConformer(
        string  memory moleculeName,
        bytes32        cshHash,
        string  memory sha256Id,
        int256         energyX1000
    ) public {
        // Prevent overwriting an existing record
        require(!registry[cshHash].exists, "Conformer already registered");

        // Store the record
        registry[cshHash] = ConformerRecord({
            moleculeName: moleculeName,
            cshHash:      cshHash,
            sha256Id:     sha256Id,
            energy:       energyX1000,
            registrant:   msg.sender,
            timestamp:    block.timestamp,
            exists:       true
        });

        allHashes.push(cshHash);
        registrantCount[msg.sender]++;

        emit ConformerRegistered(cshHash, moleculeName, msg.sender, block.timestamp);
    }

    // ── Query functions ───────────────────────────────────────────────────────

    /**
     * @notice Check if a conformer hash is already registered.
     * @param cshHash  CSH hash to query
     * @return True if registered, false otherwise
     */
    function isRegistered(bytes32 cshHash) public view returns (bool) {
        return registry[cshHash].exists;
    }

    /**
     * @notice Retrieve full record for a conformer hash.
     * @param cshHash  CSH hash to query
     * @return Full ConformerRecord struct
     */
    function getConformer(bytes32 cshHash)
        public
        view
        returns (ConformerRecord memory)
    {
        require(registry[cshHash].exists, "Conformer not found");
        return registry[cshHash];
    }

    /**
     * @notice Get total number of registered conformers.
     */
    function totalRegistered() public view returns (uint256) {
        return allHashes.length;
    }

    /**
     * @notice Get all hashes registered by a specific address.
     * @param registrant  Ethereum address to query
     * @return Array of CSH hashes registered by this address
     */
    function getHashesByRegistrant(address registrant)
        public
        view
        returns (bytes32[] memory)
    {
        uint256 count = registrantCount[registrant];
        bytes32[] memory result = new bytes32[](count);
        uint256 idx = 0;

        for (uint256 i = 0; i < allHashes.length; i++) {
            if (registry[allHashes[i]].registrant == registrant) {
                result[idx] = allHashes[i];
                idx++;
            }
        }
        return result;
    }
}
