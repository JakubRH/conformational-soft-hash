"""LSH banding for fuzzy similarity search over 64-bit CSH hashes.

Strategy: split each 64-bit hash into B bands of r bits each.
Two hashes are similarity candidates iff at least one band matches.

For B=8, r=8: each band has 256 possible values.
For Hamming distance ≤ 5 out of 64 bits, the probability that all 8 bands
differ is roughly C(64,5) ≈ 7.6M ways out of (2^64) ≈ 1.8e19.
LSH banding catches almost all true positives with very few false negatives.

For exact analysis see: Indyk & Motwani 1998, Charikar 2002.
"""

from typing import Iterator
from sqlalchemy import Column, String, Integer, ForeignKey, Index
from sqlalchemy.orm import relationship

from database import Base, ConformerEvent


# ─── Configuration ────────────────────────────────────────────────────────────

NUM_BANDS = 8        # B
BITS_PER_BAND = 8    # r
HASH_BITS = NUM_BANDS * BITS_PER_BAND  # = 64

assert HASH_BITS == 64, "CSH is 64-bit; check NUM_BANDS * BITS_PER_BAND"


# ─── Database table for the LSH index ─────────────────────────────────────────

class LSHBand(Base):
    """One row per (csh_hash, band_index) pair.

    Each conformer contributes B rows (B = NUM_BANDS).
    The (band_index, band_value) tuple is the lookup key.
    """
    __tablename__ = "lsh_bands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    csh_hash = Column(
        String(66),
        ForeignKey("conformer_events.csh_hash"),
        nullable=False,
    )
    band_index = Column(Integer, nullable=False)        # 0 to B-1
    band_value = Column(Integer, nullable=False)        # 0 to 2^r - 1

    # Composite index for fast lookup
    __table_args__ = (
        Index("ix_lsh_band_lookup", "band_index", "band_value"),
    )


# ─── Hash splitting ───────────────────────────────────────────────────────────

def hash_to_bands(csh_hash: str) -> list[int]:
    """Split a 64-bit hash (as hex string) into B bands of r bits.

    Args:
        csh_hash: hex string starting with "0x", with at least 16 hex chars
                  representing the 64-bit hash. Padding (extra zeros) ignored.

    Returns:
        List of B integers, each in [0, 2^r - 1].
    """
    # Strip "0x" prefix and take first 16 hex chars (64 bits)
    hex_part = csh_hash[2:] if csh_hash.startswith("0x") else csh_hash
    hex_64bit = hex_part[:16]  # 16 hex chars = 64 bits

    # Convert to a single 64-bit integer
    value = int(hex_64bit, 16)

    # Split into B bands of r bits each
    bands = []
    mask = (1 << BITS_PER_BAND) - 1  # e.g., 0xff for r=8
    for i in range(NUM_BANDS):
        shift = i * BITS_PER_BAND
        band_value = (value >> shift) & mask
        bands.append(band_value)
    return bands


def hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two CSH hashes (over 64 bits)."""
    h1 = int(hash1[2:18], 16) if hash1.startswith("0x") else int(hash1[:16], 16)
    h2 = int(hash2[2:18], 16) if hash2.startswith("0x") else int(hash2[:16], 16)
    return bin(h1 ^ h2).count("1")


# ─── Indexing operations ──────────────────────────────────────────────────────

def index_event(session, csh_hash: str):
    """Add B band rows for a single conformer hash."""
    bands = hash_to_bands(csh_hash)
    for i, value in enumerate(bands):
        session.add(LSHBand(
            csh_hash=csh_hash,
            band_index=i,
            band_value=value,
        ))


def index_all_events(session):
    """Build the LSH index for all events not yet indexed.

    Idempotent: skips events already in lsh_bands.
    """
    # Find events that have no band rows yet
    indexed_hashes = set(
        row[0] for row in session.query(LSHBand.csh_hash).distinct()
    )
    all_events = session.query(ConformerEvent).all()
    to_index = [ev for ev in all_events if ev.csh_hash not in indexed_hashes]

    print(f"Total events:           {len(all_events)}")
    print(f"Already indexed:        {len(indexed_hashes)}")
    print(f"To index:               {len(to_index)}")

    for ev in to_index:
        index_event(session, ev.csh_hash)
    session.commit()
    print(f"Indexed {len(to_index)} new event(s).")


# ─── Fuzzy search ─────────────────────────────────────────────────────────────

def find_similar(
    session,
    query_hash: str,
    max_hamming: int = 5,
) -> list[tuple[ConformerEvent, int]]:
    """Find conformers similar to query_hash within Hamming distance.

    Returns list of (event, hamming_distance) tuples, sorted ascending.
    """
    query_bands = hash_to_bands(query_hash)

    # Step 1: candidate retrieval — any hash sharing at least one band
    candidate_hashes: set[str] = set()
    for i, value in enumerate(query_bands):
        rows = session.query(LSHBand.csh_hash).filter_by(
            band_index=i,
            band_value=value,
        ).all()
        candidate_hashes.update(r[0] for r in rows)

    # Step 2: exact verification — compute Hamming for each candidate
    results = []
    for candidate in candidate_hashes:
        d = hamming_distance(query_hash, candidate)
        if d <= max_hamming:
            event = session.query(ConformerEvent).filter_by(
                csh_hash=candidate
            ).first()
            if event:
                results.append((event, d))

    # Sort by Hamming distance
    results.sort(key=lambda x: x[1])
    return results


# ─── Self-test and index build ────────────────────────────────────────────────

if __name__ == "__main__":
    from database import init_db, SessionLocal, event_count

    print("=" * 60)
    print("LSH banding — index build")
    print("=" * 60)
    print(f"Configuration: {NUM_BANDS} bands × {BITS_PER_BAND} bits = "
          f"{HASH_BITS} bits per hash")

    init_db()

    with SessionLocal() as session:
        index_all_events(session)

    # Demo: find similar to the test conformer
    test_hash = "0x" + "ab" * 32
    print(f"\nDemo query: {test_hash[:18]}...")

    with SessionLocal() as session:
        results = find_similar(session, test_hash, max_hamming=5)
        print(f"Found {len(results)} similar conformer(s) within Hamming ≤ 5:")
        for event, d in results:
            print(f"  Hamming={d}  {event.molecule_name}  "
                  f"(block {event.block_number})")

