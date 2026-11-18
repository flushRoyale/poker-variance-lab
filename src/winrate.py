"""
Win-rate statistics: how precisely does a sample of hands pin down a player's edge?

Units used everywhere in this project
-------------------------------------
- Win rate (wr): big blinds won per 100 hands  (bb/100)
- Standard deviation (sd): standard deviation of results per 100 hands (bb/100)
- Hands: number of hands played

Key idea
--------
If results in each block of 100 hands have standard deviation `sd`, then the
average over n blocks has standard error  sd / sqrt(n).  With hands/100 blocks:

    SE = sd / sqrt(hands / 100)

and an approximate 95% confidence interval for the true win rate is

    wr_observed  +/-  1.96 * SE

This leans on the Central Limit Theorem. Single poker hands are very skewed and
fat-tailed, but averages of many hands are close to normal, so the
approximation is reasonable for large samples (see the limitations section in
the README).
"""

from __future__ import annotations

import math
from statistics import NormalDist


def z_value(level: float = 0.95) -> float:
    """Two-sided z critical value, e.g. 1.96 for a 95% interval."""
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1")
    return NormalDist().inv_cdf(0.5 + level / 2)


def standard_error(sd_bb100: float, hands: int) -> float:
    """Standard error of an observed win rate, in bb/100."""
    if hands <= 0:
        raise ValueError("hands must be positive")
    return sd_bb100 / math.sqrt(hands / 100)


def confidence_interval(wr_bb100: float, sd_bb100: float, hands: int,
                        level: float = 0.95) -> tuple[float, float]:
    """Normal-approximation confidence interval for the true win rate."""
    half_width = z_value(level) * standard_error(sd_bb100, hands)
    return wr_bb100 - half_width, wr_bb100 + half_width


def hands_needed(sd_bb100: float, margin_bb100: float, level: float = 0.95) -> int:
    """
    Hands needed so the interval is wr +/- margin.

    Solve  z * sd / sqrt(h/100) = margin   for h:
        h = 100 * (z * sd / margin)^2
    """
    if margin_bb100 <= 0:
        raise ValueError("margin must be positive")
    return math.ceil(100 * (z_value(level) * sd_bb100 / margin_bb100) ** 2)


def prob_true_winner(wr_bb100: float, sd_bb100: float, hands: int) -> float:
    """
    Rough probability that the true win rate is above zero, treating the
    sampling distribution as normal around the observed win rate.
    (A frequentist would call 1 minus this a one-sided p-value; it is a quick
    intuition tool, not a full Bayesian posterior.)
    """
    se = standard_error(sd_bb100, hands)
    return NormalDist().cdf(wr_bb100 / se)


def prob_up_after(wr_bb100: float, sd_bb100: float, hands: int) -> float:
    """
    Probability that a player with TRUE win rate wr is ahead after `hands`.

    Inspired by Taleb's dentist in Fooled by Randomness: the more often you
    look at results, the more of what you see is noise. Over a short window
    the edge is invisible; it only shows up over long horizons.

        P(up) = Phi( wr * sqrt(hands/100) / sd )
    """
    return NormalDist().cdf(wr_bb100 * math.sqrt(hands / 100) / sd_bb100)


def sensitivity_table(wr_bb100: float, hands: int, sds: list[float],
                      level: float = 0.95) -> list[dict]:
    """Interval for one observed win rate across a range of plausible SDs."""
    rows = []
    for sd in sds:
        low, high = confidence_interval(wr_bb100, sd, hands, level)
        rows.append({
            "sd_bb100": sd,
            "se_bb100": standard_error(sd, hands),
            "ci_low": low,
            "ci_high": high,
            "p_true_winner": prob_true_winner(wr_bb100, sd, hands),
        })
    return rows


if __name__ == "__main__":
    # Self-reported record: 500,000+ hands at about 4 bb/100.
    # The SD is unknown (the database was lost), so show a plausible range.
    print(f"{'SD':>5} {'SE':>6} {'95% CI':>18} {'P(true wr > 0)':>16}")
    for row in sensitivity_table(4.0, 500_000, [70, 80, 90, 100, 110, 120, 130]):
        print(f"{row['sd_bb100']:>5.0f} {row['se_bb100']:>6.2f} "
              f"[{row['ci_low']:>6.2f}, {row['ci_high']:>6.2f}] "
              f"{row['p_true_winner']:>15.4f}")
