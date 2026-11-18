"""
Load poker hand histories in the PHH format into a SQLite database.

PHH (Poker Hand History) is a TOML-based format from the University of Toronto
Computer Poker Research Group. One .phh file holds one hand; a .phhs file holds
many hands, each in its own [table]. Spec: https://phh.readthedocs.io

Usage
-----
    python -m src.phh_loader path/to/pluribus --db data/poker.db

The loader walks the folder recursively, so pointing it at the whole Pluribus
folder is enough. It creates three tables (see sql/schema.sql):

    hands         one row per hand
    hand_players  one row per player per hand, with net result in chips and bb
    actions       one row per action (deals, bets, calls, folds, showdowns)

Results come from the `finishing_stacks` field. Hands without it are kept but
flagged (has_result = 0); pass --replay-missing to try replaying them with the
optional `pokerkit` package instead.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pip install tomli

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"


# ---------------------------------------------------------------- positions

def position_name(seat_index: int, n_players: int) -> str:
    """
    PHH orders players by position, not by physical seat: p1 is the small
    blind, p2 the big blind, and the last player is the button.
    """
    if n_players < 3:
        return f"P{seat_index}"  # heads-up conventions vary; keep it neutral
    if seat_index == 1:
        return "SB"
    if seat_index == 2:
        return "BB"
    from_button = n_players - seat_index  # 0 = button, 1 = cutoff, ...
    named = {0: "BTN", 1: "CO", 2: "HJ"}
    if from_button in named and seat_index > 2:
        return named[from_button]
    early = seat_index - 3  # 0 = UTG
    return "UTG" if early == 0 else f"UTG+{early}"


# ---------------------------------------------------------------- actions

def parse_action(text: str) -> dict:
    """
    Turn one PHH action string into a dict.

    Examples
        "d dh p1 AsKs"  -> dealer deals hole cards to player 1
        "d db 7h8h9h"   -> dealer deals board cards (flop, turn, river)
        "p3 cbr 300"    -> player 3 completes/bets/raises TO 300
        "p2 cc"         -> player 2 checks or calls
        "p1 f"          -> player 1 folds
        "p2 sm AsKs"    -> player 2 shows (or mucks) at showdown
    """
    clean = text.split("#", 1)[0].strip()  # drop inline comments
    parts = clean.split()
    if not parts:
        raise ValueError(f"empty action: {text!r}")
    out = {"actor": parts[0], "seat_index": None, "action": None,
           "amount": None, "cards": None}
    if parts[0] == "d":
        out["action"] = parts[1]
        if parts[1] == "dh":            # d dh p1 AsKs
            out["seat_index"] = int(parts[2][1:])
            out["cards"] = parts[3] if len(parts) > 3 else None
        elif len(parts) > 2:            # d db 7h8h9h
            out["cards"] = parts[2]
        return out
    if not parts[0].startswith("p"):
        raise ValueError(f"unknown actor in action: {text!r}")
    out["seat_index"] = int(parts[0][1:])
    out["action"] = parts[1]
    if parts[1] == "cbr" and len(parts) > 2:
        out["amount"] = float(parts[2])
    elif len(parts) > 2:
        out["cards"] = parts[2]
    return out


# ---------------------------------------------------------------- files

def iter_hands(path: Path):
    """Yield (hand_key, hand_dict) for every hand in a .phh or .phhs file."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    if "actions" in data:  # single-hand .phh file
        yield str(data.get("hand", path.stem)), data
        return
    for key, value in data.items():  # multi-hand .phhs file: one table per hand
        if isinstance(value, dict) and "actions" in value:
            yield str(value.get("hand", key)), value


def replay_final_stacks(path: Path):
    """Optional fallback: replay a single-hand file with pokerkit."""
    try:
        from pokerkit import HandHistory
        with open(path, "rb") as fh:
            hh = HandHistory.load(fh)
        state = None
        for state in hh:
            pass
        return list(state.stacks) if state is not None else None
    except Exception:  # missing package or unparseable hand
        return None


def _natural_key(path: Path):
    """Sort '2.phh' before '10.phh' (plain string sorting would not)."""
    import re
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(path))]


def find_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted((p for p in root.rglob("*") if p.suffix in (".phh", ".phhs")),
                  key=_natural_key)


# ---------------------------------------------------------------- loading

def load(root: Path, db_path: Path, replay_missing: bool = False) -> dict:
    files = find_files(root)
    if not files:
        raise SystemExit(f"No .phh or .phhs files found under {root}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA_PATH.read_text())

    stats = {"files": len(files), "hands": 0, "with_result": 0,
             "replayed": 0, "errors": 0}
    hand_rows, player_rows, action_rows = [], [], []
    hand_id = 0

    for path in files:
        try:
            hands = list(iter_hands(path))
        except Exception as exc:
            stats["errors"] += 1
            print(f"  skipped {path.name}: {exc}", file=sys.stderr)
            continue

        for hand_key, h in hands:
            try:
                starting = [float(s) for s in h["starting_stacks"]]
                n = len(starting)
                big_blind = float(max(h.get("blinds_or_straddles", [0]) or [0])) or None
                names = h.get("players") or [f"p{i}" for i in range(1, n + 1)]
                finishing = h.get("finishing_stacks")
                if finishing is None and replay_missing and path.suffix == ".phh":
                    finishing = replay_final_stacks(path)
                    if finishing is not None:
                        stats["replayed"] += 1
                parsed = [parse_action(a) for a in h["actions"]]
            except Exception as exc:
                stats["errors"] += 1
                print(f"  skipped hand {hand_key} in {path.name}: {exc}", file=sys.stderr)
                continue

            hand_id += 1
            has_result = finishing is not None
            hand_rows.append((hand_id, str(path), hand_key, path.parent.name,
                              h.get("variant"), n, big_blind, int(has_result)))

            for i in range(n):
                net = (float(finishing[i]) - starting[i]) if has_result else None
                net_bb = (net / big_blind) if (net is not None and big_blind) else None
                player_rows.append((hand_id, i + 1, position_name(i + 1, n),
                                    names[i] if i < len(names) else f"p{i + 1}",
                                    starting[i],
                                    float(finishing[i]) if has_result else None,
                                    net, net_bb))

            street = 0  # 0 preflop, 1 flop, 2 turn, 3 river
            for seq, a in enumerate(parsed):
                if a["actor"] == "d" and a["action"] == "db":
                    street += 1
                action_rows.append((hand_id, seq, street, a["actor"], a["seat_index"],
                                    a["action"], a["amount"], a["cards"]))

            stats["hands"] += 1
            stats["with_result"] += int(has_result)

    with con:
        con.executemany("INSERT INTO hands VALUES (?,?,?,?,?,?,?,?)", hand_rows)
        con.executemany("INSERT INTO hand_players VALUES (?,?,?,?,?,?,?,?)", player_rows)
        con.executemany("INSERT INTO actions VALUES (?,?,?,?,?,?,?,?)", action_rows)
    con.close()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Load PHH hand histories into SQLite.")
    parser.add_argument("source", type=Path, help="a .phh/.phhs file or a folder of them")
    parser.add_argument("--db", type=Path, default=Path("data/poker.db"))
    parser.add_argument("--replay-missing", action="store_true",
                        help="replay hands lacking finishing_stacks with pokerkit")
    args = parser.parse_args()
    stats = load(args.source, args.db, args.replay_missing)
    print(f"Loaded {stats['hands']:,} hands from {stats['files']:,} files into {args.db}")
    print(f"  with a result: {stats['with_result']:,}   replayed: {stats['replayed']:,}   "
          f"errors: {stats['errors']:,}")


if __name__ == "__main__":
    main()
