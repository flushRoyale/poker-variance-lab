"""
Figures and numbers for Parts 1 and 2 (no downloaded data needed).

    python -m src.make_figures

Inputs are the self-reported record (500,000+ hands, about 4 bb/100) plus a
RANGE of standard deviations, because the true SD is unknown.
Every simulation uses a fixed seed so results are reproducible.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from . import bankroll, simulate, winrate

ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = ROOT / "figures"
RESULTS_DIR = ROOT / "results"

WR = 4.0            # bb/100, self-reported
HANDS = 500_000     # self-reported lower bound
SD_BASE = 100.0     # assumption for the base case; see the SD range below
SD_RANGE = [70, 80, 90, 100, 110, 120, 130]
BUYIN = bankroll.BB_PER_BUYIN

NAVY, RED, GREY, GOLD = "#1f4e79", "#c0504d", "#9aa7b8", "#d9a441"


def _style(ax):
    ax.spines[["top", "right"]].set_visible(False)


def fig_interval_vs_sd(path: Path) -> list[dict]:
    rows = winrate.sensitivity_table(WR, HANDS, SD_RANGE)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for i, r in enumerate(rows):
        ax.plot([r["ci_low"], r["ci_high"]], [i, i], color=NAVY, lw=3)
        ax.plot(WR, i, "o", color=RED)
        ax.text(r["ci_high"] + 0.15, i, f"{r['ci_low']:.1f} to {r['ci_high']:.1f}",
                va="center", fontsize=8)
    ax.axvline(0, color="black", lw=0.6)
    ax.set_yticks(range(len(rows)), [f"SD {r['sd_bb100']:.0f}" for r in rows])
    ax.set_xlabel("True win rate, bb/100 (95% interval)")
    ax.set_title("4 bb/100 over 500,000 hands: what the true edge could be")
    ax.set_xlim(-0.5, 9.5)
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return rows


def fig_interval_vs_sample(path: Path) -> None:
    hands = np.logspace(3, 6.3, 200)
    half = [winrate.z_value() * winrate.standard_error(SD_BASE, h) for h in hands]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.fill_between(hands, WR - np.array(half), WR + np.array(half), color=GREY, alpha=0.4)
    ax.axhline(WR, color=RED, lw=1, ls="--", label="Observed 4 bb/100")
    ax.axhline(0, color="black", lw=0.6)
    for h, label in [(10_000, "10k hands\n(Pluribus study)"),
                     (100_000, "100k"), (500_000, "500k\n(my record)")]:
        hw = winrate.z_value() * winrate.standard_error(SD_BASE, h)
        ax.plot([h, h], [WR - hw, WR + hw], color=NAVY, lw=2)
        ax.text(h, WR + hw + 1, f"{label}\n±{hw:.1f}", ha="center", fontsize=8)
    ax.set_xscale("log")
    ax.set_ylim(-25, 40)
    ax.set_xlabel("Hands played (log scale)")
    ax.set_ylabel("95% interval, bb/100")
    ax.set_title(f"How fast uncertainty shrinks (SD = {SD_BASE:.0f} bb/100)")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_careers(sim: dict, path: Path) -> None:
    paths = sim["paths"] / BUYIN
    x = np.arange(paths.shape[1]) * simulate.BLOCK / 1000
    fig, ax = plt.subplots(figsize=(9, 4.8))
    for p in paths[:80]:
        ax.plot(x, p, color=GREY, lw=0.5, alpha=0.5)
    lo, hi = np.percentile(paths, [5, 95], axis=0)
    ax.plot(x, lo, color=NAVY, lw=1.2, ls=":", label="5th and 95th percentile")
    ax.plot(x, hi, color=NAVY, lw=1.2, ls=":")
    worst = paths[np.argmin(paths[:, -1])]
    ax.plot(x, worst, color=RED, lw=1.3, label="Unluckiest of 2,000 careers")
    ax.plot(x, x * 1000 * WR / 100 / BUYIN, color="black", lw=1.2,
            label="Expected path (true 4 bb/100)")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xlabel("Thousands of hands")
    ax.set_ylabel("Buy-ins won (1 buy-in = 100 bb)")
    ax.set_title("2,000 simulated careers of the SAME 4 bb/100 player")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_drawdowns(sim_n: dict, sim_t: dict, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    bins = np.linspace(0, 120, 41)
    axes[0].hist(sim_n["drawdowns"] / BUYIN, bins=bins, color=NAVY, alpha=0.6, label="Normal blocks")
    axes[0].hist(sim_t["drawdowns"] / BUYIN, bins=bins, color=GOLD, alpha=0.5,
                 label="Fat-tailed blocks (t, df=3)")
    axes[0].set_xlabel("Largest drawdown, buy-ins")
    axes[0].set_ylabel("Careers")
    axes[0].set_title("Worst downswing over 500k hands")
    axes[0].legend(frameon=False, fontsize=8)
    bins2 = np.linspace(0, 400, 41)
    axes[1].hist(sim_n["underwater"] / 1000, bins=bins2, color=NAVY, alpha=0.6, label="Normal blocks")
    axes[1].hist(sim_t["underwater"] / 1000, bins=bins2, color=GOLD, alpha=0.5,
                 label="Fat-tailed blocks (t, df=3)")
    axes[1].set_xlabel("Longest stretch without a new high, thousands of hands")
    axes[1].set_title("Longest break-even stretch")
    axes[1].legend(frameon=False, fontsize=8)
    for ax in axes:
        _style(ax)
    fig.suptitle("A true 4 bb/100 winner (SD 100) still suffers this", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_risk_of_ruin(low_wr: float, se: float, path: Path) -> list[dict]:
    buyins = np.arange(5, 101)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    point = [bankroll.risk_of_ruin(WR, SD_BASE, b * BUYIN) for b in buyins]
    averaged = [bankroll.expected_risk_of_ruin(WR, se, SD_BASE, b * BUYIN) for b in buyins]
    low = [bankroll.risk_of_ruin(low_wr, SD_BASE, b * BUYIN) for b in buyins]
    ax.plot(buyins, np.array(point) * 100, color=NAVY, lw=1.8,
            label=f"Plug in the point estimate ({WR:.0f} bb/100)")
    ax.plot(buyins, np.array(averaged) * 100, color=GOLD, lw=2.2,
            label="Average over uncertainty about the true win rate")
    ax.plot(buyins, np.array(low) * 100, color=RED, lw=1.4, ls="--",
            label=f"True win rate at the lower end of the interval ({low_wr:.1f})")
    k = bankroll.kelly_bankroll(WR, SD_BASE) / BUYIN
    trans = ax.get_xaxis_transform()  # x in data units, y in axes units
    ax.axvline(k, color=GREY, ls="--", lw=1)
    ax.text(k + 1, 0.36, f"Full Kelly at 4 bb/100\n= {k:.0f} buy-ins", fontsize=8, transform=trans)
    ax.axvline(2 * k, color=GREY, ls=":", lw=1)
    ax.text(2 * k + 1, 0.36, f"Half Kelly\n= {2 * k:.0f} buy-ins", fontsize=8, transform=trans)
    ax.set_yscale("log")
    ax.set_ylim(0.01, 100)
    ax.set_yticks([0.01, 0.1, 1, 10, 100], ["0.01%", "0.1%", "1%", "10%", "100%"])
    ax.set_xlabel("Bankroll, buy-ins (fixed stake, never moving down)")
    ax.set_ylabel("Risk of ruin (log scale)")
    ax.set_title(f"Not knowing your edge is a risk in itself (SD = {SD_BASE:.0f} bb/100)")
    ax.legend(fontsize=8, loc="lower left", framealpha=0.95, edgecolor="none")
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)

    table = []
    for b in (20, 30, 50, 100):
        table.append({"buyins": b,
                      "ror_point": bankroll.risk_of_ruin(WR, SD_BASE, b * BUYIN),
                      "ror_avg": bankroll.expected_risk_of_ruin(WR, se, SD_BASE, b * BUYIN),
                      "ror_low": bankroll.risk_of_ruin(low_wr, SD_BASE, b * BUYIN)})
    return table


def fig_silent_evidence(sim: dict, bankroll_buyins: int, path: Path) -> dict:
    """Same 2,000 careers, but now losing the bankroll ends the career."""
    absorbed, ruined = bankroll.absorb(sim["paths"], bankroll_buyins * BUYIN)
    paths = absorbed / BUYIN
    x = np.arange(paths.shape[1]) * simulate.BLOCK / 1000
    fig, ax = plt.subplots(figsize=(9, 4.8))
    shown = np.arange(400)
    for i in shown[~ruined[shown]]:
        ax.plot(x, paths[i], color=GREY, lw=0.5, alpha=0.45)
    for i in shown[ruined[shown]]:
        ax.plot(x, paths[i], color=RED, lw=0.9, alpha=0.9)
    ax.axhline(-bankroll_buyins, color=RED, lw=0.8, ls="--")
    ax.text(x[-1], -bankroll_buyins - 18, f"Bankroll gone ({bankroll_buyins} buy-ins)",
            ha="right", fontsize=8, color=RED)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylim(bottom=-bankroll_buyins - 30)
    ax.set_xlabel("Thousands of hands")
    ax.set_ylabel("Buy-ins won")
    ax.set_title(f"Silent evidence: same edge, {ruined.mean():.0%} of careers end in ruin "
                 f"(red, 400 of 2,000 shown)")
    _style(ax)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return {"bankroll_buyins": bankroll_buyins,
            "ruined_share": float(ruined.mean()),
            "ruined_count": int(ruined.sum()),
            "mean_final_free": float(sim["paths"][:, -1].mean() / BUYIN),
            "mean_final_absorbed": float(absorbed[:, -1].mean() / BUYIN)}


def main() -> None:
    FIG_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)

    sd_rows = fig_interval_vs_sd(FIG_DIR / "interval_vs_sd.png")
    fig_interval_vs_sample(FIG_DIR / "interval_vs_sample.png")

    sim_n = simulate.summarize(WR, SD_BASE, HANDS, n_careers=2000, dist="normal", seed=42)
    sim_t = simulate.summarize(WR, SD_BASE, HANDS, n_careers=2000, dist="t", seed=42)
    fig_careers(sim_n, FIG_DIR / "simulated_careers.png")
    fig_drawdowns(sim_n, sim_t, FIG_DIR / "drawdowns.png")

    se = winrate.standard_error(SD_BASE, HANDS)
    low_wr = winrate.confidence_interval(WR, SD_BASE, HANDS)[0]
    ror_rows = fig_risk_of_ruin(low_wr, se, FIG_DIR / "risk_of_ruin.png")
    ens = fig_silent_evidence(sim_n, 30, FIG_DIR / "silent_evidence.png")

    L = ["# Simulation results (generated by src/make_figures.py)", "",
         f"Inputs: observed {WR} bb/100 over {HANDS:,} hands (self-reported). "
         f"SD unknown; base case {SD_BASE:.0f} bb/100.", "",
         "## Part 1: interval for the true win rate", "",
         "| SD (bb/100) | Std. error | 95% interval | P(true wr > 0) |", "|---|---|---|---|"]
    L += [f"| {r['sd_bb100']:.0f} | {r['se_bb100']:.2f} | {r['ci_low']:.2f} to {r['ci_high']:.2f} | "
          f"{r['p_true_winner']:.4f} |" for r in sd_rows]
    L += ["", f"Hands for a ±1 bb/100 interval at SD {SD_BASE:.0f}: "
          f"{winrate.hands_needed(SD_BASE, 1):,}", "",
          f"## Part 1: chance a true {WR:.0f} bb/100 player is ahead (SD {SD_BASE:.0f})", "",
          "| Window | P(ahead) |", "|---|---|"]
    for h, label in [(100, "100 hands (one short session)"), (1_000, "1,000 hands"),
                     (10_000, "10,000 hands"), (100_000, "100,000 hands"),
                     (500_000, "500,000 hands")]:
        L.append(f"| {label} | {winrate.prob_up_after(WR, SD_BASE, h):.1%} |")
    L += ["", "## Part 1b: 2,000 simulated careers of a true 4 bb/100 player (SD 100, 500k hands)", "",
          "| Metric | Normal blocks | Fat-tailed blocks (t, df=3) |", "|---|---|---|"]
    for key, label, scale, fmt in [
        ("observed_wr_p5", "Observed win rate, 5th pct (bb/100)", 1, "{:.2f}"),
        ("observed_wr_p95", "Observed win rate, 95th pct (bb/100)", 1, "{:.2f}"),
        ("max_drawdown_median_bb", "Largest drawdown, median (buy-ins)", BUYIN, "{:.0f}"),
        ("max_drawdown_p95_bb", "Largest drawdown, 95th pct (buy-ins)", BUYIN, "{:.0f}"),
        ("underwater_median_hands", "Longest break-even stretch, median (hands)", 1, "{:,.0f}"),
        ("underwater_p95_hands", "Longest break-even stretch, 95th pct (hands)", 1, "{:,.0f}"),
    ]:
        L.append(f"| {label} | {fmt.format(sim_n[key] / scale)} | {fmt.format(sim_t[key] / scale)} |")
    L += ["", f"## Part 2: risk of ruin at a fixed stake (SD {SD_BASE:.0f})", "",
          f"| Bankroll (buy-ins) | Point estimate ({WR:.0f}) | Averaged over uncertainty | "
          f"Lower end ({low_wr:.2f}) |", "|---|---|---|---|"]
    L += [f"| {r['buyins']} | {r['ror_point']:.1%} | {r['ror_avg']:.1%} | {r['ror_low']:.1%} |"
          for r in ror_rows]
    L += ["", f"Full Kelly bankroll at {WR} bb/100: {bankroll.kelly_bankroll(WR, SD_BASE) / BUYIN:.0f} buy-ins; "
          f"half Kelly: {bankroll.kelly_bankroll(WR, SD_BASE, 0.5) / BUYIN:.0f} buy-ins.", "",
          f"## Part 2: ensemble vs. time ({ens['bankroll_buyins']} buy-in bankroll, 500k hands)", "",
          "| Measure | Value |", "|---|---|",
          f"| Average final result, no ruin possible (buy-ins) | {ens['mean_final_free']:.0f} |",
          f"| Average final result when ruin ends the career (buy-ins) | {ens['mean_final_absorbed']:.0f} |",
          f"| Careers ruined | {ens['ruined_count']} of 2,000 ({ens['ruined_share']:.1%}) |"]

    out = RESULTS_DIR / "simulation_summary.md"
    out.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
