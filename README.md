# YottaFlex Configurable Data Loading Framework

A local, metadata-driven data engineering vertical slice for the YottaFlex.ai 72-hour challenge. Source location, format, schema, keys, target and load mode live in YAML; dataset-specific behavior is not hard-coded in the pipeline.

## Features
- CSV and JSON Lines ingestion (Parquet reader included; install a Parquet engine such as `pyarrow` to use it).
- YAML metadata for types, nullability, primary keys, business rules, references, targets and load modes (`append`, `replace`, `upsert`).
- Deterministic casting, required-field/type/business-rule checks, duplicate quarantine, foreign-key checks and malformed JSONL quarantine.
- SQLite target with unique-key upserts, run ledger, JSON metrics, source-file lineage and per-run quarantine CSVs.
- Reproducible generator with a fixed seed and edge-case records; configurable to 100,000+ orders.
- Pytest coverage for happy path components, empty batch, malformed/schema changes, nulls, duplicates, invalid amounts, enum values, referential integrity and reruns.

## Architecture
`source file -> YAML config -> ingestion -> schema/type validation -> business/FK checks -> valid/reject split -> SQLite publish + quarantine -> run ledger + JSON report`.

Customers are the parent entity (`customer_id`, one row per customer). Orders are the child transaction entity (`order_id`, one row per order) and reference `customers.customer_id`. The order grain is one order event; this example models the latest state of each order, not a full event-sourcing history. `updated_at` is UTC and retained for later change-history extensions.

## Requirements and setup
Python 3.10+.

```bash
git clone https://github.com/<your-username>/yottaflex-configurable-data-loader.git
cd yottaflex-configurable-data-loader
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -e '.[dev]'
```

## Quick start
Generate the starter dataset (20 customers, 100 orders; fixed seed 42):

```bash
python scripts/generate_data.py --customers 20 --orders 100 --seed 42
```

Load the parent table first, then orders (foreign-key validation depends on customers being present):

```bash
python -m loader.cli --config config/customers.yaml --run-id customers-demo
python -m loader.cli --config config/orders.yaml --run-id orders-demo
```

Run tests:

```bash
pytest
```

Generate a larger workload:

```bash
python scripts/generate_data.py --customers 20000 --orders 100000 --seed 42
```

For a clean, all-valid sample, add `--clean`. The default generator deliberately inserts invalid amount, invalid reference, unsupported currency, duplicate key, null amount and malformed JSONL examples.

## Outputs
- `data/output/warehouse.db`: `customers`, `orders`, and `pipeline_runs` tables.
- `data/quarantine/<dataset>_<run_id>.csv`: rejected rows with `_reject_reason`, `_source_row` where available, `run_id` and `source_file`.
- `reports/run_<run_id>.json`: run status, timestamps, input/valid/rejected/published counts, duration, schema drift and failure reason.

Example reconciliation (SQLite):

```sql
SELECT 'customers' AS dataset, COUNT(*) AS target_rows FROM customers
UNION ALL
SELECT 'orders', COUNT(*) FROM orders;

SELECT status, SUM(input_rows) AS input_rows,
       SUM(valid_rows) AS valid_rows,
       SUM(rejected_rows) AS rejected_rows
FROM pipeline_runs GROUP BY status;

SELECT COUNT(*) AS orphan_orders
FROM orders o LEFT JOIN customers c ON o.customer_id=c.customer_id
WHERE c.customer_id IS NULL;
```

Expected starter run (seed 42): customers publishes 20 rows. Orders input includes 100 JSON records plus one malformed line; the verified run published 95 orders and quarantined 6 records (four invalid business/reference/null cases, one duplicate key and one malformed JSON line). See `reports/sample_run_summary.json`. Rejected examples are intentionally not silently dropped.

## Idempotency, retries and backfills
`upsert` uses configured keys and a SQLite unique index. Re-running the same source does not create duplicate target keys; a later record for the same key updates the row. Each execution has a separate `run_id` and metrics report. A failed run is recorded with a failure reason; fix the source/config and rerun with a new run ID. For a backfill, point the YAML source path to the historical batch and run it with a distinct run ID. Use `replace` only for intentional full refreshes and `append` only when the target is designed to accept repeated rows.

## Data dictionary
See [`docs/data_dictionary.md`](docs/data_dictionary.md) for entity grain, columns, types, nullability and rules.

## Performance and trade-offs
A measured run processed 20,000 customers plus 100,000 orders (120,000 total) in 7.763 seconds, approximately 15,457 input rows/second, on the local Python + pandas + SQLite environment used for this build. See `reports/performance_100k.json`. Validation uses vectorized pandas operations; the next optimization is chunked ingestion and publishing to cap memory use on multi-million-row inputs. SQLite is a local review target; a production deployment could swap the publisher for Postgres, a lakehouse table format or a cloud warehouse without changing dataset metadata concepts.

## Limitations and next steps
- This is a single-process local reference implementation, not a distributed orchestrator.
- JSONL malformed records are quarantined; malformed CSV syntax currently fails the batch at read time.
- Parquet reading requires `pyarrow` or `fastparquet` to be installed.
- Late/out-of-order order updates are handled by upsert (last processed record wins); event-time watermarking and full SCD2 history are future extensions.
- For strict production guarantees, use transactionally coordinated run-ledger and publish operations, structured schema versioning, secret management and integration tests against the chosen warehouse.

## Submission checklist
1. Run `pytest` and save the terminal output in `docs/test_evidence.txt`.
2. Run both configs and inspect `reports/` and quarantine CSVs.
3. Create a **public** GitHub repository and push this project.
4. Paste the public repository URL into the YottaFlex submission form before **9 Nov 2026, 14:55 UTC**.

Run the reconciliation utility after loading both datasets:

```bash
python scripts/reconcile.py
```

The architecture flow is also available as Mermaid source in `docs/architecture.mmd`. Committed sample target extracts are in `sample_output/`; they are derived from the starter run and contain synthetic records only.
