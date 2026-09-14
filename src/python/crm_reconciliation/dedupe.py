from __future__ import annotations

from collections import defaultdict

import polars as pl

from .normalize import (
    prepare_crm,
    prepare_marketing,
)

CRM_ELIGIBLE_STATUSES = [
    "crm_only_trackable",
    "crm_only_unknown_source",
]

MARKETING_ELIGIBLE_STATUSES = [
    "marketing_only_valid",
]


def _generate_duplicate_candidates(
    records: pl.DataFrame,
    *,
    id_col: str,
    time_col: str,
    max_delta_minutes: int,
) -> pl.DataFrame:
    """
    Generate within-system duplicate candidates using observable
    identity fields and a tight temporal window.
    """
    rules = [
        (
            ["email_norm"],
            "email",
        ),
        (
            ["phone_norm"],
            "phone",
        ),
        (
            [
                "name_norm",
                "zip_norm",
            ],
            "name_zip",
        ),
    ]

    candidate_frames: list[pl.DataFrame] = []

    for fields, rule in rules:
        filtered = records

        for field in fields:
            filtered = filtered.filter(pl.col(field).is_not_null())

        left = filtered.select(
            id_col,
            time_col,
            "service",
            *fields,
        ).rename(
            {
                id_col: "left_record_id",
                time_col: "left_timestamp",
            }
        )

        right = filtered.select(
            id_col,
            time_col,
            "service",
            *fields,
        ).rename(
            {
                id_col: "right_record_id",
                time_col: "right_timestamp",
            }
        )

        candidates = (
            left.join(
                right,
                on=[
                    "service",
                    *fields,
                ],
                how="inner",
            )
            .filter(pl.col("left_record_id") < pl.col("right_record_id"))
            .with_columns(
                (pl.col("left_timestamp") - pl.col("right_timestamp"))
                .abs()
                .dt.total_minutes()
                .alias("time_delta_minutes")
            )
            .filter(pl.col("time_delta_minutes") <= max_delta_minutes)
            .select(
                "left_record_id",
                "right_record_id",
                "time_delta_minutes",
            )
            .with_columns(pl.lit(rule).alias("dedupe_rule"))
        )

        candidate_frames.append(candidates)

    if not candidate_frames:
        return pl.DataFrame()

    return (
        pl.concat(
            candidate_frames,
            how="vertical",
        )
        .sort("time_delta_minutes")
        .unique(
            subset=[
                "left_record_id",
                "right_record_id",
            ],
            keep="first",
        )
    )


def _build_components(
    record_ids: list[str],
    candidates: pl.DataFrame,
    *,
    prefix: str,
) -> pl.DataFrame:
    """
    Convert duplicate links into deterministic connected components.
    """
    parent = {record_id: record_id for record_id in record_ids}

    def find(
        node: str,
    ) -> str:
        root = node

        while parent[root] != root:
            root = parent[root]

        while parent[node] != node:
            next_node = parent[node]
            parent[node] = root
            node = next_node

        return root

    def union(
        left: str,
        right: str,
    ) -> None:
        left_root = find(left)
        right_root = find(right)

        if left_root == right_root:
            return

        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    for row in candidates.iter_rows(named=True):
        union(
            str(row["left_record_id"]),
            str(row["right_record_id"]),
        )

    components: dict[
        str,
        list[str],
    ] = defaultdict(list)

    for record_id in record_ids:
        components[find(record_id)].append(record_id)

    ordered = sorted(
        components.values(),
        key=lambda values: min(values),
    )

    rows = []

    for number, members in enumerate(
        ordered,
        start=1,
    ):
        entity_id = f"{prefix}{number:07d}"

        for record_id in sorted(members):
            rows.append(
                {
                    "within_system_entity_id": (entity_id),
                    "record_id": (record_id),
                    "record_count": (len(members)),
                }
            )

    return pl.DataFrame(rows)


def deduplicate_singletons(
    triaged: pl.DataFrame,
    crm: pl.DataFrame,
    marketing: pl.DataFrame,
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
]:
    """
    Deduplicate unresolved observations within each source system.

    Cross-system-confirmed and manual-review records are deliberately
    excluded; this layer only handles unresolved singleton observations.
    """
    crm_prepared = prepare_crm(crm)

    marketing_prepared = prepare_marketing(marketing)

    # --------------------------------------------------------
    # Eligible CRM observations
    # --------------------------------------------------------

    crm_context = triaged.filter(pl.col("triage_status").is_in(CRM_ELIGIBLE_STATUSES)).select(
        pl.col("primary_crm_record_id").alias("crm_record_id"),
        "triage_status",
        "source_canonical",
        "campaign",
        "service",
        "event_timestamp",
    )

    crm_unresolved = crm_prepared.join(
        crm_context.select("crm_record_id"),
        on="crm_record_id",
        how="inner",
    )

    # CRM duplicates are generated at the same CRM timestamp.
    crm_candidates = _generate_duplicate_candidates(
        crm_unresolved,
        id_col="crm_record_id",
        time_col="created_at",
        max_delta_minutes=0,
    )

    crm_membership = _build_components(
        crm_unresolved["crm_record_id"].to_list(),
        crm_candidates,
        prefix="WCR",
    ).with_columns(pl.lit("crm").alias("system"))

    # --------------------------------------------------------
    # Eligible marketing observations
    # --------------------------------------------------------

    marketing_context = triaged.filter(
        pl.col("triage_status").is_in(MARKETING_ELIGIBLE_STATUSES)
    ).select(
        pl.col("primary_marketing_record_id").alias("marketing_record_id"),
        "triage_status",
        "source_canonical",
        "campaign",
        "service",
        "event_timestamp",
    )

    marketing_unresolved = marketing_prepared.join(
        marketing_context.select("marketing_record_id"),
        on="marketing_record_id",
        how="inner",
    )

    # Marketing duplicate submissions occur within a few minutes.
    marketing_candidates = _generate_duplicate_candidates(
        marketing_unresolved,
        id_col="marketing_record_id",
        time_col="captured_at",
        max_delta_minutes=15,
    )

    marketing_membership = _build_components(
        marketing_unresolved["marketing_record_id"].to_list(),
        marketing_candidates,
        prefix="WMK",
    ).with_columns(pl.lit("marketing").alias("system"))

    membership = pl.concat(
        [
            crm_membership,
            marketing_membership,
        ],
        how="vertical",
    )

    # --------------------------------------------------------
    # Human-readable entity summary
    # --------------------------------------------------------

    crm_entity_context = crm_membership.join(
        crm_context.rename({"crm_record_id": ("record_id")}),
        on="record_id",
        how="left",
    )

    marketing_entity_context = marketing_membership.join(
        marketing_context.rename({"marketing_record_id": ("record_id")}),
        on="record_id",
        how="left",
    )

    entity_context = pl.concat(
        [
            crm_entity_context,
            marketing_entity_context,
        ],
        how="vertical",
    )

    entities = (
        entity_context.group_by(
            "within_system_entity_id",
            "system",
        )
        .agg(
            pl.len().alias("record_count"),
            pl.col("event_timestamp").min().alias("event_timestamp"),
            pl.col("triage_status").first().alias("triage_status"),
            pl.col("source_canonical").drop_nulls().first().alias("source_canonical"),
            pl.col("campaign").drop_nulls().first().alias("campaign"),
            pl.col("service").drop_nulls().first().alias("service"),
        )
        .with_columns((pl.col("record_count") > 1).alias("has_duplicates"))
        .sort(
            [
                "system",
                "event_timestamp",
            ]
        )
    )

    return (
        entities,
        membership,
    )
