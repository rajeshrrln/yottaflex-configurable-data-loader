from pathlib import Path
from datetime import datetime, timezone
import json, logging, sqlite3, uuid
import pandas as pd
from .config import load_config
from .ingest import read_source
from .validate import validate_frame
from .publish import publish

ROOT = Path.cwd()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("yotta_loader")


def run_pipeline(config_path: str, run_id: str | None = None, base_dir: str | Path | None = None):
    started = datetime.now(timezone.utc)
    run_id = run_id or str(uuid.uuid4())
    base = Path(base_dir or Path.cwd())
    cfg = load_config(base / config_path)
    dataset = cfg["dataset"]["name"]
    source_path = base / cfg["source"]["path"]
    target_path = base / cfg["target"]["path"]
    run_meta = {"run_id": run_id, "dataset": dataset, "source_file": str(cfg["source"]["path"]), "started_at": started.isoformat(), "status": "running"}
    malformed = []
    try:
        raw = read_source(source_path, cfg["source"]["format"], cfg["source"].get("options"))
        malformed = raw.attrs.get("malformed_records", [])
        if raw.empty and len(raw.columns) == 0:
            raw = pd.DataFrame(columns=list(cfg["schema"]))
        # Parent datasets must be loaded before child datasets for FK validation.
        refs = {}
        for ref in cfg.get("references", []):
            with sqlite3.connect(target_path) as conn:
                try:
                    refs[ref["dataset"]] = {r[0] for r in conn.execute(f'SELECT "{ref["target_column"]}" FROM "{ref["target_table"]}"').fetchall()}
                except sqlite3.Error:
                    refs[ref["dataset"]] = set()
        valid, rejected, schema_info = validate_frame(raw, cfg, refs)
        if malformed:
            rejected = pd.concat([rejected, pd.DataFrame(malformed)], ignore_index=True, sort=False)
        # Attach operational lineage to accepted rows.
        valid["run_id"] = run_id
        valid["source_file"] = str(cfg["source"]["path"])
        publish(valid, str(target_path), cfg["target"]["table"], cfg["keys"], cfg["target"]["load_mode"])
        quarantine_path = base / "data/quarantine" / f"{dataset}_{run_id}.csv"
        if not rejected.empty:
            quarantine_path.parent.mkdir(parents=True, exist_ok=True)
            rejected["run_id"] = run_id
            rejected["source_file"] = str(cfg["source"]["path"])
            rejected.to_csv(quarantine_path, index=False)
        finished = datetime.now(timezone.utc)
        metrics = {**run_meta, "status": "success", "ended_at": finished.isoformat(), "input_rows": len(raw) + len(malformed), "valid_rows": len(valid), "rejected_rows": len(rejected), "published_rows": len(valid), "schema_drift": schema_info["unexpected_columns"], "quarantine_file": str(quarantine_path) if not rejected.empty else None, "duration_seconds": (finished-started).total_seconds()}
        _record_run(target_path, metrics)
        _write_metrics(base, metrics)
        log.info("run=%s dataset=%s status=success input=%s valid=%s rejected=%s", run_id, dataset, metrics["input_rows"], len(valid), len(rejected))
        return metrics
    except Exception as exc:
        finished = datetime.now(timezone.utc)
        metrics = {**run_meta, "status": "failed", "ended_at": finished.isoformat(), "input_rows": 0, "valid_rows": 0, "rejected_rows": len(malformed), "published_rows": 0, "failure_reason": str(exc), "duration_seconds": (finished-started).total_seconds()}
        try: _record_run(target_path, metrics)
        except Exception: pass
        _write_metrics(base, metrics)
        log.exception("run=%s dataset=%s failed", run_id, dataset)
        raise


def _record_run(db_path: Path, metrics: dict):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS pipeline_runs (run_id TEXT PRIMARY KEY, dataset TEXT, source_file TEXT, started_at TEXT, ended_at TEXT, status TEXT, input_rows INTEGER, valid_rows INTEGER, rejected_rows INTEGER, published_rows INTEGER, duration_seconds REAL, failure_reason TEXT)")
        fields = ["run_id","dataset","source_file","started_at","ended_at","status","input_rows","valid_rows","rejected_rows","published_rows","duration_seconds","failure_reason"]
        conn.execute(f"INSERT OR REPLACE INTO pipeline_runs ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})", [metrics.get(k) for k in fields])


def _write_metrics(base: Path, metrics: dict):
    path = base / "reports" / f"run_{metrics['run_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
