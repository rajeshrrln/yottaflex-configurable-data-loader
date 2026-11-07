from pathlib import Path
import json
import pandas as pd


def read_source(path: str | Path, file_format: str, options: dict | None = None) -> pd.DataFrame:
    path = Path(path)
    options = options or {}
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")
    if file_format == "csv":
        return pd.read_csv(path, **options)
    if file_format == "jsonl":
        rows, malformed = [], []
        with path.open(encoding=options.get("encoding", "utf-8")) as stream:
            for line_no, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if not isinstance(obj, dict):
                        raise ValueError("JSON record must be an object")
                    rows.append(obj)
                except (json.JSONDecodeError, ValueError) as exc:
                    malformed.append({"_source_line": line_no, "_raw_record": line.rstrip("\n"), "_reject_reason": f"malformed_json: {exc}"})
        frame = pd.DataFrame(rows)
        frame.attrs["malformed_records"] = malformed
        return frame
    if file_format == "parquet":
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported source format: {file_format}")
