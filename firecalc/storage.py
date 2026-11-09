"""Local SQLite persistence for spending categories and financial goals."""

from __future__ import annotations

import sqlite3
import json
from contextlib import closing
from pathlib import Path
from typing import Any


DATABASE_PATH = Path(__file__).resolve().parent.parent / ".firecalc.sqlite3"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sort_order INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL CHECK (amount >= 0),
            frequency TEXT NOT NULL,
            essential INTEGER NOT NULL,
            annual_inflation REAL NOT NULL,
            replacement_years INTEGER
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sort_order INTEGER NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    return connection


def load_expenses() -> list[dict[str, Any]]:
    with closing(_connect()) as connection, connection:
        rows = connection.execute(
            "SELECT category, amount, frequency, essential, annual_inflation, replacement_years "
            "FROM expenses ORDER BY sort_order, id"
        ).fetchall()
    return [
        {
            "category": row["category"],
            "amount": row["amount"],
            "frequency": row["frequency"],
            "essential": bool(row["essential"]),
            "annual_inflation": row["annual_inflation"],
            "replacement_years": row["replacement_years"] or (1 if row["frequency"] == "one-time" else None),
        }
        for row in rows
    ]


def save_expenses(expenses: list[dict[str, Any]]) -> None:
    """Replace the saved expense snapshot atomically."""
    with closing(_connect()) as connection, connection:
        connection.execute("DELETE FROM expenses")
        connection.executemany(
            """
            INSERT INTO expenses (
                sort_order, category, amount, frequency, essential, annual_inflation, replacement_years
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    index,
                    item["category"],
                    int(round(item["amount"])),
                    item["frequency"],
                    int(item["essential"]),
                    float(item.get("annual_inflation", 0.06)),
                    item.get("replacement_years") or (1 if item["frequency"] == "one-time" else None),
                )
                for index, item in enumerate(expenses)
            ],
        )


def load_goals() -> list[dict[str, Any]]:
    with closing(_connect()) as connection, connection:
        rows = connection.execute("SELECT payload FROM goals ORDER BY sort_order, id").fetchall()
    return [json.loads(row["payload"]) for row in rows]


def save_goals(goals: list[dict[str, Any]]) -> None:
    """Replace the saved goal snapshot atomically."""
    with closing(_connect()) as connection, connection:
        connection.execute("DELETE FROM goals")
        connection.executemany(
            "INSERT INTO goals (sort_order, payload) VALUES (?, ?)",
            [(index, json.dumps(goal, ensure_ascii=False)) for index, goal in enumerate(goals)],
        )
