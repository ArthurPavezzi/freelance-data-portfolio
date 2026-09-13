from __future__ import annotations

from collections import defaultdict
from typing import Any

import polars as pl


def build_reconciliation_clusters(
    resolved: pl.DataFrame,
) -> tuple[
    pl.DataFrame,
    pl.DataFrame,
]:
    """
    Convert accepted CRM ↔ marketing links into reconciled lead entities.

    Each connected component in the accepted bipartite graph represents
    one reconciled lead entity.

    Only auto-matched links are used. Manual-review candidates remain
    unresolved until explicitly adjudicated.
    """
    accepted = (
        resolved
        .filter(
            pl.col("review_status")
            == "auto_match"
        )
        .select(
            "crm_record_id",
            "marketing_record_id",
            "match_method",
        )
    )

    parent: dict[str, str] = {}

    def make(node: str) -> None:
        if node not in parent:
            parent[node] = node

    def find(node: str) -> str:
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
        make(left)
        make(right)

        left_root = find(left)
        right_root = find(right)

        if left_root == right_root:
            return

        # Deterministic root selection.
        if left_root < right_root:
            parent[right_root] = left_root
        else:
            parent[left_root] = right_root

    edges: list[
        dict[str, Any]
    ] = []

    for row in accepted.iter_rows(
        named=True
    ):
        crm_node = (
            "crm:"
            + str(
                row["crm_record_id"]
            )
        )

        marketing_node = (
            "marketing:"
            + str(
                row["marketing_record_id"]
            )
        )

        union(
            crm_node,
            marketing_node,
        )

        edges.append(
            {
                "crm_node": crm_node,
                "marketing_node": (
                    marketing_node
                ),
                "match_method": (
                    row["match_method"]
                ),
            }
        )

    component_nodes: dict[
        str,
        set[str],
    ] = defaultdict(set)

    for node in parent:
        component_nodes[
            find(node)
        ].add(node)

    ordered_components = sorted(
        component_nodes.values(),
        key=lambda nodes: min(nodes),
    )

    node_to_cluster: dict[
        str,
        str,
    ] = {}

    for number, nodes in enumerate(
        ordered_components,
        start=1,
    ):
        reconciled_lead_id = (
            f"RCL{number:07d}"
        )

        for node in nodes:
            node_to_cluster[
                node
            ] = reconciled_lead_id

    edge_summary: dict[
        str,
        dict[str, int],
    ] = defaultdict(
        lambda: {
            "match_edge_count": 0,
            "exact_edge_count": 0,
            "fuzzy_edge_count": 0,
        }
    )

    for edge in edges:
        reconciled_lead_id = (
            node_to_cluster[
                edge["crm_node"]
            ]
        )

        edge_summary[
            reconciled_lead_id
        ][
            "match_edge_count"
        ] += 1

        if (
            edge["match_method"]
            == "exact"
        ):
            edge_summary[
                reconciled_lead_id
            ][
                "exact_edge_count"
            ] += 1

        elif (
            edge["match_method"]
            == "fuzzy"
        ):
            edge_summary[
                reconciled_lead_id
            ][
                "fuzzy_edge_count"
            ] += 1

    cluster_rows: list[
        dict[str, Any]
    ] = []

    membership_rows: list[
        dict[str, Any]
    ] = []

    for nodes in ordered_components:
        reconciled_lead_id = (
            node_to_cluster[
                next(iter(nodes))
            ]
        )

        crm_records = sorted(
            node.removeprefix(
                "crm:"
            )
            for node in nodes
            if node.startswith(
                "crm:"
            )
        )

        marketing_records = sorted(
            node.removeprefix(
                "marketing:"
            )
            for node in nodes
            if node.startswith(
                "marketing:"
            )
        )

        crm_count = len(
            crm_records
        )

        marketing_count = len(
            marketing_records
        )

        summary = edge_summary[
            reconciled_lead_id
        ]

        cluster_rows.append(
            {
                "reconciled_lead_id": (
                    reconciled_lead_id
                ),
                "crm_record_count": (
                    crm_count
                ),
                "marketing_record_count": (
                    marketing_count
                ),
                "match_edge_count": (
                    summary[
                        "match_edge_count"
                    ]
                ),
                "exact_edge_count": (
                    summary[
                        "exact_edge_count"
                    ]
                ),
                "fuzzy_edge_count": (
                    summary[
                        "fuzzy_edge_count"
                    ]
                ),
                "has_crm_duplicates": (
                    crm_count > 1
                ),
                "has_marketing_duplicates": (
                    marketing_count > 1
                ),
                "is_many_to_many": (
                    crm_count > 1
                    and marketing_count > 1
                ),
            }
        )

        for crm_record_id in (
            crm_records
        ):
            membership_rows.append(
                {
                    "reconciled_lead_id": (
                        reconciled_lead_id
                    ),
                    "system": "crm",
                    "record_id": (
                        crm_record_id
                    ),
                }
            )

        for marketing_record_id in (
            marketing_records
        ):
            membership_rows.append(
                {
                    "reconciled_lead_id": (
                        reconciled_lead_id
                    ),
                    "system": (
                        "marketing"
                    ),
                    "record_id": (
                        marketing_record_id
                    ),
                }
            )

    clusters = pl.DataFrame(
        cluster_rows
    )

    membership = pl.DataFrame(
        membership_rows
    )

    return (
        clusters,
        membership,
    )
