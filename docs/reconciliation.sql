-- Target counts and referential integrity
SELECT 'customers' AS dataset, COUNT(*) AS target_rows FROM customers
UNION ALL
SELECT 'orders', COUNT(*) FROM orders;

SELECT COUNT(*) AS orphan_orders
FROM orders o LEFT JOIN customers c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;

-- Run-level reconciliation (input = accepted + rejected for fully parsed batches)
SELECT run_id, dataset, input_rows, valid_rows, rejected_rows,
       input_rows - valid_rows - rejected_rows AS unexplained_rows,
       status
FROM pipeline_runs
ORDER BY started_at;
