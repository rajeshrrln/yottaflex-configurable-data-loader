import argparse, json, sqlite3
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='Check target counts and order referential integrity')
    parser.add_argument('--db',default='data/output/warehouse.db')
    args=parser.parse_args()
    with sqlite3.connect(args.db) as conn:
        counts={name:conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in ('customers','orders')}
        orphan_count=conn.execute('SELECT COUNT(*) FROM orders o LEFT JOIN customers c ON o.customer_id=c.customer_id WHERE c.customer_id IS NULL').fetchone()[0]
        runs=conn.execute('SELECT run_id,dataset,input_rows,valid_rows,rejected_rows,status FROM pipeline_runs ORDER BY started_at').fetchall()
    result={'target_counts':counts,'orphan_orders':orphan_count,'runs':[dict(zip(['run_id','dataset','input_rows','valid_rows','rejected_rows','status'],r)) for r in runs], 'status':'PASS' if orphan_count==0 else 'FAIL'}
    print(json.dumps(result,indent=2))
    if orphan_count: raise SystemExit(1)

if __name__=='__main__': main()
