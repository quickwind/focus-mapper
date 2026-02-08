import csv
from datetime import date, timedelta
import random

def generate_data():
    start_date = date(2025, 12, 31)
    end_date = date(2026, 1, 2) # Exclusive, so includes 2025-12-31 and 2026-01-01
    
    current = start_date
    delta = timedelta(days=1)
    
    resources = ["res-123", "res-456"]
    
    rows = []
    
    # Outer loop for resources, inner loop days to match DuckDB partition/sort order better?
    # Actually, as long as we sort by (resource, date) later or in the test, it's fine.
    # But let's stick to (resource then time) order for clarity in file.
    
    for resource_id in resources:
        current = start_date
        while current < end_date:
            billing_period = current.strftime("%Y-%m")
            billing_date = current.strftime("%Y-%m-%d")
            
            for hour in range(24):
                # Randomly inject Tax records (~5% chance)
                if random.random() < 0.05:
                    category = "Tax"
                    desc = "Sales Tax"
                    cost = round(random.uniform(0.1, 1.0), 2)
                    tax = 0.0
                    tag_a = "billing"
                    tag_b = "tax"
                else:
                    category = "Usage"
                    desc = "Compute usage"
                    cost = round(random.uniform(0.5, 2.5), 2)
                    tax = round(cost * 0.1, 2)
                    tag_a = "core"
                    tag_b = "vm"

                row = {
                    "billing_period": billing_period,
                    "billing_date": billing_date,
                    "billing_hour": str(hour), 
                    "billing_currency": "USD",
                    "billed_cost": cost,
                    "tax_amount": tax,
                    "charge_category": category,
                    "charge_class": "Normal",
                    "charge_description": desc,
                    "alt_description": "",
                    "tag_a": tag_a,
                    "tag_b": tag_b,
                    "pricing_quantity": 1.0,
                    "pricing_unit": "Hours",
                    "billing_resource_id": resource_id
                }
                rows.append(row)
            current += delta

    header = [
        "billing_period", "billing_date", "billing_hour", "billing_currency",
        "billed_cost", "tax_amount", "charge_category", "charge_class",
        "charge_description", "alt_description", "tag_a", "tag_b",
        "pricing_quantity", "pricing_unit", "billing_resource_id"
    ]
    
    # Resolve path relative to this script (assumed in tools/)
    from pathlib import Path
    script_dir = Path(__file__).parent
    # Go up one level to project root, then into tests/fixtures
    output_path = script_dir.parent / "tests" / "fixtures" / "telemetry_small.csv"
    
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Generated {len(rows)} rows to {output_path}")

if __name__ == "__main__":
    generate_data()
