from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationConfig:
    seed: int = 20260907
    company_name: str = "BlueOak Home Services"
    start_date: str = "2025-01-01"
    end_date: str = "2026-06-30"

    target_customers: int = 9_000
    target_leads: int = 12_000
    lead_censoring_adjustment: float = 1.45

    duplicate_rate: float = 0.06

    # CRM noise
    missing_source_rate: float = 0.04
    source_alias_rate: float = 0.12
    phone_format_rate: float = 0.70
    missing_phone_rate: float = 0.02
    malformed_phone_rate: float = 0.03
    missing_email_rate: float = 0.025
    malformed_email_rate: float = 0.02
    missing_crm_lead_rate: float = 0.015
    crm_hard_identity_rate: float = 0.04

    # Marketing-system observation noise
    marketing_duplicate_rate: float = 0.03
    marketing_phone_format_rate: float = 0.55
    marketing_name_variant_rate: float = 0.08
    marketing_missing_email_rate: float = 0.015
    marketing_missing_phone_rate: float = 0.025
    marketing_test_record_rate: float = 0.005
    marketing_spam_record_rate: float = 0.01
