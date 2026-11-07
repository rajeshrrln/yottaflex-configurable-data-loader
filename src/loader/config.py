from pathlib import Path
import yaml


def load_config(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    required = {"dataset", "source", "target", "keys", "schema"}
    missing = required - set(config or {})
    if missing:
        raise ValueError(f"Configuration missing sections: {sorted(missing)}")
    if not config["keys"] or not set(config["keys"]).issubset(config["schema"]):
        raise ValueError("keys must be non-empty and declared in schema")
    if config["target"].get("load_mode") not in {"append", "replace", "upsert"}:
        raise ValueError("load_mode must be append, replace, or upsert")
    return config
