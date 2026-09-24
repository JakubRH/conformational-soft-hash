// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Conformer registry with molecule-scoped hashes
/// @notice Timestamps conformer records on-chain. A soft hash of this kind is
///         only meaningful within one molecule and one transform version, so
///         the registry makes that scope explicit: conformers are always
///         registered into a collection identified by (molecule, specVersion),
///         and nothing in this contract compares hashes across collections.
///         Storing a bare hash as a global key, as an earlier version did,
///         invites exactly the cross-molecule comparison the representation
///         does not support.
contract ConformerRegistry {

    struct Collection {
        string  molecule;      // molecule identifier (name or InChIKey)
        string  specVersion;   // transform version; hashes are comparable only within one
        address owner;
        uint64  createdAt;
        uint32  count;
    }

    struct Conformer {
        bytes32 cshHash;       // 256-bit soft hash, fills the slot exactly
        bytes32 sha256Id;      // full SHA-256 of the canonical feature vector
        int64   energyMilli;   // relative energy, kcal/mol x 1000; metadata only
        uint64  timestamp;
    }

    Collection[] private _collections;
    mapping(uint256 => Conformer[]) private _conformers;

    /// keccak256(molecule, specVersion) => collection id + 1 (0 means absent)
    mapping(bytes32 => uint256) private _collectionByKey;

    /// collection id => sha256Id => already registered
    mapping(uint256 => mapping(bytes32 => bool)) private _seen;

    event CollectionCreated(
        uint256 indexed collectionId,
        string  molecule,
        string  specVersion,
        address indexed owner
    );

    event ConformerRegistered(
        uint256 indexed collectionId,
        uint256 indexed index,
        bytes32 cshHash,
        bytes32 sha256Id,
        int64   energyMilli
    );

    // ---------------------------------------------------------------- write

    /// @notice Return the id of the collection for (molecule, specVersion),
    ///         creating it if it does not exist yet.
    function openCollection(string calldata molecule, string calldata specVersion)
        public
        returns (uint256 collectionId)
    {
        require(bytes(molecule).length > 0, "molecule required");
        require(bytes(specVersion).length > 0, "specVersion required");

        bytes32 key = keccak256(abi.encode(molecule, specVersion));
        uint256 existing = _collectionByKey[key];
        if (existing != 0) {
            return existing - 1;
        }

        _collections.push(Collection({
            molecule:    molecule,
            specVersion: specVersion,
            owner:       msg.sender,
            createdAt:   uint64(block.timestamp),
            count:       0
        }));
        collectionId = _collections.length - 1;
        _collectionByKey[key] = collectionId + 1;
        emit CollectionCreated(collectionId, molecule, specVersion, msg.sender);
    }

    /// @notice Register one conformer into an existing collection.
    /// @dev sha256Id is the exact identifier and must be unique within the
    ///      collection; cshHash is a lossy sketch and collisions are expected,
    ///      so it is deliberately not used for deduplication.
    function registerConformer(
        uint256 collectionId,
        bytes32 cshHash,
        bytes32 sha256Id,
        int64   energyMilli
    )
        public
        returns (uint256 index)
    {
        require(collectionId < _collections.length, "no such collection");
        require(sha256Id != bytes32(0), "sha256Id required");
        require(!_seen[collectionId][sha256Id], "conformer already registered");

        _seen[collectionId][sha256Id] = true;
        _conformers[collectionId].push(Conformer({
            cshHash:     cshHash,
            sha256Id:    sha256Id,
            energyMilli: energyMilli,
            timestamp:   uint64(block.timestamp)
        }));
        index = _conformers[collectionId].length - 1;
        _collections[collectionId].count = uint32(index + 1);
        emit ConformerRegistered(collectionId, index, cshHash, sha256Id, energyMilli);
    }

    /// @notice Open a collection if needed and register one conformer into it.
    function openAndRegister(
        string calldata molecule,
        string calldata specVersion,
        bytes32 cshHash,
        bytes32 sha256Id,
        int64   energyMilli
    )
        external
        returns (uint256 collectionId, uint256 index)
    {
        collectionId = openCollection(molecule, specVersion);
        index = registerConformer(collectionId, cshHash, sha256Id, energyMilli);
    }

    /// @notice Register several conformers of one collection in a single call.
    function registerBatch(
        uint256   collectionId,
        bytes32[] calldata cshHashes,
        bytes32[] calldata sha256Ids,
        int64[]   calldata energiesMilli
    )
        external
    {
        require(cshHashes.length == sha256Ids.length &&
                cshHashes.length == energiesMilli.length, "length mismatch");
        for (uint256 i = 0; i < cshHashes.length; i++) {
            registerConformer(collectionId, cshHashes[i], sha256Ids[i], energiesMilli[i]);
        }
    }

    // ----------------------------------------------------------------- read

    function collectionCount() external view returns (uint256) {
        return _collections.length;
    }

    function getCollection(uint256 collectionId)
        external
        view
        returns (string memory molecule, string memory specVersion,
                 address owner, uint64 createdAt, uint32 count)
    {
        require(collectionId < _collections.length, "no such collection");
        Collection storage c = _collections[collectionId];
        return (c.molecule, c.specVersion, c.owner, c.createdAt, c.count);
    }

    /// @notice Look up a collection by its (molecule, specVersion) pair.
    /// @return found whether it exists, and its id when it does.
    function findCollection(string calldata molecule, string calldata specVersion)
        external
        view
        returns (bool found, uint256 collectionId)
    {
        uint256 stored = _collectionByKey[keccak256(abi.encode(molecule, specVersion))];
        return (stored != 0, stored == 0 ? 0 : stored - 1);
    }

    function conformerCount(uint256 collectionId) external view returns (uint256) {
        return _conformers[collectionId].length;
    }

    function getConformer(uint256 collectionId, uint256 index)
        external
        view
        returns (bytes32 cshHash, bytes32 sha256Id, int64 energyMilli, uint64 timestamp)
    {
        require(index < _conformers[collectionId].length, "no such conformer");
        Conformer storage c = _conformers[collectionId][index];
        return (c.cshHash, c.sha256Id, c.energyMilli, c.timestamp);
    }

    /// @notice Every hash in one collection, for client-side retrieval.
    /// @dev Hamming distances between these are meaningful; distances against
    ///      hashes from another collection are not.
    function getHashes(uint256 collectionId) external view returns (bytes32[] memory out) {
        Conformer[] storage list = _conformers[collectionId];
        out = new bytes32[](list.length);
        for (uint256 i = 0; i < list.length; i++) {
            out[i] = list[i].cshHash;
        }
    }
}
