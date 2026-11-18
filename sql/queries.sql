-- Named queries. Each starts with a "-- name: ..." line so Python can run
-- them by name (see src/analyze_pluribus.py). They also run as-is in any
-- SQLite client, e.g. DB Browser for SQLite or `sqlite3 data/poker.db`.
--
-- SQLite has no STDDEV function, so queries return AVG(x) and AVG(x*x);
-- Python turns those into a standard deviation:  sd = sqrt(E[x^2] - E[x]^2).


-- name: data_check
-- Reconciliation, like checking a ledger balances: with no rake, chips are
-- only moved between players, so every hand must sum to zero.
SELECT
    COUNT(*)                                        AS hands,
    SUM(has_result)                                 AS hands_with_result,
    SUM(CASE WHEN ABS(total) > 0.001 THEN 1 ELSE 0 END) AS hands_not_zero_sum
FROM (
    SELECT h.hand_id, h.has_result, COALESCE(SUM(hp.net_chips), 0) AS total
    FROM hands h
    JOIN hand_players hp ON hp.hand_id = h.hand_id
    GROUP BY h.hand_id
);


-- name: player_summary
-- Win rate per player label. Each label appears at most once per hand, so
-- its rows are independent across hands and a normal interval is valid.
SELECT
    player,
    COUNT(*)                AS hands,
    SUM(net_bb)             AS total_bb,
    AVG(net_bb)             AS mean_bb,
    AVG(net_bb * net_bb)    AS mean_sq_bb
FROM hand_players
WHERE net_bb IS NOT NULL
GROUP BY player
ORDER BY hands DESC, player;


-- name: pluribus_by_position
-- Slicing by position: same question, about one sixth of the sample each.
SELECT
    position,
    COUNT(*)                AS hands,
    AVG(net_bb)             AS mean_bb,
    AVG(net_bb * net_bb)    AS mean_sq_bb
FROM hand_players
WHERE player = 'Pluribus' AND net_bb IS NOT NULL
GROUP BY position
ORDER BY CASE position
    WHEN 'UTG' THEN 1 WHEN 'HJ' THEN 2 WHEN 'CO' THEN 3
    WHEN 'BTN' THEN 4 WHEN 'SB' THEN 5 WHEN 'BB' THEN 6 ELSE 7 END;


-- name: vpip_pfr
-- VPIP: share of hands where a player voluntarily put chips in preflop.
-- PFR:  share of hands where a player raised preflop.
-- Subtlety: in PHH, "cc" means check OR call. A big blind who checks when no
-- one raised has not put money in voluntarily, so for the big blind a "cc"
-- only counts if someone raised earlier in the hand.
WITH preflop AS (
    SELECT a.hand_id, a.seq, a.seat_index, a.action, hp.position
    FROM actions a
    JOIN hand_players hp
      ON hp.hand_id = a.hand_id AND hp.seat_index = a.seat_index
    WHERE a.street = 0 AND a.actor <> 'd' AND a.action IN ('cc', 'cbr')
),
per_player_hand AS (
    SELECT
        p.hand_id,
        p.seat_index,
        MAX(CASE
              WHEN p.action = 'cbr' THEN 1
              WHEN p.position = 'BB' AND NOT EXISTS (
                   SELECT 1 FROM actions r
                   WHERE r.hand_id = p.hand_id AND r.street = 0
                     AND r.action = 'cbr' AND r.seq < p.seq) THEN 0
              ELSE 1
            END)                                      AS vpip,
        MAX(CASE WHEN p.action = 'cbr' THEN 1 ELSE 0 END) AS pfr
    FROM preflop p
    GROUP BY p.hand_id, p.seat_index
)
SELECT
    CASE WHEN hp.player = 'Pluribus' THEN 'Pluribus' ELSE 'Humans (pooled)' END AS who,
    COUNT(*)                                               AS player_hands,
    ROUND(100.0 * SUM(COALESCE(v.vpip, 0)) / COUNT(*), 1)  AS vpip_pct,
    ROUND(100.0 * SUM(COALESCE(v.pfr, 0))  / COUNT(*), 1)  AS pfr_pct
FROM hand_players hp
LEFT JOIN per_player_hand v
  ON v.hand_id = hp.hand_id AND v.seat_index = hp.seat_index
GROUP BY who
ORDER BY who DESC;


-- name: pluribus_sequence
-- Pluribus's result hand by hand, in file order, for the cumulative chart.
-- The order changes the shape of the curve, never its end point.
SELECT hp.net_bb
FROM hand_players hp
JOIN hands h ON h.hand_id = hp.hand_id
WHERE hp.player = 'Pluribus' AND hp.net_bb IS NOT NULL
ORDER BY h.hand_id;


-- name: session_results
-- Results per session folder: watch how much they swing.
SELECT
    h.session,
    COUNT(*)                     AS hands,
    ROUND(AVG(hp.net_bb) * 100, 1) AS bb_per_100
FROM hand_players hp
JOIN hands h ON h.hand_id = hp.hand_id
WHERE hp.player = 'Pluribus' AND hp.net_bb IS NOT NULL
GROUP BY h.session
ORDER BY h.session;
