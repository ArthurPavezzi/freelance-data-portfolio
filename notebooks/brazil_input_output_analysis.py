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
from input_output.shocks import (
    apply_final_demand_shock,
    build_percentage_shock,
)

from input_output.scenarios import (
    ShockScenario,
    compare_scenarios,
    run_scenarios,
    write_scenario_outputs,
)
# %% [markdown]
# ## 1. Load official IBGE data

# %%
WORKBOOK = (
    "data/raw/ibge_mip/2015/"
    "Matriz_de_Insumo_Produto_2015_Nivel_67.xls"
)

tables = parse_ibge_workbook(
    WORKBOOK
)

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
key_sectors = (
    linkages
    .loc[
        linkages["is_key_sector"],
        "sector_code",
    ]
    .tolist()
)

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
delta_y_exports = (
    tables
    .final_demand_by_sector[
        "exports"
    ]
    * 0.10
)

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
delta_y_investment = (
    tables
    .final_demand_by_sector[
        "gross_fixed_capital_formation"
    ]
    * 0.10
)

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
        description=(
            "40% increase in final demand "
            "for Rasmussen-Hirschman "
            "key sectors"
        ),
        delta_final_demand=(
            delta_y_key
        ),
    ),
    ShockScenario(
        name="exports_10pct",
        description=(
            "10% increase in exports"
        ),
        delta_final_demand=(
            delta_y_exports
        ),
    ),
    ShockScenario(
        name="investment_10pct",
        description=(
            "10% increase in gross fixed "
            "capital formation"
        ),
        delta_final_demand=(
            delta_y_investment
        ),
    ),
]

runs = run_scenarios(
    scenarios=scenarios,
    leontief=L,
    sectors=tables.sectors,
)

scenario_comparison = (
    compare_scenarios(
        runs
    )
)

scenario_comparison

# %% [markdown]
# ## 8. Export scenario results

# %%
scenario_paths = (
    write_scenario_outputs(
        runs=runs
    )
)

scenario_paths