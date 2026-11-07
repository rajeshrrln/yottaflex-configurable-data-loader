import pandas as pd


def validate_frame(frame: pd.DataFrame, config: dict, known_reference_values: dict | None = None):
    """Vectorized schema and rule validation with row-level reject explanations."""
    schema = config["schema"]
    required_cols = set(schema)
    missing_cols = required_cols - set(frame.columns)
    unexpected_cols = set(frame.columns) - required_cols
    if missing_cols:
        raise ValueError(f"Unexpected schema change; missing columns: {sorted(missing_cols)}")

    source = frame[list(schema)].copy().reset_index(drop=True)
    n = len(source)
    reasons = [[] for _ in range(n)]
    converted = pd.DataFrame(index=source.index)

    def add(mask, message):
        if not hasattr(mask, "__len__"):
            mask = [mask] * n
        for i in range(n):
            if bool(mask.iloc[i] if hasattr(mask, "iloc") else mask[i]):
                reasons[i].append(message)

    for column, spec in schema.items():
        series = source[column]
        nulls = series.isna()
        kind = spec["type"]
        if not spec.get("nullable", True):
            add(nulls, f"{column}:null_not_allowed")
        if kind == "string":
            converted[column] = series.astype("string").str.strip()
        elif kind in {"integer", "decimal"}:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = series.notna() & numeric.isna()
            add(invalid, f"{column}:could_not_convert_to_{kind}")
            if kind == "integer":
                fractional = numeric.notna() & ((numeric % 1) != 0)
                add(fractional, f"{column}:not_an_integer")
                converted[column] = numeric.where(~fractional).astype("Int64")
            else:
                converted[column] = numeric
        elif kind == "date":
            parsed = pd.to_datetime(series, errors="coerce")
            invalid = series.notna() & parsed.isna()
            add(invalid, f"{column}:could_not_convert_to_date")
            converted[column] = parsed.dt.strftime("%Y-%m-%d")
        elif kind == "timestamp":
            parsed = pd.to_datetime(series, utc=True, errors="coerce")
            invalid = series.notna() & parsed.isna()
            add(invalid, f"{column}:could_not_convert_to_timestamp")
            converted[column] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        elif kind == "boolean":
            normalized = series.astype("string").str.strip().str.lower()
            mapping = {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}
            result = normalized.map(mapping)
            invalid = series.notna() & result.isna()
            add(invalid, f"{column}:not_a_boolean")
            converted[column] = result
        else:
            raise ValueError(f"unsupported_type:{kind}")

    for key in config["keys"]:
        missing_key = converted[key].isna() | converted[key].astype("string").eq("")
        add(missing_key, f"{key}:missing_key")

    for rule in config.get("business_rules", []):
        col, kind = rule["column"], rule["rule"]
        values = converted[col]
        present = values.notna()
        if kind == "email":
            failed = present & ~values.astype("string").str.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", na=False)
        elif kind == "regex":
            failed = present & ~values.astype("string").str.fullmatch(rule["pattern"], na=False)
        elif kind == "greater_than":
            failed = present & ~(pd.to_numeric(values, errors="coerce") > float(rule["value"]))
        elif kind == "in":
            failed = present & ~values.isin(rule["values"])
        elif kind == "not_future_date":
            today = pd.Timestamp.now(tz="UTC").date().isoformat()
            failed = present & (values.astype("string") > today)
        else:
            raise ValueError(f"Unknown business rule: {kind}")
        add(failed, f"{rule['name']}:business_rule_failed")

    for ref in config.get("references", []):
        known = (known_reference_values or {}).get(ref["dataset"])
        if known is not None:
            values = converted[ref["column"]]
            failed = values.notna() & ~values.isin(known)
            add(failed, f"{ref['column']}:invalid_reference_key")

    rejected_idx = [i for i, why in enumerate(reasons) if why]
    accepted_idx = [i for i, why in enumerate(reasons) if not why]
    valid = converted.iloc[accepted_idx].copy()
    rejected_records = []
    for i in rejected_idx:
        rejected_records.append({**source.iloc[i].to_dict(), "_source_row": i + 1, "_reject_reason": ";".join(sorted(set(reasons[i])))})

    # Deterministic duplicate handling: keep the last occurrence in the input batch.
    duplicate_mask = valid.duplicated(subset=config["keys"], keep="last")
    for original_idx, duplicate in zip(valid.index[duplicate_mask], valid.loc[duplicate_mask].to_dict(orient="records")):
        rejected_records.append({**source.iloc[original_idx].to_dict(), "_source_row": int(original_idx) + 1, "_reject_reason": "duplicate_key_in_batch"})
    valid = valid.loc[~duplicate_mask].reset_index(drop=True)
    valid = valid.astype(object).where(pd.notna(valid), None)
    return valid, pd.DataFrame(rejected_records), {"unexpected_columns": sorted(unexpected_cols)}
