"""
Monte Carlo simulation of poker careers.

Each simulated career is a sequence of 100-hand blocks. The result of each
block is drawn from a distribution with mean `wr` and standard deviation `sd`
(both in bb/100). Two choices for the block distribution:

- "normal": the standard textbook assumption
- "t":      a Student-t with `df` degrees of freedom, rescaled to the SAME sd.
            Same average and same volatility, but fatter tails, so rare
            extreme blocks happen more often. This is the Taleb question:
            does the conclusion survive if the bell curve is wrong?

The metrics mirror what a trading desk tracks for a strategy:
- final observed win rate
- maximum drawdown (largest peak-to-trough fall, in big blinds)
- longest time under water (longest stretch, in hands, without a new high)
"""

from __future__ import annotations

import numpy as np

BLOCK = 100  # hands per simulated block


def simulate_blocks(wr: float, sd: float, hands: int, n_careers: int,
                    dist: str = "normal", df: float = 3.0,
                    seed: int | None = 42) -> np.ndarray:
    """Return an array of shape (n_careers, hands // 100) of block results in bb."""
    rng = np.random.default_rng(seed)
    n_blocks = hands // BLOCK
    shape = (n_careers, n_blocks)
    if dist == "normal":
        return rng.normal(wr, sd, size=shape)
    if dist == "t":
        if df <= 2:
            raise ValueError("df must be > 2 for the variance to exist")
        # A standard t(df) has variance df/(df-2); rescale to unit variance.
        scale = sd / np.sqrt(df / (df - 2))
        return wr + scale * rng.standard_t(df, size=shape)
    raise ValueError("dist must be 'normal' or 't'")


def career_paths(blocks: np.ndarray) -> np.ndarray:
    """Cumulative winnings in bb, starting from 0, shape (n_careers, n_blocks + 1)."""
    zeros = np.zeros((blocks.shape[0], 1))
    return np.hstack([zeros, np.cumsum(blocks, axis=1)])


def max_drawdown(paths: np.ndarray) -> np.ndarray:
    """Largest peak-to-trough fall for each career, in bb (a positive number)."""
    running_peak = np.maximum.accumulate(paths, axis=1)
    return (running_peak - paths).max(axis=1)


def longest_underwater(paths: np.ndarray) -> np.ndarray:
    """
    Longest stretch without a new all-time high, in hands, for each career.
    Poker players call this a "break-even stretch"; traders call it time under water.
    """
    running_peak = np.maximum.accumulate(paths, axis=1)
    below = paths < running_peak  # True while under water
    longest = np.zeros(paths.shape[0], dtype=int)
    current = np.zeros(paths.shape[0], dtype=int)
    for col in range(below.shape[1]):
        current = np.where(below[:, col], current + 1, 0)
        longest = np.maximum(longest, current)
    return longest * BLOCK


def summarize(wr: float, sd: float, hands: int, n_careers: int = 2000,
              dist: str = "normal", df: float = 3.0, seed: int | None = 42) -> dict:
    """Run a simulation and return the headline numbers."""
    blocks = simulate_blocks(wr, sd, hands, n_careers, dist, df, seed)
    paths = career_paths(blocks)
    observed_wr = blocks.mean(axis=1)
    dd = max_drawdown(paths)
    uw = longest_underwater(paths)
    pct = lambda a, q: float(np.percentile(a, q))
    return {
        "dist": dist,
        "observed_wr_p5": pct(observed_wr, 5),
        "observed_wr_p95": pct(observed_wr, 95),
        "share_losing_careers": float((observed_wr < 0).mean()),
        "max_drawdown_median_bb": pct(dd, 50),
        "max_drawdown_p95_bb": pct(dd, 95),
        "underwater_median_hands": pct(uw, 50),
        "underwater_p95_hands": pct(uw, 95),
        "paths": paths,
        "drawdowns": dd,
        "underwater": uw,
        "observed_wr": observed_wr,
    }


if __name__ == "__main__":
    for d in ("normal", "t"):
        s = summarize(wr=4.0, sd=100.0, hands=500_000, dist=d)
        print(f"\n[{d}] true wr 4 bb/100, sd 100, 500k hands, 2,000 careers")
        print(f"  observed wr, 90% of careers: {s['observed_wr_p5']:.2f} to {s['observed_wr_p95']:.2f} bb/100")
        print(f"  max drawdown: median {s['max_drawdown_median_bb']:,.0f} bb, "
              f"95th pct {s['max_drawdown_p95_bb']:,.0f} bb")
        print(f"  longest break-even stretch: median {s['underwater_median_hands']:,.0f} hands, "
              f"95th pct {s['underwater_p95_hands']:,.0f} hands")
