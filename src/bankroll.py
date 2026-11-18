"""
Bankroll management: how big a cushion does an edge need?

Risk of ruin (RoR), closed form
-------------------------------
Model winnings as a random walk with drift `wr` and volatility `sd` per 100
hands (a Brownian motion with drift). The probability of EVER losing a
bankroll of B big blinds, playing the same stake forever, is

    RoR = exp(-2 * wr * B / sd^2)        (for wr > 0; RoR = 1 if wr <= 0)

Inverting it gives the bankroll needed for a target risk:

    B = -sd^2 * ln(RoR) / (2 * wr)

Kelly link
----------
Choosing the stake so that 1 big blind is a fraction k of the bankroll, the
long-run log growth per 100 hands is about  k*wr - (k*sd)^2 / 2, which is
maximised at k* = wr / sd^2. So the Kelly-optimal bankroll is

    B_kelly = sd^2 / wr   big blinds.

Plug B_kelly into the RoR formula: a player who sits at full-Kelly bankroll and
NEVER moves down in stakes has RoR = exp(-2), about 13.5%. Half Kelly
(twice the bankroll) gives exp(-4), about 1.8%. Real Kelly bettors avoid ruin
by shrinking their bets as they lose; the fixed-stake case shows why moving
down is part of any serious bankroll rule.

The catch: every formula here needs the TRUE win rate, which we only know as
an interval (see winrate.py). Ruin risk is extremely sensitive to it.
"""

from __future__ import annotations

import math

import numpy as np

from .simulate import career_paths, simulate_blocks

BB_PER_BUYIN = 100  # a standard full buy-in is 100 big blinds


def risk_of_ruin(wr: float, sd: float, bankroll_bb: float) -> float:
    """Probability of ever losing `bankroll_bb` at a fixed stake (infinite horizon)."""
    if wr <= 0:
        return 1.0
    return math.exp(-2 * wr * bankroll_bb / sd ** 2)


def bankroll_for_risk(wr: float, sd: float, target_ror: float) -> float:
    """Bankroll in big blinds needed for a target risk of ruin."""
    if wr <= 0:
        return math.inf
    if not 0 < target_ror < 1:
        raise ValueError("target_ror must be between 0 and 1")
    return -sd ** 2 * math.log(target_ror) / (2 * wr)


def kelly_bankroll(wr: float, sd: float, fraction: float = 1.0) -> float:
    """Bankroll in big blinds for fractional Kelly (fraction=0.5 is half Kelly)."""
    if wr <= 0:
        return math.inf
    return (sd ** 2 / wr) / fraction


def expected_risk_of_ruin(wr_hat: float, se: float, sd: float, bankroll_bb: float,
                          grid: int = 4001) -> float:
    """
    Risk of ruin averaged over our uncertainty about the true win rate.

    The true win rate is treated as Normal(wr_hat, se), a flat-prior
    approximation using the standard error from winrate.py. Because RoR is a
    CONVEX function of the win rate, Jensen's inequality guarantees

        average of RoR(w)  >=  RoR(average w)

    so plugging in the point estimate always understates the risk. This is
    the Talebian point that uncertainty about a parameter is itself a risk.
    """
    w = np.linspace(wr_hat - 8 * se, wr_hat + 8 * se, grid)
    density = np.exp(-0.5 * ((w - wr_hat) / se) ** 2)
    density /= density.sum()
    ror = np.where(w > 0, np.exp(-2 * np.clip(w, 0, None) * bankroll_bb / sd ** 2), 1.0)
    return float((ror * density).sum())


def absorb(paths: np.ndarray, bankroll_bb: float) -> tuple[np.ndarray, np.ndarray]:
    """
    Apply an absorbing barrier: once a career loses `bankroll_bb`, it stops
    there for good (no rebuys, no second chance).

    Returns (absorbed_paths, ruined_mask). This is the difference between
    ensemble probability (2,000 players each playing once) and time
    probability (one player living through one path), which Taleb discusses
    in Skin in the Game, building on Ole Peters' work on ergodicity.
    """
    hit = paths <= -bankroll_bb
    ruined = hit.any(axis=1)
    first_hit = np.where(ruined, hit.argmax(axis=1), paths.shape[1])
    cols = np.arange(paths.shape[1])
    after = cols[None, :] >= first_hit[:, None]
    return np.where(after, -bankroll_bb, paths), ruined


def simulated_ruin(wr: float, sd: float, bankroll_bb: float, hands: int,
                   n_careers: int = 5000, dist: str = "normal",
                   seed: int | None = 7) -> float:
    """
    Share of simulated careers that lose the whole bankroll within `hands`.
    Checked at 100-hand intervals, so it slightly understates true risk.
    """
    blocks = simulate_blocks(wr, sd, hands, n_careers, dist=dist, seed=seed)
    paths = career_paths(blocks)
    return float((paths.min(axis=1) <= -bankroll_bb).mean())


if __name__ == "__main__":
    wr, sd = 4.0, 100.0
    print(f"Assumed true wr {wr} bb/100, sd {sd} bb/100\n")
    print(f"{'Buy-ins':>8} {'RoR (formula)':>14} {'RoR in 100k hands (sim)':>24}")
    for buyins in (10, 20, 30, 50, 100):
        b = buyins * BB_PER_BUYIN
        print(f"{buyins:>8} {risk_of_ruin(wr, sd, b):>14.2%} "
              f"{simulated_ruin(wr, sd, b, hands=100_000):>24.2%}")
    print(f"\nFull Kelly bankroll: {kelly_bankroll(wr, sd) / BB_PER_BUYIN:.0f} buy-ins")
    print(f"Half Kelly bankroll: {kelly_bankroll(wr, sd, 0.5) / BB_PER_BUYIN:.0f} buy-ins")
