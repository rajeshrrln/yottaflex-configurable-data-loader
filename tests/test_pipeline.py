import json, sqlite3
import pandas as pd
import pytest
from loader.config import load_config
from loader.validate import validate_frame
from loader.pipeline import run_pipeline


def test_config_loads(project_root):
    cfg=load_config(project_root/"config/customers.yaml")
    assert cfg["keys"] == ["customer_id"]


def test_customer_valid_and_invalid_rows(project_root):
    cfg=load_config(project_root/"config/customers.yaml")
    good={"customer_id":"C1","customer_name":"A","email":"a@example.com","signup_date":"2024-01-01","country_code":"IN","updated_at":"2026-01-01T00:00:00Z"}
    bad={**good,"customer_id":"C2","email":"bad"}
    valid,rejects,_=validate_frame(pd.DataFrame([good,bad]),cfg)
    assert len(valid)==1 and len(rejects)==1
    assert "valid_email" in rejects.iloc[0]["_reject_reason"]


def test_duplicate_key_keeps_last(project_root):
    cfg=load_config(project_root/"config/customers.yaml")
    row={"customer_id":"C1","customer_name":"A","email":"a@example.com","signup_date":"2024-01-01","country_code":"IN","updated_at":"2026-01-01T00:00:00Z"}
    valid,rejects,_=validate_frame(pd.DataFrame([row,{**row,"customer_name":"B"}]),cfg)
    assert len(valid)==1 and valid.iloc[0].customer_name=="B"
    assert "duplicate_key" in rejects.iloc[0]["_reject_reason"]


def test_missing_required_field_rejects(project_root):
    cfg=load_config(project_root/"config/customers.yaml")
    row={"customer_id":"C1","customer_name":None,"email":"a@example.com","signup_date":"2024-01-01","country_code":"IN","updated_at":"2026-01-01T00:00:00Z"}
    valid,rejects,_=validate_frame(pd.DataFrame([row]),cfg)
    assert valid.empty and "null_not_allowed" in rejects.iloc[0]["_reject_reason"]


def test_unexpected_schema_change_fails(project_root):
    cfg=load_config(project_root/"config/customers.yaml")
    with pytest.raises(ValueError,match="missing columns"):
        validate_frame(pd.DataFrame([{"customer_id":"C1"}]),cfg)


def test_empty_batch_is_safe(project_root,tmp_path):
    (tmp_path/"data/input").mkdir(parents=True)
    (tmp_path/"data/output").mkdir(parents=True)
    (tmp_path/"config").mkdir()
    cfg=(project_root/"config/customers.yaml").read_text()
    (tmp_path/"config/customers.yaml").write_text(cfg)
    (tmp_path/"data/input/customers.csv").write_text("customer_id,customer_name,email,signup_date,country_code,updated_at\n")
    result=run_pipeline("config/customers.yaml", "empty-run", tmp_path)
    assert result["input_rows"]==0 and result["valid_rows"]==0


def test_domain_edge_cases_in_orders(project_root):
    cfg=load_config(project_root/"config/orders.yaml")
    row={"order_id":"O1","customer_id":"C1","order_date":"2025-01-01","amount":10,"currency":"INR","status":"PAID","updated_at":"2026-01-01T00:00:00Z"}
    for change, expected in [({"amount":-1},"positive_amount"),({"currency":"XYZ"},"supported_currency")]:
        valid,rejects,_=validate_frame(pd.DataFrame([{**row,**change}]),cfg,{"customers":{"C1"}})
        assert valid.empty and expected in rejects.iloc[0]["_reject_reason"]


def test_rerun_is_idempotent(project_root,tmp_path):
    import shutil
    shutil.copytree(project_root/"config",tmp_path/"config")
    shutil.copytree(project_root/"data/input",tmp_path/"data/input")
    (tmp_path/"data/output").mkdir(parents=True)
    (tmp_path/"data/quarantine").mkdir(parents=True)
    (tmp_path/"reports").mkdir()
    run_pipeline("config/customers.yaml","customers-1",tmp_path)
    run_pipeline("config/customers.yaml","customers-2",tmp_path)
    with sqlite3.connect(tmp_path/"data/output/warehouse.db") as conn:
        count=conn.execute("select count(*) from customers").fetchone()[0]
    assert count==20


def test_invalid_reference_is_quarantined(project_root):
    cfg=load_config(project_root/"config/orders.yaml")
    row={"order_id":"O2","customer_id":"NO_SUCH_CUSTOMER","order_date":"2025-01-01","amount":10,"currency":"INR","status":"PAID","updated_at":"2026-01-01T00:00:00Z"}
    valid,rejects,_=validate_frame(pd.DataFrame([row]),cfg,{"customers":{"C1"}})
    assert valid.empty and "invalid_reference_key" in rejects.iloc[0]["_reject_reason"]


def test_malformed_jsonl_is_reported(project_root,tmp_path):
    import shutil
    shutil.copytree(project_root/"config",tmp_path/"config")
    (tmp_path/"data/input").mkdir(parents=True)
    (tmp_path/"data/output").mkdir(parents=True)
    (tmp_path/"data/input/customers.csv").write_text("customer_id,customer_name,email,signup_date,country_code,updated_at\n")
    (tmp_path/"data/input/orders.jsonl").write_text('{broken json\n')
    # A malformed-only batch still produces a run report and a quarantine artifact.
    result=run_pipeline("config/orders.yaml","malformed-only",tmp_path)
    assert result["input_rows"]==1 and result["rejected_rows"]==1


def test_failed_run_records_failure_reason(project_root,tmp_path):
    import shutil
    shutil.copytree(project_root/"config",tmp_path/"config")
    (tmp_path/"data/input").mkdir(parents=True)
    (tmp_path/"data/output").mkdir(parents=True)
    (tmp_path/"data/input/customers.csv").write_text("wrong_column\nvalue\n")
    with pytest.raises(ValueError):
        run_pipeline("config/customers.yaml","failure-run",tmp_path)
    with sqlite3.connect(tmp_path/"data/output/warehouse.db") as conn:
        status=conn.execute("select status from pipeline_runs where run_id='failure-run'").fetchone()[0]
    assert status=="failed"


def test_unexpected_columns_are_reported(project_root):
    cfg = load_config(project_root / "config/customers.yaml")

    row = {
        "customer_id": "C100",
        "customer_name": "Test Customer",
        "email": "test@example.com",
        "signup_date": "2024-01-01",
        "country_code": "IN",
        "updated_at": "2026-01-01T00:00:00Z",
        "unexpected_field": "extra_value",
    }

    valid, rejects, schema_info = validate_frame(
        pd.DataFrame([row]), cfg
    )

    assert len(valid) == 1
    assert rejects.empty
    assert schema_info["unexpected_columns"] == ["unexpected_field"]
    assert "unexpected_field" not in valid.columns


def test_multiple_unexpected_columns_are_reported(project_root):
    cfg = load_config(project_root / "config/customers.yaml")

    row = {
        "customer_id": "C101",
        "customer_name": "Another Customer",
        "email": "another@example.com",
        "signup_date": "2024-01-01",
        "country_code": "IN",
        "updated_at": "2026-01-01T00:00:00Z",
        "extra_b": "B",
        "extra_a": "A",
    }

    valid, rejects, schema_info = validate_frame(
        pd.DataFrame([row]), cfg
    )

    assert len(valid) == 1
    assert rejects.empty
    assert schema_info["unexpected_columns"] == ["extra_a", "extra_b"]
