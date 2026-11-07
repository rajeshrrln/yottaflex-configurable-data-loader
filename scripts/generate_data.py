import argparse, json, random
from datetime import date, timedelta, datetime, timezone
from pathlib import Path


def generate(out: Path, customers: int = 20, orders: int = 100, seed: int = 42, include_edge_cases: bool = True):
    random.seed(seed); out.mkdir(parents=True, exist_ok=True)
    countries = ["IN", "US", "GB", "DE", "AU"]
    cust = []
    for i in range(1, customers + 1):
        cust.append({"customer_id": f"C{i:06d}", "customer_name": f"Customer {i}", "email": f"customer{i}@example.com", "signup_date": (date(2022,1,1)+timedelta(days=random.randint(0,1500))).isoformat(), "country_code": random.choice(countries), "updated_at": datetime(2026,1,1,tzinfo=timezone.utc).isoformat()})
    with (out / "customers.csv").open("w", encoding="utf-8") as f:
        f.write("customer_id,customer_name,email,signup_date,country_code,updated_at\n")
        for r in cust:
            f.write(",".join(str(r[k]) for k in ["customer_id","customer_name","email","signup_date","country_code","updated_at"]) + "\n")
    rows=[]
    for i in range(1, orders + 1):
        rows.append({"order_id": f"O{i:07d}", "customer_id": random.choice(cust)["customer_id"], "order_date": (date(2025,1,1)+timedelta(days=random.randint(0,600))).isoformat(), "amount": round(random.uniform(10,5000),2), "currency": random.choice(["INR","USD","EUR"]), "status": random.choice(["PLACED","PAID","SHIPPED","CANCELLED","REFUNDED"]), "updated_at": datetime(2026,1,1,tzinfo=timezone.utc).isoformat()})
    if include_edge_cases and orders >= 6:
        rows[0] = {**rows[0], "amount": -10}                 # invalid amount
        rows[1] = {**rows[1], "customer_id": "C999999"}    # invalid FK
        rows[2] = {**rows[2], "currency": "XYZ"}          # invalid enum
        rows[3] = dict(rows[3])                              # duplicate event
        rows[4] = {**rows[4], "order_id": rows[3]["order_id"]}
        rows[5] = {**rows[5], "amount": None}               # required null
    with (out / "orders.jsonl").open("w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r) + "\n")
        if include_edge_cases: f.write('{malformed json line\n')
    return len(cust), len(rows)

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--customers",type=int,default=20); p.add_argument("--orders",type=int,default=100); p.add_argument("--seed",type=int,default=42); p.add_argument("--out",default="data/input"); p.add_argument("--clean",action="store_true"); a=p.parse_args()
    print(generate(Path(a.out),a.customers,a.orders,a.seed,not a.clean))
