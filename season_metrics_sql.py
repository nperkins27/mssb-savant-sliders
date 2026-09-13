"""Season metric queries, vendored from ProjectRio-web app/season_metrics_db.py
(https://github.com/ProjectRio/ProjectRio-web/pull/154).

Copied mechanically: the SQL text is unchanged except that SQLAlchemy's
:name bind parameters are written as psycopg's %(name)s. Keep it in step with
upstream; season_metrics.py documents the definitions.

NOTE: includes the special-catches column and RUNS_SQL for the three per-9
metrics, which are not pushed to the PR yet.
"""

# S9 Superstars Off is typed 'League' rather than 'Season', so it cannot be
# found by the discovery rule below. It is the only main-line season that
# needs naming explicitly.
SEASON_ID_EXCEPTIONS = (74,)

# Main-line Stars Off seasons, discoverable without a maintained list.
# tag_set.name_lowercase strips punctuation, so matching names that END in
# 'superstarsoff' excludes the Hazards / Mega / Randoms variants without
# naming them, and type='Season' excludes tournaments in the same window.
SEASON_DISCOVERY_SQL = '''
    SELECT id
    FROM tag_set
    WHERE (
            type = 'Season'
            AND (name_lowercase LIKE '%%superstarsoff'
                 OR name_lowercase LIKE 'starsoffseason%%')
            AND name_lowercase NOT LIKE 'practice%%'
          )
       OR id = ANY(%(exceptions)s)
'''

# Order of the numerator/denominator pairs returned by cAGGREGATE_SQL for each
# role. Position is the contract between the SQL and Python -- keep in step.
BATTING_ORDER = (
    'bat_barrel_pct',
    'bat_chase_pct',
    'bat_whiff_pct',
    'bat_ozone_contact_pct',
    'bat_k_pct',
    'bat_charge_timing_pct',
    'bat_slap_timing_pct',
    'bat_charge_down_input_pct',
)

PITCHING_ORDER = (
    'pitch_barrels_allowed_pct',
    'pitch_whiff_pct',
    'pitch_k_pct',
    'pitch_hr_allowed_pct',
    'pitch_special_catches_per_9',
)

# One pass over the season's events, producing every numerator and denominator
# for both roles. Batting fills all eight pairs; pitching fills five and pads
# the rest with NULL so the two halves can be UNIONed. The fifth pitching pair
# is special catches, whose denominator (outs recorded on defense) is NULL here
# and filled in from cRUNS_SQL, the same outs the runs-against rate uses.
#
# Enum values: result_of_ab 1 strikeout / 2 walk / 3 HBP / 10 HR (1-16 is the
# decodable range, so "not none" is `BETWEEN 1 AND 16`); 5 caught, 6 caught
# line drive, 14 sac fly and 16 foul catch are the outs made by catching the
# ball. type_of_swing 1 slap, 2 charge. type_of_contact 1/2/3 are the barrel
# values out of 0-4. input_direction_stick 4/5/6 are down, down-left,
# down-right. fielding_summary.action 2 is a sliding (diving) play and 3 a
# wall jump; jump = 1 is a jump. A special catch is a catch made with any of
# the three.
AGGREGATE_SQL = '''
WITH sg AS (
    SELECT DISTINCT gh.game_id
    FROM game_history gh
    WHERE gh.tag_set_id = %(tag_set_id)s
      AND gh.game_id IS NOT NULL
),
ev AS MATERIALIZED (
    SELECT
        CASE WHEN e.half_inning = 0 THEN g.away_player_id ELSE g.home_player_id END AS batter_user,
        CASE WHEN e.half_inning = 0 THEN g.home_player_id ELSE g.away_player_id END AS pitcher_user,
        ch.name_lowercase AS batter_char,
        e.result_of_ab,
        ps.type_of_swing,
        ps.in_strikezone,
        ps.contact_summary_id,
        cs.type_of_contact,
        cs.frame_of_swing_upon_contact AS frame,
        cs.input_direction_stick AS stick,
        fs.action AS field_action,
        fs.jump AS field_jump
    FROM sg
    JOIN game g ON g.game_id = sg.game_id
    JOIN event e ON e.game_id = sg.game_id
    LEFT JOIN pitch_summary ps ON ps.id = e.pitch_summary_id
    LEFT JOIN contact_summary cs ON cs.id = ps.contact_summary_id
    LEFT JOIN fielding_summary fs ON fs.id = cs.fielding_summary_id
    LEFT JOIN character_game_summary bcgs ON bcgs.id = e.batter_id
    LEFT JOIN character ch ON ch.char_id = bcgs.char_id
)
SELECT 'bat' AS role, batter_user AS user_id,
    COUNT(*) FILTER (WHERE contact_summary_id IS NOT NULL AND type_of_contact IN (1,2,3))            AS n1,
    COUNT(*) FILTER (WHERE contact_summary_id IS NOT NULL AND type_of_contact IN (0,1,2,3,4))        AS d1,
    COUNT(*) FILTER (WHERE in_strikezone IS FALSE AND type_of_swing IS NOT NULL AND type_of_swing <> 0) AS n2,
    COUNT(*) FILTER (WHERE in_strikezone IS FALSE)                                                   AS d2,
    COUNT(*) FILTER (WHERE type_of_swing IS NOT NULL AND type_of_swing <> 0 AND contact_summary_id IS NULL) AS n3,
    COUNT(*) FILTER (WHERE type_of_swing IS NOT NULL AND type_of_swing <> 0)                         AS d3,
    COUNT(*) FILTER (WHERE in_strikezone IS FALSE AND type_of_swing IS NOT NULL AND type_of_swing <> 0
                       AND contact_summary_id IS NOT NULL)                                           AS n4,
    COUNT(*) FILTER (WHERE in_strikezone IS FALSE AND type_of_swing IS NOT NULL AND type_of_swing <> 0) AS d4,
    COUNT(*) FILTER (WHERE result_of_ab = 1)                                                         AS n5,
    COUNT(*) FILTER (WHERE result_of_ab BETWEEN 1 AND 16)                                            AS d5,
    COUNT(*) FILTER (WHERE type_of_swing = 2 AND batter_char = ANY(%(charge_chars)s)
                       AND frame IN (7,8,9))                                                         AS n6,
    COUNT(*) FILTER (WHERE type_of_swing = 2 AND batter_char = ANY(%(charge_chars)s)
                       AND frame BETWEEN 2 AND 10)                                                   AS d6,
    COUNT(*) FILTER (WHERE type_of_swing = 1 AND frame IN (3,4,5))                                   AS n7,
    COUNT(*) FILTER (WHERE type_of_swing = 1 AND frame BETWEEN 2 AND 10)                             AS d7,
    COUNT(*) FILTER (WHERE type_of_swing = 2 AND contact_summary_id IS NOT NULL
                       AND batter_char = ANY(%(power_chars)s) AND stick IN (4,5,6))                     AS n8,
    COUNT(*) FILTER (WHERE type_of_swing = 2 AND contact_summary_id IS NOT NULL
                       AND batter_char = ANY(%(power_chars)s))                                          AS d8
FROM ev
WHERE batter_user IS NOT NULL
GROUP BY batter_user

UNION ALL

SELECT 'pitch', pitcher_user,
    COUNT(*) FILTER (WHERE contact_summary_id IS NOT NULL AND type_of_contact IN (1,2,3))            AS n1,
    COUNT(*) FILTER (WHERE contact_summary_id IS NOT NULL AND type_of_contact IN (0,1,2,3,4))        AS d1,
    COUNT(*) FILTER (WHERE type_of_swing IS NOT NULL AND type_of_swing <> 0 AND contact_summary_id IS NULL) AS n2,
    COUNT(*) FILTER (WHERE type_of_swing IS NOT NULL AND type_of_swing <> 0)                         AS d2,
    COUNT(*) FILTER (WHERE result_of_ab = 1)                                                         AS n3,
    COUNT(*) FILTER (WHERE result_of_ab BETWEEN 1 AND 16)                                            AS d3,
    COUNT(*) FILTER (WHERE result_of_ab = 10 AND batter_char = ANY(%(power_chars)s))                    AS n4,
    COUNT(*) FILTER (WHERE result_of_ab BETWEEN 1 AND 16 AND result_of_ab NOT IN (2,3)
                       AND batter_char = ANY(%(power_chars)s))                                          AS d4,
    COUNT(*) FILTER (WHERE result_of_ab IN (5,6,14,16)
                       AND (field_action IN (2,3) OR field_jump = 1))                                AS n5,
    NULL AS d5,
    NULL, NULL, NULL, NULL, NULL, NULL
FROM ev
WHERE pitcher_user IS NOT NULL
GROUP BY pitcher_user
'''

# Distinct games each player appeared in, for the shared 10-game floor and for
# the gen_games_played metric. Note this is NOT the same count the ELO formula
# uses: a player can appear in a game that has no rated game_history row.
GAMES_SQL = '''
WITH sg AS (
    SELECT DISTINCT gh.game_id
    FROM game_history gh
    WHERE gh.tag_set_id = %(tag_set_id)s
      AND gh.game_id IS NOT NULL
)
SELECT x.user_id, COUNT(DISTINCT x.game_id) AS games
FROM (
    SELECT sg.game_id, g.away_player_id AS user_id FROM sg JOIN game g ON g.game_id = sg.game_id
    UNION ALL
    SELECT sg.game_id, g.home_player_id            FROM sg JOIN game g ON g.game_id = sg.game_id
) x
WHERE x.user_id IS NOT NULL
GROUP BY x.user_id
'''

# Inputs for the adjusted ELO formula. Rating is the result ELO on the most
# recent rated game of the season; wins and games come from that same sequence.
ELO_SQL = '''
WITH pl AS (
    SELECT gh.id,
           gh.date_created,
           cu.user_id,
           (gh.winner_comm_user_id = cu.id) AS won,
           CASE WHEN gh.winner_comm_user_id = cu.id
                THEN gh.winner_result_elo ELSE gh.loser_result_elo END AS result_elo
    FROM game_history gh
    JOIN community_user cu
      ON cu.id IN (gh.winner_comm_user_id, gh.loser_comm_user_id)
    WHERE gh.tag_set_id = %(tag_set_id)s
),
agg AS (
    SELECT user_id, COUNT(*) AS games, COUNT(*) FILTER (WHERE won) AS wins
    FROM pl GROUP BY user_id
),
latest AS (
    SELECT DISTINCT ON (user_id) user_id, result_elo
    FROM pl ORDER BY user_id, date_created DESC, id DESC
)
SELECT a.user_id, a.wins, a.games, l.result_elo
FROM agg a JOIN latest l ON l.user_id = a.user_id
'''

# Runs and outs for the per-9 metrics, from the per-character game summaries.
# A team's summed runs_allowed is the runs its opponent scored (it matches the
# opponent's final score in 99.3% of S14 team-games), and its summed
# outs_pitched is the outs it recorded on defense. So for each player:
#   runs against / 9 = 27 * own runs_allowed      / own outs_pitched
#   runs / 9         = 27 * opponent runs_allowed / opponent outs_pitched
RUNS_SQL = '''
WITH sg AS (
    SELECT DISTINCT gh.game_id
    FROM game_history gh
    WHERE gh.tag_set_id = %(tag_set_id)s
      AND gh.game_id IS NOT NULL
),
team AS (
    SELECT c.game_id, c.team_id, c.user_id,
           SUM(c.runs_allowed) AS runs_allowed,
           SUM(c.outs_pitched) AS outs
    FROM sg
    JOIN character_game_summary c ON c.game_id = sg.game_id
    GROUP BY c.game_id, c.team_id, c.user_id
)
SELECT own.user_id,
       SUM(opp.runs_allowed) AS runs_scored,
       SUM(opp.outs)         AS outs_batting,
       SUM(own.runs_allowed) AS runs_allowed,
       SUM(own.outs)         AS outs_fielding
FROM team own
JOIN team opp ON opp.game_id = own.game_id AND opp.team_id <> own.team_id
WHERE own.user_id IS NOT NULL
GROUP BY own.user_id
'''
