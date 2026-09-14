import polars as pl
from crm_reconciliation.cluster import (
    build_reconciliation_clusters,
)


def _resolved_matches() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "crm_record_id": [
                "CRM1",
                "CRM2",
                "CRM3",
                "CRM3",
                "CRM4",
            ],
            "marketing_record_id": [
                "MKT1",
                "MKT1",
                "MKT2",
                "MKT3",
                "MKT4",
            ],
            "match_method": [
                "exact",
                "exact",
                "exact",
                "fuzzy",
                "fuzzy",
            ],
            "review_status": [
                "auto_match",
                "auto_match",
                "auto_match",
                "auto_match",
                "manual_review",
            ],
        }
    )


def test_connected_records_form_single_cluster() -> None:
    clusters, membership = (
        build_reconciliation_clusters(
            _resolved_matches()
        )
    )

    assert clusters.height == 2

    crm_duplicate_cluster = (
        clusters
        .filter(
            pl.col(
                "crm_record_count"
            )
            == 2
        )
    )

    assert (
        crm_duplicate_cluster.height
        == 1
    )

    assert (
        crm_duplicate_cluster[
            "marketing_record_count"
        ][0]
        == 1
    )


def test_marketing_duplicates_form_single_cluster() -> None:
    clusters, _ = (
        build_reconciliation_clusters(
            _resolved_matches()
        )
    )

    marketing_duplicate_cluster = (
        clusters
        .filter(
            pl.col(
                "marketing_record_count"
            )
            == 2
        )
    )

    assert (
        marketing_duplicate_cluster.height
        == 1
    )

    assert (
        marketing_duplicate_cluster[
            "crm_record_count"
        ][0]
        == 1
    )


def test_manual_review_links_are_excluded() -> None:
    _, membership = (
        build_reconciliation_clusters(
            _resolved_matches()
        )
    )

    assert (
        "CRM4"
        not in membership[
            "record_id"
        ].to_list()
    )

    assert (
        "MKT4"
        not in membership[
            "record_id"
        ].to_list()
    )


def test_membership_contains_each_accepted_record_once() -> None:
    _, membership = (
        build_reconciliation_clusters(
            _resolved_matches()
        )
    )

    assert membership.height == 6

    assert (
        membership[
            "record_id"
        ].n_unique()
        == membership.height
    )


def test_cluster_ids_are_reproducible() -> None:
    first = (
        build_reconciliation_clusters(
            _resolved_matches()
        )
    )

    second = (
        build_reconciliation_clusters(
            _resolved_matches()
        )
    )

    assert first[0].equals(
        second[0]
    )

    assert first[1].equals(
        second[1]
    )


def test_cluster_membership_has_unique_records_per_system() -> None:
    _, membership = (
        build_reconciliation_clusters(
            _resolved_matches()
        )
    )

    duplicates = (
        membership
        .group_by(
            "system",
            "record_id",
        )
        .len()
        .filter(
            pl.col("len") > 1
        )
    )

    assert duplicates.height == 0


def test_cluster_edge_counts_are_consistent() -> None:
    clusters, _ = (
        build_reconciliation_clusters(
            _resolved_matches()
        )
    )

    assert (
        clusters[
            "match_edge_count"
        ].sum()
        == 4
    )
