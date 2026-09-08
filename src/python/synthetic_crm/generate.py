from __future__ import annotations

import json
from pathlib import Path

from .config import SimulationConfig
from .customers import generate_customers
from .marketing import generate_leads


OUTPUT_DIR = Path("data/synthetic/crm")
GROUND_TRUTH_DIR = OUTPUT_DIR / "ground_truth"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"


def main() -> None:
    config = SimulationConfig()

    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    customers = generate_customers(config)
    leads = generate_leads(customers, config)

    customers_path = GROUND_TRUTH_DIR / "customers.parquet"
    leads_path = GROUND_TRUTH_DIR / "leads.parquet"
    
    customers.write_parquet(customers_path)
    leads.write_parquet(leads_path)

    manifest = {
        "company_name": config.company_name,
        "seed": config.seed,
        "period": {
            "start_date": config.start_date,
            "end_date": config.end_date,
        },
        "targets": {
            "customers": config.target_customers,
            "leads": config.target_leads,
        },
        "generated": {
            "customers": customers.height,
            "leads": leads.height,
        },
        "files": {
            "customers": str(customers_path),
            "leads": str(leads_path),
        },
    }

    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("Synthetic CRM dataset generated.")
    print()
    print(f"Company: {config.company_name}")
    print(f"Seed: {config.seed}")
    print(f"Period: {config.start_date} → {config.end_date}")
    print()
    print(f"Customers: {customers.height:,}")
    print(f"Leads: {leads.height:,}")


if __name__ == "__main__":
    main()
