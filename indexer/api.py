"""REST API for the CSH V2 indexer.

Three endpoints:
  GET /health                  -> sanity check + DB stats
  GET /similar?hash=...&t=...  -> fuzzy similarity search
  GET /event/{csh_hash}        -> single event details
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from database import SessionLocal, ConformerEvent, IndexerState, event_count
from lsh import find_similar, LSHBand


app = FastAPI(
    title="CSH V2 Registry API",
    description=(
        "Fuzzy similarity search over conformational soft hashes "
        "registered on Ethereum Sepolia."
    ),
    version="0.1.0",
)


# ─── Response models ──────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    total_events: int
    last_indexed_block: int
    indexed_hashes: int


class EventResponse(BaseModel):
    csh_hash: str
    registrant: str
    timestamp: int
    molecule_name: str
    sha256_id: str
    energy_kcal_mol: float
    block_number: int
    tx_hash: str
    etherscan_url: str


class SimilarMatch(BaseModel):
    event: EventResponse
    hamming_distance: int = Field(..., description="Bits differing from query")


class SimilarResponse(BaseModel):
    query_hash: str
    threshold: int
    num_matches: int
    matches: list[SimilarMatch]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def event_to_response(ev: ConformerEvent) -> EventResponse:
    return EventResponse(
        csh_hash=ev.csh_hash,
        registrant=ev.registrant,
        timestamp=ev.timestamp,
        molecule_name=ev.molecule_name,
        sha256_id=ev.sha256_id,
        energy_kcal_mol=ev.energy_x1000 / 1000,
        block_number=ev.block_number,
        tx_hash=ev.tx_hash,
        etherscan_url=f"https://sepolia.etherscan.io/tx/{ev.tx_hash}",
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
def health():
    """Server health check + database statistics."""
    with SessionLocal() as session:
        state = session.query(IndexerState).first()
        total = event_count(session)
        indexed = session.query(LSHBand.csh_hash).distinct().count()

    return HealthResponse(
        status="ok",
        total_events=total,
        last_indexed_block=state.last_indexed_block if state else 0,
        indexed_hashes=indexed,
    )


@app.get("/similar", response_model=SimilarResponse)
def similar(
    hash: str = Query(..., description="CSH hash to query (hex, 0x prefix)"),
    threshold: int = Query(5, ge=0, le=64,
                           description="Maximum Hamming distance"),
):
    """Fuzzy similarity search.

    Returns conformers within Hamming distance ≤ threshold from the query.
    """
    # Validate hash format
    if not hash.startswith("0x"):
        raise HTTPException(400, "hash must start with '0x'")
    hex_part = hash[2:]
    if not all(c in "0123456789abcdefABCDEF" for c in hex_part):
        raise HTTPException(400, "hash contains non-hex characters")
    if len(hex_part) < 16:
        raise HTTPException(400, "hash must be at least 16 hex chars (64 bits)")

    with SessionLocal() as session:
        results = find_similar(session, hash, max_hamming=threshold)
        matches = [
            SimilarMatch(
                event=event_to_response(ev),
                hamming_distance=d,
            )
            for ev, d in results
        ]

    return SimilarResponse(
        query_hash=hash,
        threshold=threshold,
        num_matches=len(matches),
        matches=matches,
    )


@app.get("/event/{csh_hash}", response_model=EventResponse)
def get_event(csh_hash: str):
    """Retrieve a single event by exact CSH hash."""
    if not csh_hash.startswith("0x"):
        csh_hash = "0x" + csh_hash

    with SessionLocal() as session:
        event = session.query(ConformerEvent).filter_by(
            csh_hash=csh_hash
        ).first()
        if not event:
            raise HTTPException(404, f"No event found for hash {csh_hash}")
        return event_to_response(event)


# ─── Run server (for local dev) ───────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
