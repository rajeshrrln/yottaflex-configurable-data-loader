
import sqlite3

import pandas as pd
import pytest

from loader.publish import publish


def make_order(amount, updated_at):
    return pd.DataFrame([{
        "order_id": "O100",
        "customer_id": "C1",
        "amount": amount,
        "updated_at": updated_at,
    }])


def read_order(db_path):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            "SELECT amount, updated_at FROM orders WHERE order_id='O100'"
        ).fetchone()


def test_newer_order_update_is_published(tmp_path):
    db = str(tmp_path / "test.db")

    publish(
        make_order(500, "2026-01-01T10:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    publish(
        make_order(700, "2026-01-01T11:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    assert read_order(db) == (700, "2026-01-01T11:00:00Z")


def test_older_order_update_is_ignored(tmp_path):
    db = str(tmp_path / "test.db")

    publish(
        make_order(500, "2026-01-01T10:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    publish(
        make_order(300, "2026-01-01T09:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    assert read_order(db) == (500, "2026-01-01T10:00:00Z")


def test_equal_timestamp_does_not_overwrite(tmp_path):
    db = str(tmp_path / "test.db")

    publish(
        make_order(500, "2026-01-01T10:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    publish(
        make_order(900, "2026-01-01T10:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    assert read_order(db) == (500, "2026-01-01T10:00:00Z")


def test_missing_ordering_column_fails(tmp_path):
    db = str(tmp_path / "test.db")
    frame = pd.DataFrame([{"order_id": "O1", "amount": 100}])

    with pytest.raises(ValueError, match="Ordering column"):
        publish(
            frame, db, "orders", ["order_id"], "upsert",
            order_column="updated_at",
        )
