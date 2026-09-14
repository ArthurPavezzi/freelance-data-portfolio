from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import polars as pl

ROOT = Path(__file__).resolve().parents[1]

REPORT = ROOT / "reports" / "reconciliation"

VALIDATION = REPORT / "internal_validation"

FIG = ROOT / "figures" / "crm-reconciliation"

FIG.mkdir(parents=True, exist_ok=True, )


def save_figure(fig: plt.Figure, filename: str, ) -> None:
    path = FIG / filename

    fig.tight_layout()

    fig.savefig(path,
        dpi=180,
        bbox_inches="tight",
    )

    plt.close(fig)


def generate_source_reconstruction() -> None:
    """
    Internal validation figure.

    Compares reconstructed lead counts against hidden
    synthetic ground truth.
    """
    source = pl.read_csv(
        VALIDATION
        / "source_validation.csv"
    )

    labels = (
        source[
            "source_canonical"
        ]
        .to_list()
    )

    truth = (
        source[
            "true_leads"
        ]
        .to_list()
    )

    reconstructed = (
        source[
            "reconstructed_leads"
        ]
        .to_list()
    )

    fig, ax = plt.subplots(
        figsize=(9, 5.4)
    )

    x = list(
        range(
            len(labels)
        )
    )

    width = 0.36

    ax.bar(
        [
            i - width / 2
            for i in x
        ],
        truth,
        width,
        label="Hidden truth",
    )

    ax.bar(
        [
            i + width / 2
            for i in x
        ],
        reconstructed,
        width,
        label="Reconstructed",
    )

    ax.set_title(
        "True vs. reconstructed trackable leads"
    )

    ax.set_ylabel(
        "Lead entities"
    )

    ax.set_xticks(x)

    ax.set_xticklabels(
        labels
    )

    ax.legend()

    ax.grid(
        axis="y",
        alpha=0.2,
    )

    save_figure(
        fig,
        "01_source_reconstruction.png",
    )


def generate_paid_cpl_comparison() -> None:
    """
    Internal validation figure.

    Includes hidden synthetic truth and therefore must not
    be used as a client-facing deliverable.
    """
    paid_truth = pl.read_csv(
        VALIDATION
        / "paid_kpi_validation.csv"
    )

    paid_recon = pl.read_csv(
        REPORT
        / "reconstructed_paid_kpis.csv"
    )

    joined = (
        paid_recon
        .join(
            paid_truth.select(
                [
                    "source_canonical",
                    "true_cpl",
                ]
            ),
            on="source_canonical",
            how="inner",
        )
        .sort(
            "source_canonical"
        )
    )

    labels = (
        joined[
            "source_canonical"
        ]
        .to_list()
    )

    series = {
        "Platform reported": (
            joined[
                "platform_reported_cpl"
            ]
            .to_list()
        ),
        "CRM-confirmed": (
            joined[
                "crm_confirmed_cpl"
            ]
            .to_list()
        ),
        "Reconstructed": (
            joined[
                "reconstructed_cpl"
            ]
            .to_list()
        ),
        "Hidden truth": (
            joined[
                "true_cpl"
            ]
            .to_list()
        ),
    }

    fig, ax = plt.subplots(
        figsize=(9, 5.4)
    )

    x = list(
        range(
            len(labels)
        )
    )

    width = 0.18

    offsets = [
        -1.5 * width,
        -0.5 * width,
        0.5 * width,
        1.5 * width,
    ]

    for (
        name,
        values,
    ), offset in zip(
        series.items(),
        offsets,
    ):
        ax.bar(
            [
                i + offset
                for i in x
            ],
            values,
            width,
            label=name,
        )

    ax.set_title(
        "Paid-media CPL: reported, confirmed, reconstructed, and truth"
    )

    ax.set_ylabel(
        "Cost per lead ($)"
    )

    ax.set_xticks(x)

    ax.set_xticklabels(
        labels
    )

    ax.legend()

    ax.grid(
        axis="y",
        alpha=0.2,
    )

    save_figure(
        fig,
        "02_paid_cpl_comparison.png",
    )


def generate_cpl_error_reduction() -> None:
    """
    Internal validation figure.

    Shows absolute CPL error rates before and after
    reconciliation relative to hidden synthetic truth.
    """
    validation = pl.read_csv(
        VALIDATION
        / "paid_kpi_validation.csv"
    ).sort(
        "source_canonical"
    )

    labels = (
        validation[
            "source_canonical"
        ]
        .to_list()
    )

    platform_error = (
        (
            validation[
                "platform_cpl_error_rate"
            ]
            .abs()
            * 100
        )
        .to_list()
    )

    reconstructed_error = (
        (
            validation["reconstructed_cpl_error_rate"].abs() * 100
        ).to_list()
    )

    fig, ax = plt.subplots(
        figsize=(9, 5.4)
    )

    x = list(
        range(
            len(labels)
        )
    )

    width = 0.36

    ax.bar(
        [
            i - width / 2
            for i in x
        ],
        platform_error,
        width,
        label="Platform reported",
    )

    ax.bar(
        [
            i + width / 2
            for i in x
        ],
        reconstructed_error,
        width,
        label="Reconstructed",
    )

    ax.set_title(
        "CPL error relative to hidden truth"
    )

    ax.set_ylabel(
        "Absolute CPL error (%)"
    )

    ax.set_xticks(x)

    ax.set_xticklabels(
        labels
    )

    ax.legend()

    ax.grid(
        axis="y",
        alpha=0.2,
    )

    save_figure(
        fig,
        "03_cpl_error_reduction.png",
    )


def generate_acquisition_composition() -> None:
    """
    Client-safe figure.

    Shows the composition of the reconstructed acquisition
    universe without using hidden synthetic ground truth.
    """
    sources = pl.read_csv(
        REPORT
        / "reconstructed_sources.csv"
    ).sort(
        "reconstructed_leads",
        descending=True,
    )

    labels = (
        sources[
            "source_canonical"
        ]
        .to_list()
    )

    confirmed = (
        sources[
            "cross_system_confirmed"
        ]
        .to_list()
    )

    crm_only = (
        sources[
            "crm_only_entities"
        ]
        .to_list()
    )

    marketing_only = (
        sources[
            "marketing_only_entities"
        ]
        .to_list()
    )

    fig, ax = plt.subplots(
        figsize=(9, 5.4)
    )

    ax.bar(
        labels,
        confirmed,
        label="Cross-system confirmed",
    )

    ax.bar(
        labels,
        crm_only,
        bottom=confirmed,
        label="CRM-only",
    )

    second_bottom = [
        confirmed_value
        + crm_value
        for (
            confirmed_value,
            crm_value,
        ) in zip(
            confirmed,
            crm_only,
        )
    ]

    ax.bar(
        labels,
        marketing_only,
        bottom=second_bottom,
        label="Marketing-only",
    )

    ax.set_title(
        "Reconstructed acquisition universe"
    )

    ax.set_ylabel(
        "Lead entities"
    )

    ax.legend()

    ax.grid(
        axis="y",
        alpha=0.2,
    )

    save_figure(
        fig,
        "04_acquisition_composition.png",
    )


def generate_client_cpl_comparison() -> None:
    """
    Client-safe figure.

    Compares operational CPL definitions without exposing
    hidden synthetic ground truth.
    """
    paid = pl.read_csv(
        REPORT
        / "reconstructed_paid_kpis.csv"
    ).sort(
        "source_canonical"
    )

    labels = (
        paid[
            "source_canonical"
        ]
        .to_list()
    )

    series = {
        "Platform reported": (
            paid[
                "platform_reported_cpl"
            ]
            .to_list()
        ),
        "CRM-confirmed": (
            paid[
                "crm_confirmed_cpl"
            ]
            .to_list()
        ),
        "Reconstructed": (
            paid[
                "reconstructed_cpl"
            ]
            .to_list()
        ),
    }

    fig, ax = plt.subplots(figsize=(9, 5.4))

    x = list(range(len(labels)))

    width = 0.24

    offsets = [-width, 0.0, width, ]

    for (name, values, ), offset in zip(series.items(), offsets, ):
        ax.bar(
            [i + offset for i in x],
            values,
            width,
            label=name,
        )

    ax.set_title("Paid-media CPL after reconciliation")

    ax.set_ylabel("Cost per lead ($)")

    ax.set_xticks(x)

    ax.set_xticklabels(labels)

    ax.legend()

    ax.grid(axis="y", alpha=0.2, )

    save_figure(fig, "05_client_cpl_comparison.png", )


def main() -> None:
    generate_source_reconstruction()

    generate_paid_cpl_comparison()

    generate_cpl_error_reduction()

    generate_acquisition_composition()

    generate_client_cpl_comparison()

    print(
        "Wrote 5 CRM portfolio figures to "
        f"{FIG}"
    )


if __name__ == "__main__":
    main()
