"""SQLite database for the CSH V2 indexer.

Stores:
  - ConformerEvent: one row per registered conformer (from blockchain events)
  - IndexerState: singleton tracking the last indexed block
"""

from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker

# Database file lives next to this module
DB_PATH = Path(__file__).resolve().parent / "csh_indexer.db"
DB_URL = f"sqlite:///{DB_PATH}"

Base = declarative_base()


class ConformerEvent(Base):
    """One conformer registration as recorded on-chain."""
    __tablename__ = "conformer_events"

    # Blockchain identity (cshHash is unique by design — contract enforces it)
    csh_hash = Column(String(66), primary_key=True)  # "0x" + 64 hex chars

    # Event payload
    registrant = Column(String(42), nullable=False, index=True)
    timestamp = Column(BigInteger, nullable=False)
    molecule_name = Column(String(256), nullable=False)
    sha256_id = Column(String(256), nullable=False)
    energy_x1000 = Column(BigInteger, nullable=False)

    # Provenance
    block_number = Column(BigInteger, nullable=False, index=True)
    tx_hash = Column(String(66), nullable=False)

    # When our indexer recorded this
    indexed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return (
            f"<ConformerEvent(csh_hash={self.csh_hash[:18]}..., "
            f"name={self.molecule_name}, block={self.block_number})>"
        )


class IndexerState(Base):
    """Singleton row tracking indexer progress."""
    __tablename__ = "indexer_state"

    id = Column(Integer, primary_key=True, default=1)  # always 1
    last_indexed_block = Column(BigInteger, nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (
            f"<IndexerState(last_block={self.last_indexed_block}, "
            f"updated={self.updated_at})>"
        )


# ─── Engine and session factory ───────────────────────────────────────────────

engine = create_engine(DB_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """Create tables if they don't exist."""
    Base.metadata.create_all(engine)
    print(f"Database initialized at: {DB_PATH}")


def get_state(session, default_start_block: int) -> IndexerState:
    """Get or create the indexer state row."""
    state = session.query(IndexerState).filter_by(id=1).first()
    if state is None:
        state = IndexerState(id=1, last_indexed_block=default_start_block - 1)
        session.add(state)
        session.commit()
    return state


def event_count(session) -> int:
    """Total number of registered events in the database."""
    return session.query(ConformerEvent).count()


# ─── Self-test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Initializing database...")
    init_db()

    with SessionLocal() as session:
        state = get_state(session, default_start_block=1)
        print(f"Current state: {state}")
        print(f"Total events: {event_count(session)}")
