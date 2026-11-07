
import sqlite3
from pathlib import Path

import pandas as pd


def _quote(identifier: str) -> str:
    """Safely quote a SQLite identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def publish(
    frame: pd.DataFrame,
    db_path: str,
    table: str,
    keys: list[str],
    mode: str,
    order_column: str | None = None,
):
    """Publish records using append, replace, or configurable upsert."""

    if not keys:
        raise ValueError("At least one primary key is required")

    if mode not in {"replace", "append", "upsert"}:
        raise ValueError(f"Unsupported load mode: {mode}")

    if mode == "upsert":
        missing_keys = [key for key in keys if key not in frame.columns]
        if missing_keys:
            raise ValueError(f"Missing upsert key columns: {missing_keys}")

        if order_column and order_column not in frame.columns:
            raise ValueError(
                f"Ordering column '{order_column}' is missing from input"
            )

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    table_q = _quote(table)
    stage_name = f"_{table}_stage"
    stage_q = _quote(stage_name)

    with sqlite3.connect(db_path) as conn:
        if mode == "replace":
            frame.to_sql(table, conn, if_exists="replace", index=False)

        elif mode == "append":
            frame.to_sql(table, conn, if_exists="append", index=False)

        elif mode == "upsert":
            # Staging and target changes participate in the same transaction.
            frame.to_sql(stage_name, conn, if_exists="replace", index=False)

            cols = list(frame.columns)

            if not cols:
                raise ValueError("Cannot upsert a DataFrame without columns")

            nonkeys = [column for column in cols if column not in keys]

            conflict = ", ".join(_quote(key) for key in keys)
            insert_cols = ", ".join(_quote(column) for column in cols)
            select_cols = ", ".join(_quote(column) for column in cols)

            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table_q} "
                f"AS SELECT * FROM {stage_q} WHERE 0"
            )

            index_name = f"ux_{table}_{'_'.join(keys)}"
            index_q = _quote(index_name)

            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_q} "
                f"ON {table_q} ({conflict})"
            )

            if nonkeys:
                updates = ", ".join(
                    f"{_quote(column)} = excluded.{_quote(column)}"
                    for column in nonkeys
                )

                update_condition = ""

                if order_column:
                    timestamp_q = _quote(order_column)
                    update_condition = (
                        f" WHERE excluded.{timestamp_q} "
                        f"> {table_q}.{timestamp_q}"
                    )

                sql = (
                    f"INSERT INTO {table_q} ({insert_cols}) "
                    f"SELECT {select_cols} FROM {stage_q} WHERE 1 "
                    f"ON CONFLICT ({conflict}) "
                    f"DO UPDATE SET {updates}{update_condition}"
                )
            else:
                sql = (
                    f"INSERT INTO {table_q} ({insert_cols}) "
                    f"SELECT {select_cols} FROM {stage_q} WHERE 1 "
                    f"ON CONFLICT ({conflict}) DO NOTHING"
                )

            conn.execute(sql)
            conn.execute(f"DROP TABLE IF EXISTS {stage_q}")

        conn.commit()
