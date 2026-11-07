import sqlite3
from pathlib import Path
import pandas as pd


def publish(frame: pd.DataFrame, db_path: str, table: str, keys: list[str], mode: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        if mode == "replace":
            frame.to_sql(table, conn, if_exists="replace", index=False)
        elif mode == "append":
            frame.to_sql(table, conn, if_exists='append', index=False)
        elif mode == "upsert":
            frame.to_sql(f"_{table}_stage", conn, if_exists="replace", index=False)
            cols = list(frame.columns)
            if not cols:
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(f'{c} TEXT' for c in keys)})")
            else:
                conn.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM _{table}_stage WHERE 0")
                nonkeys = [c for c in cols if c not in keys]
                updates = ", ".join(f'"{c}"=excluded."{c}"' for c in nonkeys)
                conflict = ", ".join(f'"{k}"' for k in keys)
                insert_cols = ", ".join(f'"{c}"' for c in cols)
                select_cols = ", ".join(f'"{c}"' for c in cols)
                sql = f'INSERT INTO "{table}" ({insert_cols}) SELECT {select_cols} FROM "_{table}_stage" WHERE 1 ON CONFLICT ({conflict}) '
                sql += f'DO UPDATE SET {updates}' if updates else 'DO NOTHING'
                # Ensure configured keys are enforced by a unique index.
                idx = f"ux_{table}_{'_'.join(keys)}"
                conn.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS "{idx}" ON "{table}" ({conflict})')
                conn.execute(sql)
            conn.execute(f'DROP TABLE IF EXISTS "_{table}_stage"')
        else:
            raise ValueError(f"Unsupported load mode: {mode}")
        conn.commit()
