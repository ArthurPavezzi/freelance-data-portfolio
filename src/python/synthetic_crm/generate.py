from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from .config import SimulationConfig
from .corruptions import corrupt_crm_leads
from .customers import generate_customers
from .funnel import generate_funnel
from .marketing import generate_leads
from .marketing_export import TRACKABLE_SOURCES, generate_marketing_export
from .marketing_spend import generate_marketing_spend

OUTPUT_DIR = Path("data/synthetic/crm")
GROUND_TRUTH_DIR = OUTPUT_DIR / "ground_truth"
RAW_EXPORTS_DIR = OUTPUT_DIR / "raw_exports"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"


def main() -> None:
    config = SimulationConfig()

    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    RAW_EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

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

    (
        marketing_leads,
        marketing_corruption_log,
        marketing_observation_map,
    ) = generate_marketing_export(
        leads,
        customers,
        config,
    )

    (
        marketing_spend,
        marketing_spend_truth,
    ) = generate_marketing_spend(
        leads,
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
    marketing_leads_path = RAW_EXPORTS_DIR / "marketing_leads.csv"
    marketing_corruption_log_path = GROUND_TRUTH_DIR / "marketing_corruption_log.parquet"
    marketing_observation_map_path = GROUND_TRUTH_DIR / "marketing_observation_map.parquet"
    marketing_spend_path = RAW_EXPORTS_DIR / "marketing_spend.csv"
    marketing_spend_truth_path = GROUND_TRUTH_DIR / "marketing_spend_truth.parquet"

    customers.write_parquet(customers_path)
    salespeople.write_parquet(salespeople_path)
    leads.write_parquet(leads_path)
    estimates.write_parquet(estimates_path)
    jobs.write_parquet(jobs_path)
    crm_leads.write_csv(crm_leads_path)
    crm_corruption_log.write_parquet(corruption_log_path)
    crm_observation_map.write_parquet(observation_map_path)
    marketing_leads.write_csv(marketing_leads_path)
    marketing_corruption_log.write_parquet(marketing_corruption_log_path)
    marketing_observation_map.write_parquet(marketing_observation_map_path)
    marketing_spend.write_csv(marketing_spend_path)
    marketing_spend_truth.write_parquet(marketing_spend_truth_path)

    omitted_crm_leads = crm_corruption_log.filter(
        pl.col("corruption_type") == "missing_crm_lead"
    ).height

    trackable_true_leads = leads.filter(pl.col("source").is_in(list(TRACKABLE_SOURCES))).height

    marketing_observed_true_leads = (
        marketing_observation_map["ground_truth_lead_id"].drop_nulls().n_unique()
    )

    marketing_noise_records = marketing_observation_map.filter(
        pl.col("ground_truth_lead_id").is_null()
    ).height

    marketing_duplicate_records = marketing_observation_map["is_duplicate"].sum()

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
                "observed_true_leads": (crm_observation_map["ground_truth_lead_id"].n_unique()),
                "omitted_true_leads": (omitted_crm_leads),
                "corruptions": (crm_corruption_log.height),
            },
            "marketing_export": {
                "records": (marketing_leads.height),
                "trackable_true_leads": (trackable_true_leads),
                "observed_true_leads": (marketing_observed_true_leads),
                "duplicate_records": (marketing_duplicate_records),
                "noise_records": (marketing_noise_records),
                "corruptions": (marketing_corruption_log.height),
            },
            "marketing_performance": {
                "rows": (marketing_spend.height),
                "total_spend": round(
                    float(marketing_spend["spend"].sum()),
                    2,
                ),
                "platform_conversions": int(marketing_spend["platform_conversions"].sum()),
                "ground_truth_paid_leads": int(marketing_spend_truth["ground_truth_leads"].sum()),
            },
        },
        "files": {
            "customers": str(customers_path),
            "salespeople": str(salespeople_path),
            "leads": str(leads_path),
            "estimates": str(estimates_path),
            "jobs": str(jobs_path),
            "crm_leads": str(crm_leads_path),
            "crm_corruption_log": str(corruption_log_path),
            "crm_observation_map": str(observation_map_path),
            "marketing_leads": str(marketing_leads_path),
            "marketing_corruption_log": str(marketing_corruption_log_path),
            "marketing_observation_map": str(marketing_observation_map_path),
            "marketing_spend": str(marketing_spend_path),
            "marketing_spend_truth": str(marketing_spend_truth_path),
        },
        "corruption_rates": {
            "phone_format": (config.phone_format_rate),
            "source_alias": (config.source_alias_rate),
            "missing_phone": (config.missing_phone_rate),
            "malformed_phone": (config.malformed_phone_rate),
            "missing_email": (config.missing_email_rate),
            "malformed_email": (config.malformed_email_rate),
            "missing_source": (config.missing_source_rate),
            "missing_crm_lead": (config.missing_crm_lead_rate),
            "duplicate_record": (config.duplicate_rate),
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
