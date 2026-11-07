# YottaFlex Configurable Data Loading Framework

A local, metadata-driven data engineering framework built for the YottaFlex.ai 72-hour coding challenge.

The framework uses YAML configuration to define source paths, formats, schemas, keys, targets, and load modes instead of hard-coding dataset-specific behavior in the pipeline.

## Features

- CSV and JSON Lines ingestion, with optional Parquet support through `pyarrow` or `fastparquet`.
- YAML metadata for data types, nullability, primary keys, business rules, references, targets, and load modes (`append`, `replace`, `upsert`).
- Deterministic type casting and validation.
- Required-field, type, business-rule, duplicate-key, and foreign-key validation.
- Rejected records are quarantined with traceable rejection reasons.
- SQLite publishing with unique-key upserts.
- Pipeline run ledger, JSON metrics, source-file lineage, and per-run quarantine CSVs.
- Reproducible sample-data generator with a fixed random seed.
- Scalable data generation for 100,000+ orders.
- Automated pytest coverage for ingestion, validation, duplicates, empty batches, malformed data, and domain-specific cases.

## Architecture

```text
Source Files
     |
     v
YAML Configuration
     |
     v
Ingestion
     |
     v
Schema and Type Validation
     |
     v
Business Rule and Foreign-Key Checks
     |
     v
Valid / Rejected Record Split
     |
     +--------------------+
     |                    |
     v                    v
SQLite Publishing     Quarantine CSV
     |
     v
Run Ledger and JSON Metrics
```

### Entities and relationships

**Customers:** Parent entity, with `customer_id` as the primary key. Each row represents one customer.

**Orders:** Child transaction entity, with `order_id` as the primary key. Each order references `customers.customer_id`.

The order grain is one order record. This implementation models the latest processed state of each order rather than maintaining a complete event-sourcing history.

The `updated_at` field represents the order update timestamp and is stored in UTC.

## Requirements and setup

- Python 3.10 or later
- Git

### 1. Clone the repository

```bash
git clone https://github.com/rajeshrrln/yottaflex-configurable-data-loader.git
cd yottaflex-configurable-data-loader
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the virtual environment

**Windows PowerShell:**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS:**

```bash
source .venv/bin/activate
```

### 4. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

## Quick start

### Generate starter data

Generate 20 customers and 100 orders using seed 42:

```bash
python scripts/generate_data.py --customers 20 --orders 100 --seed 42
```

### Run the customer pipeline

```bash
python -m loader.cli --config config/customers.yaml --run-id customers-demo
```

### Run the orders pipeline

Load customers first because order validation depends on the customer records:

```bash
python -m loader.cli --config config/orders.yaml --run-id orders-demo
```

### Run automated tests

```bash
pytest
```

### Generate a larger dataset

```bash
python scripts/generate_data.py --customers 20000 --orders 100000 --seed 42
```

For a clean dataset without deliberately generated invalid records, use the `--clean` option.

The default generator includes examples such as invalid amounts, invalid references, unsupported currencies, duplicate keys, null amounts, and malformed JSON Lines.

## Outputs

The pipeline generates the following outputs:

**SQLite database**

`data/output/warehouse.db`

Contains:
- `customers`
- `orders`
- `pipeline_runs`

**Quarantine records**

`data/quarantine/<dataset>_<run_id>.csv`

Rejected records include available lineage information such as:
- `_reject_reason`
- `_source_row`
- `run_id`
- `source_file`

**Pipeline execution reports**

`reports/run_<run_id>.json`

Reports include:
- Run status
- Start and end timestamps
- Input, valid, rejected, and published row counts
- Execution duration
- Schema drift information
- Failure reason, when applicable

## Reconciliation

After loading both datasets, execute:

```bash
python scripts/reconcile.py
```

Example SQLite reconciliation queries:

```sql
SELECT 'customers' AS dataset, COUNT(*) AS target_rows
FROM customers

UNION ALL

SELECT 'orders', COUNT(*)
FROM orders;

SELECT
    status,
    SUM(input_rows) AS input_rows,
    SUM(valid_rows) AS valid_rows,
    SUM(rejected_rows) AS rejected_rows
FROM pipeline_runs
GROUP BY status;

SELECT COUNT(*) AS orphan_orders
FROM orders o
LEFT JOIN customers c
    ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
```

### Sample execution results

For the documented starter run using seed 42:

- Customers published: 20
- Orders input: 101 lines, including one malformed JSON line
- Orders published: 95
- Orders rejected: 6

The rejected records are retained in quarantine rather than silently discarded.

See `reports/sample_run_summary.json` for the recorded sample execution evidence.

## Idempotency, retries, and backfills

The `upsert` load mode uses configured keys and SQLite uniqueness constraints to avoid duplicate target keys during repeated execution.

Each pipeline execution receives a separate `run_id` and execution report.

For a failed run:
1. Inspect the execution report and failure reason.
2. Correct the source data or configuration.
3. Rerun using a new run ID.
4. Verify the published records and reconciliation results.

For historical backfills, configure the YAML source path to point to the historical input batch and execute it with a distinct run ID.

Use:
- `replace` for intentional full refreshes.
- `append` when repeated rows are acceptable or handled by the target design.
- `upsert` when records should be inserted or updated based on configured keys.

**Late-arriving data limitation:** The current upsert behavior is based on processing order. A previously processed newer record can be overwritten by an older record that arrives later. Event-time protection, watermarks, and full SCD Type 2 history are not currently implemented.

## Documentation

Additional documentation is available in `docs/`:

- `architecture.mmd` — Architecture diagram.
- `data_dictionary.md` — Entity grain, columns, types, nullability, and business rules.
- `design_notes.md` — Design decisions and trade-offs.
- `reconciliation.sql` — Reconciliation queries.
- `test_evidence.txt` — Recorded automated test output.
- `ai_prompt_history.md` — AI assistance and development disclosure.

## Performance and trade-offs

The recorded local performance run processed:

- 20,000 customers
- 100,000 orders
- 120,000 total records
- 7.763 seconds
- Approximately 15,457 input records per second

See `reports/performance_100k.json` for the recorded benchmark.

The implementation uses pandas vectorized operations for validation. A reasonable next optimization is chunked ingestion and publishing to reduce memory consumption for multi-million-row workloads.

SQLite provides a lightweight local review target. The publisher could be extended to PostgreSQL or a cloud warehouse while retaining the metadata-driven pipeline design.

## Limitations and future improvements

- The framework is a single-process local implementation, not a distributed orchestrator.
- Malformed JSON Lines are quarantined; malformed CSV syntax currently fails the batch during reading.
- Parquet support requires `pyarrow` or `fastparquet`.
- Late-arriving records currently follow processing-order upsert behavior.
- Full event history and SCD Type 2 tracking are not implemented.
- Production deployment would benefit from transactionally coordinated run-ledger and publishing operations, schema versioning, secret management, and integration testing against the target warehouse.
- Chunked ingestion would improve scalability for larger workloads.

## Submission checklist

1. Run `pytest` and update `docs/test_evidence.txt` with the actual output.
2. Run both customer and order configurations.
3. Inspect execution reports and quarantine files.
4. Run reconciliation and verify the results.
5. Ensure the GitHub repository is public.
6. Submit the repository URL through the YottaFlex.ai portal before the stated deadline.

The architecture flow is also available in `docs/architecture.mmd`. Synthetic sample output is available in `sample_output/`.