"""
Tests. Run with either:
    python -m pytest tests/
    python -m tests.test_project
The fixtures in tests/fixtures/ are hand-made synthetic hands, not real data.
"""

import math
import sqlite3
import tempfile
from pathlib import Path

from src import bankroll, winrate
from src.analyze_pluribus import load_queries, run
from src.phh_loader import load, parse_action, position_name

FIXTURES = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------ statistics

def test_standard_error_matches_hand_calculation():
    # 500,000 hands = 5,000 blocks of 100; sqrt(5000) = 70.71
    assert math.isclose(winrate.standard_error(100, 500_000), 100 / math.sqrt(5000))


def test_interval_is_symmetric_and_95_percent():
    low, high = winrate.confidence_interval(4, 100, 500_000)
    assert math.isclose((low + high) / 2, 4)
    assert math.isclose(high - 4, 1.959964 * 100 / math.sqrt(5000), rel_tol=1e-5)


def test_hands_needed_inverts_the_interval():
    h = winrate.hands_needed(sd_bb100=100, margin_bb100=2)
    low, high = winrate.confidence_interval(0, 100, h)
    assert high <= 2 + 1e-9


def test_kelly_bankroll_gives_exp_minus_two_ruin():
    b = bankroll.kelly_bankroll(4, 100)
    assert math.isclose(b, 2500)
    assert math.isclose(bankroll.risk_of_ruin(4, 100, b), math.exp(-2))


def test_losing_player_always_goes_broke():
    assert bankroll.risk_of_ruin(-1, 100, 10_000) == 1.0


def test_edge_is_invisible_in_short_windows():
    # A true 4 bb/100 winner is barely better than a coin flip over 100 hands.
    assert 0.51 < winrate.prob_up_after(4, 100, 100) < 0.52
    assert winrate.prob_up_after(4, 100, 500_000) > 0.99


def test_uncertainty_raises_risk_of_ruin_jensen():
    se = winrate.standard_error(100, 500_000)
    for buyins in (20, 30, 50, 100):
        b = buyins * 100
        assert bankroll.expected_risk_of_ruin(4, se, 100, b) > bankroll.risk_of_ruin(4, 100, b)


def test_absorbing_barrier_freezes_ruined_paths():
    import numpy as np
    paths = np.array([[0, -5, -12, 3, 8],     # hits -10 at step 2, must stay there
                      [0, 2, 4, 6, 8]])       # never ruined
    absorbed, ruined = bankroll.absorb(paths, 10)
    assert ruined.tolist() == [True, False]
    assert absorbed[0].tolist() == [0, -5, -10, -10, -10]
    assert absorbed[1].tolist() == [0, 2, 4, 6, 8]


def test_move_down_rule_steps_down_then_runs_out_of_stakes():
    import numpy as np
    from src.move_down import run_rule
    # Start 5,000 bb (50 buy-ins). Results are in bb of the stake being played.
    blocks = np.array([[-2100, -2000, -1000, -3000, 99999]], dtype=float)
    r = run_rule(blocks)  # two stakes below, ratio 2
    # 2,900 < 3,000 -> down to half stakes; -1,000 -> 1,900; -500 -> 1,400 < 1,500
    # -> quarter stakes; -750 -> 650 < 750 (30 buy-ins of the lowest stake) -> ruined.
    assert r["ruined"].tolist() == [True]
    assert r["final_bankroll_bb"][0] == 650   # frozen once ruined


def test_move_down_rule_moves_back_up():
    import numpy as np
    from src.move_down import run_rule
    blocks = np.array([[-2100, 4400, 0]], dtype=float)
    r = run_rule(blocks)
    # 2,900 -> half stakes; +2,200 -> 5,100 >= 50 buy-ins of the starting stake -> back up.
    assert not r["ruined"][0]
    assert r["blocks_below"][0] == 1


# ------------------------------------------------------------ parsing

def test_parse_actions():
    assert parse_action("p3 cbr 300")["amount"] == 300
    assert parse_action("p2 cc")["action"] == "cc"
    deal = parse_action("d dh p1 AsKs")
    assert deal["seat_index"] == 1 and deal["cards"] == "AsKs"
    board = parse_action("d db 7h8h9h")
    assert board["action"] == "db" and board["cards"] == "7h8h9h"
    assert parse_action("p1 f # tanked, then folded")["action"] == "f"


def test_positions_six_max():
    assert [position_name(i, 6) for i in range(1, 7)] == ["SB", "BB", "UTG", "HJ", "CO", "BTN"]


# ------------------------------------------------------------ loader + SQL

def _load_fixture_db():
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    stats = load(FIXTURES, tmp)
    return stats, sqlite3.connect(tmp)


def test_loader_counts_and_flags_missing_results():
    stats, con = _load_fixture_db()
    assert stats["hands"] == 3
    assert stats["with_result"] == 2
    q = load_queries()
    check = run(con, q["data_check"])[0]
    assert check["hands_not_zero_sum"] == 0


def test_net_results_in_big_blinds():
    _, con = _load_fixture_db()
    rows = con.execute(
        "SELECT h.hand_key, hp.net_bb FROM hand_players hp JOIN hands h USING (hand_id) "
        "WHERE hp.player = 'Pluribus' ORDER BY h.hand_key").fetchall()
    assert rows == [("1", 3.0), ("2", -0.5), ("3", None)]


def test_vpip_rule_for_big_blind():
    _, con = _load_fixture_db()
    q = load_queries()
    out = {r["who"]: r for r in run(con, q["vpip_pfr"])}
    # Pluribus raised preflop in hands 1 and 3, folded in hand 2.
    assert out["Pluribus"]["vpip_pct"] == 66.7
    assert out["Pluribus"]["pfr_pct"] == 66.7
    # Humans: BB calls a raise (hands 1, 3) and UTG limps (hand 2) = 3 of 15.
    # The BB check in hand 2 must NOT count.
    assert out["Humans (pooled)"]["vpip_pct"] == 20.0
    assert out["Humans (pooled)"]["pfr_pct"] == 0.0


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\nAll {len(tests)} tests passed.")
