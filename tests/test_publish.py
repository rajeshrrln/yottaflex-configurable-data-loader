
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


def test_failed_upsert_preserves_existing_record(tmp_path):
    db = str(tmp_path / "recovery.db")

    publish(
        make_order(500, "2026-01-01T10:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TRIGGER reject_bad_update
            BEFORE UPDATE ON orders
            WHEN NEW.amount = 999
            BEGIN
                SELECT RAISE(ABORT, 'simulated publishing failure');
            END
        """)

    with pytest.raises(sqlite3.IntegrityError):
        publish(
            make_order(999, "2026-01-01T12:00:00Z"),
            db, "orders", ["order_id"], "upsert",
            order_column="updated_at",
        )

    assert read_order(db) == (500, "2026-01-01T10:00:00Z")


def test_corrected_retry_succeeds_after_failure(tmp_path):
    db = str(tmp_path / "retry.db")

    publish(
        make_order(500, "2026-01-01T10:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TRIGGER reject_bad_update
            BEFORE UPDATE ON orders
            WHEN NEW.amount = 999
            BEGIN
                SELECT RAISE(ABORT, 'simulated publishing failure');
            END
        """)

    with pytest.raises(sqlite3.IntegrityError):
        publish(
            make_order(999, "2026-01-01T12:00:00Z"),
            db, "orders", ["order_id"], "upsert",
            order_column="updated_at",
        )

    with sqlite3.connect(db) as conn:
        conn.execute("DROP TRIGGER reject_bad_update")

    publish(
        make_order(700, "2026-01-01T11:00:00Z"),
        db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    assert read_order(db) == (700, "2026-01-01T11:00:00Z")


def test_repeated_retry_does_not_create_duplicates(tmp_path):
    db = str(tmp_path / "idempotent.db")
    frame = make_order(700, "2026-01-01T11:00:00Z")

    publish(
        frame, db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    publish(
        frame, db, "orders", ["order_id"], "upsert",
        order_column="updated_at",
    )

    with sqlite3.connect(db) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM orders WHERE order_id='O100'"
        ).fetchone()[0]

    assert count == 1
