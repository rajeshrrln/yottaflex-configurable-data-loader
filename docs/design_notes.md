# Design and trade-off note

1. **Metadata over dataset-specific code:** YAML carries source format/path, schema, keys, target and load mode. The same pipeline modules process both customers and orders.
2. **Local reproducibility:** SQLite avoids credentials and external infrastructure, making review straightforward. It is not intended as a high-concurrency warehouse.
3. **Explicit reject path:** validation returns accepted and rejected records separately; each reject has a reason and source lineage.
4. **Idempotency:** configured business keys become a unique index and `upsert` prevents duplicate target keys on reruns.
5. **Parent-child order:** customers load before orders so reference validation can query the parent target.
6. **History trade-off:** this vertical slice stores latest state for each order. A production event-history requirement should use append-only events or SCD2 with effective timestamps.
7. **Performance:** row-wise validation is easy to inspect and explain. Vectorized checks and chunked ingestion/publishing are the first optimization candidates for 100k+ rows.
