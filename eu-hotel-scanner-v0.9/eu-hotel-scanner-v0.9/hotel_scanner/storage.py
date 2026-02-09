from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import CountryMetrics


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "hotel_scanner.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_utc TEXT NOT NULL,
            checkin TEXT NOT NULL,
            checkout TEXT NOT NULL,
            scan_mode TEXT NOT NULL,
            alpha REAL NOT NULL,
            min_price REAL,
            max_price REAL
        )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS country_metrics (
            run_id INTEGER NOT NULL,
            country_code TEXT NOT NULL,
            country_name TEXT NOT NULL,
            cost_index REAL NOT NULL,
            min_price REAL NOT NULL,
            median_price REAL NOT NULL,
            p90_price REAL NOT NULL,
            effective_min REAL NOT NULL,
            effective_median REAL NOT NULL,
            PRIMARY KEY (run_id, country_code),
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        )"""
    )
    conn.commit()


def log_run(
    conn: sqlite3.Connection,
    checkin,
    checkout,
    scan_mode: str,
    alpha: float,
    min_price: Optional[float],
    max_price: Optional[float],
) -> int:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO runs (created_utc, checkin, checkout, scan_mode, alpha, min_price, max_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.utcnow().isoformat(timespec="seconds") + "Z",
            str(checkin),
            str(checkout),
            scan_mode,
            float(alpha),
            float(min_price) if min_price is not None else None,
            float(max_price) if max_price is not None else None,
        ),
    )
    conn.commit()
    return cur.lastrowid


def log_country_metrics(
    conn: sqlite3.Connection,
    run_id: int,
    metrics_by_country: Dict[str, CountryMetrics],
) -> None:
    cur = conn.cursor()
    rows = []
    for m in metrics_by_country.values():
        rows.append(
            (
                run_id,
                m.country_code,
                m.country_name,
                float(m.cost_index),
                float(m.min_price_per_night),
                float(m.median_price_per_night),
                float(m.p90_price_per_night),
                float(m.effective_min_price),
                float(m.effective_median_price),
            )
        )
    cur.executemany(
        """INSERT OR REPLACE INTO country_metrics
        (run_id, country_code, country_name, cost_index,
         min_price, median_price, p90_price, effective_min, effective_median)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()


def get_latest_run_id(conn: sqlite3.Connection) -> Optional[int]:
    cur = conn.cursor()
    cur.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    return int(row["id"]) if row else None


def get_historical_country_summary(conn: sqlite3.Connection) -> List[dict]:
    """Aggregate median prices across runs and compare vs cost index.

    Returns one row per country with:
    - avg_median_price
    - avg_effective_median
    - normalized_median = avg_median_price / cost_index
    """
    cur = conn.cursor()
    cur.execute(
        """SELECT
                country_code,
                country_name,
                cost_index,
                AVG(median_price) AS avg_median_price,
                AVG(effective_median) AS avg_effective_median
            FROM country_metrics
            GROUP BY country_code, country_name, cost_index
        """
    )
    rows = []
    for r in cur.fetchall():
        cost_index = float(r["cost_index"])
        avg_median = float(r["avg_median_price"])
        normalized = avg_median / cost_index if cost_index > 0 else avg_median
        rows.append(
            {
                "country_code": r["country_code"],
                "country_name": r["country_name"],
                "cost_index": cost_index,
                "avg_median_price": avg_median,
                "avg_effective_median": float(r["avg_effective_median"]),
                "normalized_median": normalized,
            }
        )
    return rows
