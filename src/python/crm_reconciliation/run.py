from __future__ import annotations

from collections.abc import Callable

from .run_acquisition import (
    main as run_acquisition,
)
from .run_clusters import (
    main as run_clusters,
)
from .run_dedupe import (
    main as run_dedupe,
)
from .run_exact import (
    main as run_exact,
)
from .run_fuzzy import (
    main as run_fuzzy,
)
from .run_ledger import (
    main as run_ledger,
)
from .run_report import (
    main as run_report,
)
from .run_resolution import (
    main as run_resolution,
)
from .run_triage import (
    main as run_triage,
)

PipelineStage = tuple[
    str,
    Callable[[], None],
]


PIPELINE_STAGES: tuple[
    PipelineStage,
    ...,
] = (
    (
        "Exact matching",
        run_exact,
    ),
    (
        "Fuzzy candidate recovery",
        run_fuzzy,
    ),
    (
        "Match resolution",
        run_resolution,
    ),
    (
        "Entity clustering",
        run_clusters,
    ),
    (
        "Unified lead ledger",
        run_ledger,
    ),
    (
        "Observable triage",
        run_triage,
    ),
    (
        "Within-system deduplication",
        run_dedupe,
    ),
    (
        "Acquisition reconstruction",
        run_acquisition,
    ),
    (
        "Operational reporting",
        run_report,
    ),
)


def main() -> None:
    total = len(PIPELINE_STAGES)

    print()
    print("CRM Reconciliation Pipeline")
    print("=" * 27)
    print()

    for position, (
        name,
        stage,
    ) in enumerate(
        PIPELINE_STAGES,
        start=1,
    ):
        print(f"[{position}/{total}] {name}")

        stage()

        print()

    print("=" * 27)
    print("Pipeline complete.")

    print()
    print("Operational outputs:")
    print("  data/processed/reconciliation/")
    print("  reports/reconciliation/")


if __name__ == "__main__":
    main()
