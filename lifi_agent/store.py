"""
LI.FI Intents Agent — Persistent quote history (SQLite).
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


DB_FILE = Path.home() / ".lifi_agent_quotes.db"


class QuoteStore:
    """Persistent quote history using SQLite."""

    def __init__(self, db_path: Path = DB_FILE):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent TEXT,
                    from_chain TEXT,
                    to_chain TEXT,
                    token TEXT,
                    input_amount TEXT,
                    output_amount TEXT,
                    fee_pct TEXT,
                    quote_id TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def store(self, intent_repr: str, from_chain: str, to_chain: str,
              token: str, input_amount: str, output_amount: str,
              fee_pct: Optional[str], quote_id: str):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO quotes (intent, from_chain, to_chain, token,
                                  input_amount, output_amount, fee_pct, quote_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (intent_repr, from_chain, to_chain, token, input_amount,
                  output_amount, fee_pct, quote_id))
            conn.commit()

    def get_recent(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM quotes ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
            if total == 0:
                return {"total": 0, "avg_fee": 0, "top_routes": [], "top_tokens": []}

            avg_fee = conn.execute(
                "SELECT AVG(CAST(fee_pct AS REAL)) FROM quotes WHERE fee_pct != '999'"
            ).fetchone()[0] or 0

            top_routes = conn.execute("""
                SELECT from_chain, to_chain, COUNT(*) as cnt
                FROM quotes GROUP BY from_chain, to_chain
                ORDER BY cnt DESC LIMIT 5
            """).fetchall()

            top_tokens = conn.execute("""
                SELECT token, COUNT(*) as cnt
                FROM quotes GROUP BY token
                ORDER BY cnt DESC LIMIT 3
            """).fetchall()

            return {
                "total": total,
                "avg_fee": round(avg_fee, 3),
                "top_routes": [(r[0], r[1], r[2]) for r in top_routes],
                "top_tokens": [(t[0], t[1]) for t in top_tokens],
            }


_quote_store = None

def get_quote_store() -> QuoteStore:
    global _quote_store
    if _quote_store is None:
        _quote_store = QuoteStore()
    return _quote_store
