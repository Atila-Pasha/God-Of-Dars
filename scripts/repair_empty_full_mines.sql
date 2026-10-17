-- One-time repair for mines left at the 12-hour cap by the old daily-cycle
-- logic after their owner had already collected all cargo. Mines with cargo
-- or mine loot taken since the last collection are deliberately untouched.
BEGIN;

CREATE TEMP TABLE empty_full_mines ON COMMIT DROP AS
SELECT mine.id, mine.user_id
FROM mines AS mine
CROSS JOIN LATERAL (
    SELECT MAX(tx.created_at) AS last_collection
    FROM transactions AS tx
    WHERE tx.user_id = mine.user_id AND tx.reason = 'MINE_COLLECTION'
) AS history
WHERE mine.daily_produced_minutes >= 720
  AND mine.today_coin = 0
  AND mine.today_diamond = 0
  AND mine.today_banana = 0
  AND history.last_collection IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM attacks AS attack
      WHERE attack.target_id = mine.user_id
        AND (attack.mine_loot_coin > 0 OR attack.mine_loot_diamond > 0)
        AND attack.resolved_at > history.last_collection
  );

SELECT 'mines_to_restart' AS item, COUNT(*) AS value FROM empty_full_mines;
SELECT id, user_id FROM empty_full_mines ORDER BY user_id;

UPDATE mines AS mine
SET daily_produced_minutes = 0,
    last_collected_at = NOW(),
    updated_at = NOW()
FROM empty_full_mines AS stuck
WHERE mine.id = stuck.id;

COMMIT;
