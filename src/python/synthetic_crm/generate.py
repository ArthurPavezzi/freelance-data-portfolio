from __future__ import annotations

import json
from pathlib import Path

from .config import SimulationConfig
from .customers import generate_customers
from .marketing import generate_leads
from .funnel import generate_funnel
from .corruptions import corrupt_crm_leads


OUTPUT_DIR = Path("data/synthetic/crm")
GROUND_TRUTH_DIR = OUTPUT_DIR / "ground_truth"
RAW_EXPORTS_DIR = OUTPUT_DIR / "raw_exports"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"


def main() -> None:
    config = SimulationConfig()

    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    RAW_EXPORTS_DIR.mkdir(parents=True,exist_ok=True)

    customers = generate_customers(config)
    
    base_leads = generate_leads(
        customers,
        config,
    )
    
    salespeople, leads, estimates, jobs = generate_funnel(
        base_leads,
        customers,
        config,
    )

    (
        crm_leads,
        crm_corruption_log,
        crm_observation_map,
    ) = corrupt_crm_leads(
        leads,
        customers,
        config,
    )

    customers_path = GROUND_TRUTH_DIR / "customers.parquet"
    salespeople_path = GROUND_TRUTH_DIR / "salespeople.parquet"
    leads_path = GROUND_TRUTH_DIR / "leads.parquet"
    estimates_path = GROUND_TRUTH_DIR / "estimates.parquet"
    jobs_path = GROUND_TRUTH_DIR / "jobs.parquet"
    crm_leads_path = RAW_EXPORTS_DIR / "crm_leads.csv"
    corruption_log_path = GROUND_TRUTH_DIR / "crm_corruption_log.parquet"
    observation_map_path = GROUND_TRUTH_DIR / "crm_observation_map.parquet"
    
    customers.write_parquet(customers_path)
    salespeople.write_parquet(salespeople_path)
    leads.write_parquet(leads_path)
    estimates.write_parquet(estimates_path)
    jobs.write_parquet(jobs_path)
    crm_leads.write_csv(crm_leads_path)
    crm_corruption_log.write_parquet(corruption_log_path)
    crm_observation_map.write_parquet(observation_map_path)

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
            "salespeople": salespeople.height,
            "leads": leads.height,
            "estimates": estimates.height,
            "jobs": jobs.height,
            "crm_export": {
                        "records": crm_leads.height,
                        "corruptions": (
                            crm_corruption_log.height
                        ),
                    },
        },
        "files": {
            "customers": str(customers_path),
            "salespeople": str(salespeople_path),
            "leads": str(leads_path),
            "estimates": str(estimates_path),
            "jobs": str(jobs_path),
            "crm_leads": str(
                crm_leads_path
            ),
            "crm_corruption_log": str(
                corruption_log_path
            ),
            "crm_observation_map": str(
                observation_map_path
            ),
        },
        "corruption_rates": {
            "phone_format": (
                config.phone_format_rate
            ),
            "malformed_phone": (
                config.malformed_phone_rate
            ),
            "malformed_email": (
                config.malformed_email_rate
            ),
            "missing_source": (
                config.missing_source_rate
            ),
            "duplicate_record": (
                config.duplicate_rate
            ),
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
