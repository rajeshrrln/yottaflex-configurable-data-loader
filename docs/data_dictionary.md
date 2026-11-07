# Data dictionary

## customers — customer master
**Grain:** one current record per `customer_id`. **Primary key:** `customer_id`.

| Column | Type | Nullable | Rule / meaning |
|---|---|---:|---|
| customer_id | string | no | Stable source business key |
| customer_name | string | no | Display name |
| email | string | no | Must match basic email pattern |
| signup_date | date | no | ISO date; cannot be future-dated |
| country_code | string | no | Two uppercase letters |
| updated_at | timestamp | no | Source update time; normalized to UTC |
| run_id | string | no (lineage) | Pipeline execution ID |
| source_file | string | no (lineage) | Configured source path |

## orders — order transactions
**Grain:** one current state per `order_id`. **Primary key:** `order_id`. **Foreign key:** `customer_id -> customers.customer_id`.

| Column | Type | Nullable | Rule / meaning |
|---|---|---:|---|
| order_id | string | no | Stable order key |
| customer_id | string | no | Must exist in customer target |
| order_date | date | no | Business event date |
| amount | decimal | no | Strictly greater than zero |
| currency | string | no | INR, USD or EUR |
| status | string | no | PLACED, PAID, SHIPPED, CANCELLED or REFUNDED |
| updated_at | timestamp | no | Source update time; normalized to UTC |
| run_id | string | no (lineage) | Pipeline execution ID |
| source_file | string | no (lineage) | Configured source path |

## Operational table: pipeline_runs
One row per run ID with dataset, source file, UTC start/end, status, row counts, duration and failure reason. Quarantine CSVs retain rejected source fields and a machine-readable `_reject_reason`.

## Assumptions
- IDs are stable strings supplied by source systems; the loader does not generate surrogate IDs.
- Duplicate business keys inside one batch: last input occurrence wins; earlier duplicates are quarantined.
- `upsert` implements latest processed state, not complete history. If full event history is required, use an append-only event table or SCD Type 2 target.
- Nulls in non-nullable columns are rejected. Unexpected extra columns are reported as schema drift; missing declared columns fail the batch.
