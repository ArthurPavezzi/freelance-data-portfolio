# Freelance Data Portfolio

[![Tests](https://github.com/ArthurPavezzi/freelance-data-portfolio/actions/workflows/tests.yml/badge.svg)](https://github.com/ArthurPavezzi/freelance-data-portfolio/actions/workflows/tests.yml)

**Arthur Pavezzi — Economist, Quantitative Researcher & Data Analyst**

Reproducible, end-to-end projects in **data engineering, analytics, automation, quantitative research, and economic modeling**.

Available for freelance and contract data work.

[GitHub](https://github.com/ArthurPavezzi) · [LinkedIn](https://www.linkedin.com/in/arthur-pavezzi/)

This repository showcases realistic business and research cases, with an emphasis on the full analytical workflow: messy source data, validation, reusable code, automated testing, reporting, and decision-ready outputs.

---

## Featured Projects

### 1. CRM & Marketing Reconciliation

**Business data engineering · Entity resolution · Marketing attribution · Reporting**

A synthetic but realistic home-services CRM case built around a common operational problem: customer and lead data are fragmented across CRM exports, marketing platforms, duplicate records, inconsistent contact information, and incomplete attribution.

The project reconstructs a reliable acquisition universe from corrupted source systems and produces client-facing reporting without relying on hidden synthetic ground truth.

**Highlights**

- synthetic CRM and marketing data generation with controlled data-quality problems;
- normalization of names, phone numbers, emails, and lead attributes;
- exact and fuzzy record matching;
- graph-based entity resolution;
- within-system deduplication;
- marketing-source reconstruction;
- paid-media reconciliation;
- automated validation and triage;
- client-facing and internal-validation outputs.

The final reconstruction recovers approximately **99.6% of trackable leads**, with complete entity validity and source attribution in the synthetic benchmark.

[View the case →](cases/crm-marketing-reconciliation/README.md)

---

### 2. Brazilian Input-Output Analysis

**Economic modeling · Official data ingestion · Matrix methods · Scenario analysis**

A reproducible analysis of the Brazilian economy using the **2015 Input-Output Matrix published by IBGE**.

The project reconstructs Brazil's 67-sector technical coefficient matrix and Leontief inverse from official product-by-industry tables, validates the reconstructed matrices against IBGE's published matrices, identifies structurally important sectors using Rasmussen-Hirschman linkages, and implements reusable final-demand shock scenarios.

**Highlights**

- automated ingestion of official IBGE Excel data;
- semantic parsing of 127 products and 67 activities;
- reconstruction of the technical coefficient matrix;
- reconstruction of the Leontief inverse;
- independent numerical validation against official matrices;
- Rasmussen-Hirschman forward and backward linkages;
- identification of 11 key sectors;
- reusable final-demand shock API;
- export, investment, and key-sector scenarios;
- equal-size scenario comparisons;
- reproducible figures and analytical outputs.

The reconstructed matrices match the official IBGE matrices at approximately **machine precision**.

For equal R$ 100 billion final-demand shocks:

| Scenario composition | Total output | Indirect effect | Output multiplier |
| --- | ---: | ---: | ---: |
| Key sectors | R$ 208.1 bn | R$ 108.1 bn | 2.081 |
| Exports | R$ 194.3 bn | R$ 94.3 bn | 1.943 |
| Investment | R$ 176.6 bn | R$ 76.6 bn | 1.766 |

[View the case →](cases/brazil-input-output-analysis/README.md)

---

## What This Portfolio Focuses On

The projects are designed around two complementary areas.

### Business Data Automation & Analytics

Typical problems include:

- CRM cleanup and reconciliation;
- duplicate detection and entity resolution;
- marketing attribution;
- spreadsheet and reporting automation;
- ETL pipelines;
- KPI reporting;
- operational data quality;
- automated validation;
- dashboard-ready datasets.

### Economic & Research Data

Typical problems include:

- official statistical data pipelines;
- econometric and economic modeling;
- input-output analysis;
- panel and time-series workflows;
- reproducible quantitative research;
- scenario analysis;
- analytical reporting and visualization.

---

## Demonstrated Stack

**Python:** pandas, NumPy, Polars, PyArrow/Parquet, RapidFuzz, Matplotlib, pytest

**Data workflows:** Excel and CSV ingestion, normalization, entity resolution, record linkage, deduplication, reconciliation, validation, ETL-style pipelines, and reproducible analytical outputs

**Economic modeling:** matrix methods, input-output analysis, Leontief models, Rasmussen-Hirschman linkages, and scenario analysis

**Engineering workflow:** Git, GitHub, uv, modular Python packages, automated testing, and structured project layouts

**Reporting:** analytical tables, client-facing summaries, reproducible figures, and export-ready datasets

---

## Repository Structure

```text
.
├── cases/
│   ├── brazil-input-output-analysis/
│   └── crm-marketing-reconciliation/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── synthetic/
│
├── figures/
│   ├── crm-reconciliation/
│   └── input-output/
│
├── notebooks/
│   └── brazil_input_output_analysis.py
│
├── reports/
│   ├── input-output/
│   └── reconciliation/
│
├── scripts/
│
├── src/
│   └── python/
│       ├── crm_reconciliation/
│       ├── input_output/
│       └── synthetic_crm/
│
└── tests/
    └── python/
```

Core analytical logic lives under `src/`, while case documentation, figures, reports, and literate analyses provide the presentation layer.

Generated intermediate data are generally kept separate from the source code.

---

## Reproducibility & Testing

The portfolio is built around reusable modules rather than one-off notebooks.

The current Python test suite contains **132 passing tests** covering synthetic data generation, reconciliation logic, input-output parsing, matrix reconstruction, validation, structural analysis, shock modeling, scenario management, and artifact generation.

Run the complete Python test suite with:

```bash
uv run pytest
```

Some modules are currently imported from the source tree:

```bash
PYTHONPATH=src/python uv run python notebooks/brazil_input_output_analysis.py
```

The input-output analysis also uses `# %%` cells and can be explored interactively in editors such as Spyder or VS Code.

---

## Design Principles

Projects in this repository generally follow the same workflow:

**ingest → clean → validate → model → test → analyze → report**

The goal is to make analytical work:

* reproducible;
* inspectable;
* testable;
* reusable;
* explicit about assumptions;
* useful beyond a single notebook run.

Synthetic data are used where a realistic public business case is useful but real client data cannot be published. Official public datasets are used when the project is research-oriented.

---

## Planned Cases

Additional projects will extend the portfolio into areas such as:

* recurring business reporting automation;
* API-driven analytics pipelines;
* music listening / Last.fm analytics;
* additional economic and research-data workflows.

---

## About

I am an economist and quantitative researcher working across **data analysis, automation, econometrics, economic modeling, and research software**.

I am particularly interested in projects where the difficult part is not simply producing a chart, but turning fragmented or messy data into a reliable analytical workflow.

---

## License

Unless otherwise noted, code in this repository is available under the [MIT License](LICENSE).
