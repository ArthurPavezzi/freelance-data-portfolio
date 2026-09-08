from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 20260907

    start_date: str = "2025-01-01"
    end_date: str = "2026-06-30"

    target_customers: int = 9_000
    target_leads: int = 12_000
    
    lead_censoring_adjustment: float = 1.45

    phone_format_rate: float = 0.70

    duplicate_rate: float = 0.06
    missing_source_rate: float = 0.04
    malformed_phone_rate: float = 0.03
    malformed_email_rate: float = 0.02
    missing_crm_lead_rate: float = 0.015

    company_name: str = "BlueOak Home Services"
