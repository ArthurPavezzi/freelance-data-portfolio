from pathlib import Path
import polars as pl
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"

# Expected repository outputs:
VALIDATION = Path("reports/reconciliation/internal_validation")
REPORT = Path("reports/reconciliation")

source = pl.read_csv(VALIDATION / "source_validation.csv")
paid_truth = pl.read_csv(VALIDATION / "paid_kpi_validation.csv")
paid_recon = pl.read_csv(REPORT / "reconstructed_paid_kpis.csv")

FIG.mkdir(parents=True, exist_ok=True)

# True vs reconstructed source volume
labels = source["source_canonical"].to_list()
truth = source["true_leads"].to_list()
recon = source["reconstructed_leads"].to_list()

fig, ax = plt.subplots(figsize=(9, 5.4))
x = list(range(len(labels)))
w = 0.36
ax.bar([i-w/2 for i in x], truth, w, label="Hidden truth")
ax.bar([i+w/2 for i in x], recon, w, label="Reconstructed")
ax.set_title("True vs. reconstructed trackable leads")
ax.set_ylabel("Lead entities")
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.legend()
ax.grid(axis="y", alpha=0.2)
fig.tight_layout()
fig.savefig(FIG / "01_source_reconstruction.png", dpi=180)
plt.close(fig)

# CPL comparison
joined = paid_recon.join(
    paid_truth.select(
        "source_canonical",
        "true_cpl",
    ),
    on="source_canonical",
    how="inner",
).sort("source_canonical")

labels = joined["source_canonical"].to_list()
series = {
    "Platform reported": joined["platform_reported_cpl"].to_list(),
    "CRM-confirmed": joined["crm_confirmed_cpl"].to_list(),
    "Reconstructed": joined["reconstructed_cpl"].to_list(),
    "Hidden truth": joined["true_cpl"].to_list(),
}
fig, ax = plt.subplots(figsize=(9, 5.4))
x = list(range(len(labels)))
w = 0.18
offsets = [-1.5*w, -0.5*w, 0.5*w, 1.5*w]
for (name, vals), off in zip(series.items(), offsets):
    ax.bar([i+off for i in x], vals, w, label=name)
ax.set_title("Paid-media CPL: reported, confirmed, reconstructed, and truth")
ax.set_ylabel("Cost per lead ($)")
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.legend()
ax.grid(axis="y", alpha=0.2)
fig.tight_layout()
fig.savefig(FIG / "02_paid_cpl_comparison.png", dpi=180)
plt.close(fig)

print(f"Wrote portfolio figures to {FIG}")
