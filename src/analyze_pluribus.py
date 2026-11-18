"""
Analyze the 10,000 hands Pluribus played against five professionals.

Usage (after running the loader):
    python -m src.analyze_pluribus --db data/poker.db

What it does
1. Checks the data reconciles (every hand sums to zero chips).
2. Computes Pluribus's RAW win rate with a 95% interval, using SQL for the
   aggregation and Python for the statistics.
3. Compares that interval with the published estimate (48 mbb/game, standard
   error 25 mbb/game, i.e. 4.8 +/- 2.5 bb/100), which the authors obtained with
   AIVAT, a variance-reduction method that removes much of the card luck.
4. Splits results by position and computes VPIP/PFR, showing how slicing a
   sample makes every estimate noisier.
5. Saves figures to figures/ and a Markdown summary to results/.
"""

from __future__ import annotations

import argparse
import math
import re
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .winrate import hands_needed, z_value

ROOT = Path(__file__).resolve().parent.parent
QUERIES_PATH = ROOT / "sql" / "queries.sql"
FIG_DIR = ROOT / "figures"
RESULTS_DIR = ROOT / "results"

# Published result, Brown & Sandholm (2019), Science: 5 humans + 1 Pluribus.
AIVAT_WR_BB100 = 4.8
AIVAT_SE_BB100 = 2.5


def load_queries(path: Path = QUERIES_PATH) -> dict[str, str]:
    """Split queries.sql on '-- name: x' markers into {name: sql}."""
    text = path.read_text()
    chunks = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    return {chunks[i]: chunks[i + 1].strip() for i in range(1, len(chunks), 2)}


def run(con: sqlite3.Connection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def interval_from_moments(n: int, mean_bb: float, mean_sq_bb: float) -> dict:
    """
    Turn per-hand moments into bb/100 statistics.
    sd per hand uses the n-1 (sample) correction.
    """
    var = max(mean_sq_bb - mean_bb ** 2, 0.0) * n / max(n - 1, 1)
    sd_hand = math.sqrt(var)
    wr = mean_bb * 100
    sd_100 = sd_hand * 10                 # sd of a 100-hand block
    se = sd_100 / math.sqrt(n / 100)
    z = z_value(0.95)
    return {"wr": wr, "sd_100": sd_100, "se": se,
            "low": wr - z * se, "high": wr + z * se}


def fig_cumulative(seq: list[float], stats: dict, path: Path) -> None:
    x = np.arange(1, len(seq) + 1)
    cum = np.cumsum(seq)
    band = 1.96 * (stats["sd_100"] / 10) * np.sqrt(x)  # luck band around zero
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.fill_between(x, -band, band, color="#9aa7b8", alpha=0.25,
                    label="95% range for a zero-edge player (pure luck)")
    ax.plot(x, cum, color="#1f4e79", lw=1.4, label="Pluribus, cumulative big blinds")
    ax.plot(x, x * AIVAT_WR_BB100 / 100, color="#c0504d", lw=1.2, ls="--",
            label=f"Published AIVAT estimate ({AIVAT_WR_BB100} bb/100)")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xlabel("Hands")
    ax.set_ylabel("Big blinds won")
    ax.set_title("Pluribus vs. five pros: raw results against the luck band")
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def fig_positions(rows: list[dict], path: Path) -> None:
    labels = [r["position"] for r in rows]
    wr = [r["wr"] for r in rows]
    err = [1.96 * r["se"] for r in rows]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, wr, color="#1f4e79", alpha=0.85)
    ax.errorbar(labels, wr, yerr=err, fmt="none", ecolor="black", capsize=5, lw=1)
    ax.axhline(0, color="black", lw=0.6)
    ax.set_ylabel("bb/100 (bars: 95% interval)")
    ax.set_title("Pluribus win rate by position: smaller slices, wider intervals")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze the Pluribus hand database.")
    parser.add_argument("--db", type=Path, default=Path("data/poker.db"))
    args = parser.parse_args()

    FIG_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)
    q = load_queries()
    con = sqlite3.connect(args.db)

    check = run(con, q["data_check"])[0]
    print(f"Hands: {check['hands']:,}  with result: {check['hands_with_result']:,}  "
          f"not zero-sum: {check['hands_not_zero_sum']:,}")

    players = run(con, q["player_summary"])
    for p in players:
        p.update(interval_from_moments(p["hands"], p["mean_bb"], p["mean_sq_bb"]))
    plur = next((p for p in players if p["player"] == "Pluribus"), None)
    if plur is None:
        raise SystemExit("No rows for player 'Pluribus'. Check the player names in the data.")

    positions = run(con, q["pluribus_by_position"])
    for r in positions:
        r.update(interval_from_moments(r["hands"], r["mean_bb"], r["mean_sq_bb"]))

    vpip = run(con, q["vpip_pfr"])
    sessions = run(con, q["session_results"])
    seq = [r["net_bb"] for r in run(con, q["pluribus_sequence"])]
    con.close()

    # How many raw hands would match the precision AIVAT reached?
    raw_hands_for_aivat_precision = hands_needed(plur["sd_100"], 1.96 * AIVAT_SE_BB100)
    variance_ratio = (plur["se"] / AIVAT_SE_BB100) ** 2

    fig_cumulative(seq, plur, FIG_DIR / "pluribus_cumulative.png")
    fig_positions(positions, FIG_DIR / "pluribus_by_position.png")

    lines = [
        "# Pluribus results (generated by src/analyze_pluribus.py)",
        "",
        f"Data check: {check['hands']:,} hands, {check['hands_with_result']:,} with a result, "
        f"{check['hands_not_zero_sum']:,} failing the zero-sum check.",
        "",
        "## Raw win rate vs. the published AIVAT estimate",
        "",
        "| Estimate | Win rate (bb/100) | Std. error | 95% interval |",
        "|---|---|---|---|",
        f"| Raw results, {plur['hands']:,} hands | {plur['wr']:.2f} | {plur['se']:.2f} | "
        f"{plur['low']:.2f} to {plur['high']:.2f} |",
        f"| Published (AIVAT) | {AIVAT_WR_BB100:.2f} | {AIVAT_SE_BB100:.2f} | "
        f"{AIVAT_WR_BB100 - 1.96 * AIVAT_SE_BB100:.2f} to {AIVAT_WR_BB100 + 1.96 * AIVAT_SE_BB100:.2f} |",
        "",
        f"Raw standard deviation: {plur['sd_100']:.1f} bb/100.",
        f"Raw results would need about {raw_hands_for_aivat_precision:,} hands to be as precise "
        f"as the AIVAT estimate, roughly {variance_ratio:.1f}x the sample.",
        "",
        "## By position (Pluribus)",
        "",
        "| Position | Hands | bb/100 | 95% interval |",
        "|---|---|---|---|",
    ]
    lines += [f"| {r['position']} | {r['hands']:,} | {r['wr']:.1f} | "
              f"{r['low']:.1f} to {r['high']:.1f} |" for r in positions]
    lines += ["", "## Preflop style", "", "| Who | Player-hands | VPIP % | PFR % |", "|---|---|---|---|"]
    lines += [f"| {r['who']} | {r['player_hands']:,} | {r['vpip_pct']} | {r['pfr_pct']} |" for r in vpip]
    lines += ["", "## Per player label", "",
              "Human labels are anonymized seat names; do not assume one label is one person.", "",
              "| Player | Hands | bb/100 | 95% interval |", "|---|---|---|---|"]
    lines += [f"| {p['player']} | {p['hands']:,} | {p['wr']:.1f} | {p['low']:.1f} to {p['high']:.1f} |"
              for p in players]
    lines += ["", "## By session folder (Pluribus)", "", "| Session | Hands | bb/100 |", "|---|---|---|"]
    lines += [f"| {s['session']} | {s['hands']:,} | {s['bb_per_100']} |" for s in sessions]

    out = RESULTS_DIR / "pluribus_summary.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[5:12]))
    print(f"\nSaved {out} and two figures in {FIG_DIR}/")


if __name__ == "__main__":
    main()
