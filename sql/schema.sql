-- Schema for the hand-history database.
-- Rebuilt from scratch on every load so reruns never double-count hands.

DROP TABLE IF EXISTS actions;
DROP TABLE IF EXISTS hand_players;
DROP TABLE IF EXISTS hands;

-- One row per hand.
CREATE TABLE hands (
    hand_id      INTEGER PRIMARY KEY,
    source_file  TEXT NOT NULL,
    hand_key     TEXT,             -- hand number from the file, or the file name
    session      TEXT,             -- name of the folder the file sits in
    variant      TEXT,             -- 'NT' = no-limit Texas hold'em
    n_players    INTEGER NOT NULL,
    big_blind    REAL,
    has_result   INTEGER NOT NULL  -- 1 if finishing stacks were available
);

-- One row per player per hand. seat_index follows PHH order:
-- 1 = small blind, 2 = big blind, ..., last = button.
CREATE TABLE hand_players (
    hand_id         INTEGER NOT NULL REFERENCES hands(hand_id),
    seat_index      INTEGER NOT NULL,
    position        TEXT NOT NULL,     -- SB, BB, UTG, HJ, CO, BTN
    player          TEXT NOT NULL,
    starting_stack  REAL NOT NULL,
    finishing_stack REAL,
    net_chips       REAL,              -- finishing minus starting stack
    net_bb          REAL,              -- net_chips / big blind
    PRIMARY KEY (hand_id, seat_index)
);

-- One row per action, in order.
CREATE TABLE actions (
    hand_id     INTEGER NOT NULL REFERENCES hands(hand_id),
    seq         INTEGER NOT NULL,      -- 0, 1, 2, ... within the hand
    street      INTEGER NOT NULL,      -- 0 preflop, 1 flop, 2 turn, 3 river
    actor       TEXT NOT NULL,         -- 'd' (dealer) or 'p1', 'p2', ...
    seat_index  INTEGER,               -- player the action belongs to
    action      TEXT NOT NULL,         -- dh, db, cbr, cc, f, sm, ...
    amount      REAL,                  -- for cbr: the total bet/raise size
    cards       TEXT,
    PRIMARY KEY (hand_id, seq)
);

CREATE INDEX idx_players_name ON hand_players(player);
CREATE INDEX idx_actions_street ON actions(hand_id, street, action);
