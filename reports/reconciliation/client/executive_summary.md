# Executive Summary

## Business problem

BlueOak Home Services is a fictional home-services company with lead data spread across a CRM, a marketing lead export, and paid-media reporting. The systems disagree because of duplicate submissions, missing observations, inconsistent source labels, malformed contact fields, CRM omissions, marketing tracking loss, and test/spam records.

A naive dashboard therefore answers a deceptively simple question — “How many leads did we acquire, and at what cost?” — differently depending on which system is used.

## Approach

The project builds a production-like reconciliation workflow without using hidden synthetic ground truth in any operational step:

1. Normalize names, email addresses, phone numbers, ZIP codes, sources, and timestamps.
2. Resolve high-confidence records with deterministic rules.
3. Generate blocked fuzzy candidates for difficult identity cases.
4. Auto-match high-confidence fuzzy pairs and route ambiguous pairs to manual review.
5. Convert accepted links into connected components so duplicate rows do not become duplicate leads.
6. Build a unified ledger, triage unresolved observations, and deduplicate within each source system.
7. Reconstruct an acquisition universe from confirmed cross-system entities plus credible CRM-only and marketing-only entities.
8. Recompute paid-media KPIs from that reconstructed universe.

## Business result

The reconstructed universe contains 8,932 trackable acquisition entities. Paid-media CPL changes materially once platform-reported conversions are reconciled with operational data:

| Channel | Platform CPL | CRM-confirmed CPL | Reconstructed CPL |
|---|---:|---:|---:|
| Facebook Ads | $75.53 | $86.09 | $82.54 |
| Google Ads | $123.39 | $133.09 | $129.07 |

The platform view is optimistic, while requiring a lead to appear in both systems is too conservative. The reconstructed KPI provides a middle ground based on observable evidence.

### Business impact

Across $595,406 in paid-media spend, platform reporting implied a $106.38 cost per lead. After cross-system reconciliation and deduplication, CPL was $113.00 — a **$6.62 per-lead (5.9%) understatement** in the platform view.

The gap was $7.01 per lead on Facebook Ads and $5.69 on Google Ads.

## Internal synthetic benchmark

Ground truth is used only after the pipeline is complete, strictly for validation. Against 8,972 true trackable leads, the workflow reconstructs 8,932 unique valid entities:

- Lead recall: 99.5542%
- Entity validity: 100%
- Source attribution accuracy: 100%
- Unmapped entities: 0
- Impure entities: 0
- Fragmented true leads: 0
- Duplicate-entity excess: 0

For paid channels, reconstructed CPL is within 0.3% of hidden truth, compared with 4–8% error in the platform-reported CPL.

## Decision takeaway

The project demonstrates why reporting problems are often entity-resolution problems before they are dashboard problems. Reconciliation changes the denominator behind acquisition KPIs and prevents duplicate, missing, or noisy records from driving marketing decisions.
