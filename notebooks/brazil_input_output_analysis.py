# %% [markdown]
# # Brazilian Input-Output Analysis
#
# Reconstructing Brazil's 2015 input-output system from
# official IBGE data and evaluating structural linkages
# and final-demand shocks.

# %%
from input_output.linkages import rasmussen_hirschman
from input_output.matrices import (
    build_leontief_inverse,
    build_technical_matrix,
)
from input_output.parse import parse_ibge_workbook
from input_output.scenarios import (
    ShockScenario,
    compare_scenarios,
    run_scenarios,
    write_scenario_outputs,
)
from input_output.shocks import (
    apply_final_demand_shock,
    build_percentage_shock,
    rescale_shock_to_total,
)

# %% [markdown]
# ## 1. Load official IBGE data

# %%
WORKBOOK = "data/raw/ibge_mip/2015/Matriz_de_Insumo_Produto_2015_Nivel_67.xls"

tables = parse_ibge_workbook(WORKBOOK)

tables.Bn.shape, tables.D.shape


# %% [markdown]
# ## 2. Reconstruct the technical coefficient matrix
# ## and Leontief inverse

# %%
A = build_technical_matrix(
    tables.D,
    tables.Bn,
)

L = build_leontief_inverse(A)

A.shape, L.shape


# %% [markdown]
# ## 3. Rasmussen-Hirschman linkages

# %%
linkages = rasmussen_hirschman(
    L,
    tables.sectors,
)

linkages.sort_values(
    [
        "is_key_sector",
        "backward_linkage",
    ],
    ascending=[
        False,
        False,
    ],
).head(20)


# %% [markdown]
# ## 4. Scenario 1 — 40% increase in final demand
# ## of key sectors
#
# This reproduces the basic scenario explored in the
# original analysis, but using the reconstructed official
# input-output system and a reusable shock engine.

# %%
key_sectors = linkages.loc[
    linkages["is_key_sector"],
    "sector_code",
].tolist()

delta_y_key = build_percentage_shock(
    final_demand=tables.final_demand,
    sector_codes=key_sectors,
    rate=0.40,
)

key_result = apply_final_demand_shock(
    leontief=L,
    delta_final_demand=delta_y_key,
    sectors=tables.sectors,
)

key_result


# %%
key_result.sector_impacts.sort_values(
    "total_output_impact",
    ascending=False,
).head(15)


# %% [markdown]
# ## 5. Scenario 2 — 10% increase in exports

# %%
delta_y_exports = tables.final_demand_by_sector["exports"] * 0.10

export_result = apply_final_demand_shock(
    leontief=L,
    delta_final_demand=delta_y_exports,
    sectors=tables.sectors,
)

export_result


# %%
export_result.sector_impacts.sort_values(
    "total_output_impact",
    ascending=False,
).head(15)


# %% [markdown]
# ## 6. Scenario 3 — 10% increase in investment

# %%
delta_y_investment = tables.final_demand_by_sector["gross_fixed_capital_formation"] * 0.10

investment_result = apply_final_demand_shock(
    leontief=L,
    delta_final_demand=delta_y_investment,
    sectors=tables.sectors,
)

investment_result


# %%
investment_result.sector_impacts.sort_values(
    "total_output_impact",
    ascending=False,
).head(15)


# %% [markdown]
# ## 7. Scenario comparison

# %%
scenarios = [
    ShockScenario(
        name="key_sectors_40pct",
        description=("40% increase in final demand for Rasmussen-Hirschman key sectors"),
        delta_final_demand=(delta_y_key),
    ),
    ShockScenario(
        name="exports_10pct",
        description=("10% increase in exports"),
        delta_final_demand=(delta_y_exports),
    ),
    ShockScenario(
        name="investment_10pct",
        description=("10% increase in gross fixed capital formation"),
        delta_final_demand=(delta_y_investment),
    ),
]

runs = run_scenarios(
    scenarios=scenarios,
    leontief=L,
    sectors=tables.sectors,
)

scenario_comparison = compare_scenarios(runs)

scenario_comparison

# %% [markdown]
# ## 8. Export scenario results

# %%
scenario_paths = write_scenario_outputs(runs=runs)

scenario_paths

# %% [markdown]
# ## 9. Equal-size scenario comparison
#
# The previous scenarios differ both in composition and in
# the total size of the demand shock. To isolate the effect
# of sectoral composition, each shock is rescaled to the same
# R$ 100 billion increase in final demand.
#
# Values in the IBGE input-output tables are expressed in
# R$ millions, so R$ 100 billion corresponds to 100,000.

# %%
EQUAL_SHOCK_TOTAL = 100_000.0

delta_y_key_equal = rescale_shock_to_total(
    delta_final_demand=delta_y_key,
    target_total=EQUAL_SHOCK_TOTAL,
)

delta_y_exports_equal = rescale_shock_to_total(
    delta_final_demand=delta_y_exports,
    target_total=EQUAL_SHOCK_TOTAL,
)

delta_y_investment_equal = rescale_shock_to_total(
    delta_final_demand=delta_y_investment,
    target_total=EQUAL_SHOCK_TOTAL,
)

(
    delta_y_key_equal.sum(),
    delta_y_exports_equal.sum(),
    delta_y_investment_equal.sum(),
)

# %%
equal_size_scenarios = [
    ShockScenario(
        name="key_sectors_100bn",
        description=(
            "R$ 100 billion final-demand shock "
            "distributed according to the "
            "key-sector scenario composition"
        ),
        delta_final_demand=(delta_y_key_equal),
    ),
    ShockScenario(
        name="exports_100bn",
        description=(
            "R$ 100 billion export shock "
            "distributed according to baseline "
            "sectoral export composition"
        ),
        delta_final_demand=(delta_y_exports_equal),
    ),
    ShockScenario(
        name="investment_100bn",
        description=(
            "R$ 100 billion investment shock "
            "distributed according to baseline "
            "sectoral investment composition"
        ),
        delta_final_demand=(delta_y_investment_equal),
    ),
]

equal_size_runs = run_scenarios(
    scenarios=equal_size_scenarios,
    leontief=L,
    sectors=tables.sectors,
)

equal_size_comparison = compare_scenarios(equal_size_runs)

equal_size_comparison

# %% [markdown]
# ## 10. Export equal-size scenarios

# %%
equal_size_paths = write_scenario_outputs(
    runs=equal_size_runs,
    output_dir=("reports/input-output/scenarios/equal_size"),
)

equal_size_paths

# %% [markdown]
# ## 11. Comparing equal-size demand shocks
#
# Each scenario applies the same R$ 100 billion increase in
# final demand. Differences in total output therefore reflect
# differences in the sectoral composition of the shock.

# %%
from pathlib import Path

import matplotlib.pyplot as plt

plot_data = (
    equal_size_comparison.set_index("scenario")
    .loc[
        [
            "key_sectors_100bn",
            "exports_100bn",
            "investment_100bn",
        ],
        [
            "direct_demand_shock",
            "indirect_output_impact",
        ],
    ]
    .rename(
        index={
            "key_sectors_100bn": "Key sectors",
            "exports_100bn": "Exports",
            "investment_100bn": "Investment",
        },
        columns={
            "direct_demand_shock": "Direct demand shock",
            "indirect_output_impact": "Indirect output impact",
        },
    )
    / 1_000
)

ax = plot_data.plot(
    kind="bar",
    stacked=True,
    figsize=(9, 6),
)

ax.set_title("Output Effects of a R$ 100 Billion Final-Demand Shock")

ax.set_xlabel("")
ax.set_ylabel("R$ billion")

ax.legend(title="")

ax.tick_params(
    axis="x",
    rotation=0,
)

plt.tight_layout()

for container_total, patch_group in zip(
    equal_size_comparison["total_output_impact"] / 1_000,
    ax.containers[-1],
):
    ax.annotate(
        f"{container_total:.1f}",
        (
            patch_group.get_x() + patch_group.get_width() / 2,
            patch_group.get_y() + patch_group.get_height(),
        ),
        xytext=(0, 4),
        textcoords="offset points",
        ha="center",
        va="bottom",
    )

figure_path = "figures/input-output/01_equal_size_shock_comparison.png"

figure_dir = Path("figures/input-output")

figure_dir.mkdir(
    parents=True,
    exist_ok=True,
)

plt.savefig(
    figure_path,
    dpi=300,
    bbox_inches="tight",
)

plt.show()

# %% [markdown]
# ## 12. Rasmussen-Hirschman structural linkages
#
# Forward linkages measure how strongly a sector supplies
# inputs to the rest of the economy, while backward linkages
# measure how strongly it depends on inputs from other sectors.
#
# Values above 1 indicate above-average linkages.
# Sectors above 1 in both dimensions are classified as
# key sectors (Type III).

# %%
from pathlib import Path

figure_dir = Path("figures/input-output")

figure_dir.mkdir(
    parents=True,
    exist_ok=True,
)

fig, ax = plt.subplots(figsize=(10, 8))

key_mask = linkages["is_key_sector"]

other_linkages = linkages.loc[~key_mask]

key_linkages = linkages.loc[key_mask]

ax.scatter(
    other_linkages["backward_linkage"],
    other_linkages["forward_linkage"],
    alpha=0.45,
    label="Other sectors",
)

ax.scatter(
    key_linkages["backward_linkage"],
    key_linkages["forward_linkage"],
    s=70,
    alpha=0.9,
    label="Key sectors",
    zorder=3,
)

ax.axvline(
    1.0,
    linewidth=1,
)

ax.axhline(
    1.0,
    linewidth=1,
)

ax.set_xlabel("Backward linkage")

ax.set_ylabel("Forward linkage")

ax.set_title("Rasmussen-Hirschman Linkages — Brazil, 2015")

ax.legend()

label_offsets = {
    "1991": (8, 6),
    "4900": (8, 6),
    "3500": (8, 6),
    "2091": (8, 6),
    "7380": (6, 14),
    "2200": (30, 10),
    "2092": (8, -16),
    "2491": (8, 8),
    "2500": (-22, -18),
    "1700": (8, 18),
    "6100": (8, -16),
}

for _, row in key_linkages.iterrows():
    offset = label_offsets[row["sector_code"]]

    ax.annotate(
        row["sector_code"],
        (
            row["backward_linkage"],
            row["forward_linkage"],
        ),
        xytext=offset,
        textcoords="offset points",
        fontsize=8,
    )

x_min, x_max = ax.get_xlim()
y_min, y_max = ax.get_ylim()

ax.text(
    x_min + 0.03 * (x_max - x_min),
    y_max - 0.06 * (y_max - y_min),
    "Type II\nForward-oriented",
    va="top",
)

ax.text(
    x_max - 0.03 * (x_max - x_min),
    y_max - 0.06 * (y_max - y_min),
    "Type III\nKey sectors",
    ha="right",
    va="top",
)

ax.text(
    x_min + 0.03 * (x_max - x_min),
    y_min + 0.04 * (y_max - y_min),
    "Type I\nWeak linkages",
    va="bottom",
)

ax.text(
    x_max - 0.03 * (x_max - x_min),
    y_min + 0.04 * (y_max - y_min),
    "Type IV\nBackward-oriented",
    ha="right",
    va="bottom",
)

plt.tight_layout()

plt.savefig(
    figure_dir / "02_rasmussen_hirschman_linkages.png",
    dpi=300,
    bbox_inches="tight",
)

plt.show()

# %%
key_sector_table = (
    key_linkages[
        [
            "sector_code",
            "sector_name",
            "forward_linkage",
            "backward_linkage",
        ]
    ]
    .sort_values(
        "forward_linkage",
        ascending=False,
    )
    .reset_index(drop=True)
)

key_sector_table

# %% [markdown]
# ## 13. Sectoral impact profiles
#
# Equal-size shocks can generate similar aggregate effects
# while producing very different sectoral patterns.
#
# To compare these productive signatures, we select the
# sectors with the largest output impacts across the three
# R$ 100 billion scenarios.

# %%
equal_run_map = {run.scenario.name: run for run in equal_size_runs}

TOP_N = 8

top_sector_codes = set()

for run in equal_size_runs:
    top_codes = run.result.sector_impacts.nlargest(
        TOP_N,
        "total_output_impact",
    )["sector_code"]

    top_sector_codes.update(top_codes)

len(top_sector_codes)

# %%
import pandas as pd

scenario_labels = {
    "key_sectors_100bn": "Key sectors",
    "exports_100bn": "Exports",
    "investment_100bn": "Investment",
}

impact_frames = []

for run in equal_size_runs:
    frame = run.result.sector_impacts.loc[lambda df: df["sector_code"].isin(top_sector_codes)][
        [
            "sector_code",
            "sector_name",
            "total_output_impact",
        ]
    ].copy()

    frame["scenario"] = scenario_labels[run.scenario.name]

    impact_frames.append(frame)

sector_scenario_impacts = pd.concat(
    impact_frames,
    ignore_index=True,
)

sector_scenario_impacts["impact_billion"] = sector_scenario_impacts["total_output_impact"] / 1_000

sector_scenario_impacts.head()

# %%
impact_pivot = sector_scenario_impacts.pivot(
    index=[
        "sector_code",
        "sector_name",
    ],
    columns="scenario",
    values="impact_billion",
).fillna(0.0)

impact_pivot["max_impact"] = impact_pivot.max(axis=1)

impact_pivot = impact_pivot.sort_values(
    "max_impact",
    ascending=True,
).drop(columns="max_impact")

impact_pivot

# %%
plot_sector_impacts = impact_pivot[
    [
        "Key sectors",
        "Exports",
        "Investment",
    ]
]

plot_sector_impacts.index = [f"{code} — {name}" for code, name in plot_sector_impacts.index]

ax = plot_sector_impacts.plot(
    kind="barh",
    figsize=(11, 9),
)

ax.set_title("Sectoral Output Effects of Equal-Size Demand Shocks")

ax.set_xlabel("Output impact (R$ billion)")

ax.set_ylabel("")

ax.legend(title="")

plt.tight_layout()

plt.savefig(
    figure_dir / "03_sectoral_shock_profiles.png",
    dpi=300,
    bbox_inches="tight",
)

plt.show()
