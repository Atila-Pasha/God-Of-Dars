-- One-time production repair for answers submitted to the same question in
-- multiple groups. Run only after taking a database backup and deploying the
-- cross-group answer lock. Invalid rows remain available for audit.
BEGIN;

CREATE TEMP TABLE group_answer_rank ON COMMIT DROP AS
SELECT
    id,
    user_id,
    ROW_NUMBER() OVER (
        PARTITION BY user_id, question_id ORDER BY answered_at, id
    ) AS attempt_number
FROM answers
WHERE group_id IS NOT NULL;

CREATE TEMP TABLE affected_users ON COMMIT DROP AS
SELECT user_id
FROM group_answer_rank
GROUP BY user_id
HAVING COUNT(*) FILTER (WHERE attempt_number > 1) > 0;

-- Calculate the average after removing cross-group duplicate answers, so the
-- exploit itself cannot inflate the normalization target.
CREATE TEMP TABLE correction_target ON COMMIT DROP AS
WITH corrected_counts AS (
    SELECT
        a.user_id,
        COUNT(*) FILTER (
            WHERE a.is_correct AND a.is_valid
              AND (r.id IS NULL OR r.attempt_number = 1)
        ) AS correct_count
    FROM answers AS a
    LEFT JOIN group_answer_rank AS r ON r.id = a.id
    GROUP BY a.user_id
)
SELECT GREATEST(
    1,
    ROUND(AVG(correct_count) FILTER (WHERE correct_count > 0))::integer
) AS maximum_correct
FROM corrected_counts;

CREATE TEMP TABLE duplicate_answer_ids ON COMMIT DROP AS
SELECT a.id, a.user_id
FROM group_answer_rank AS r
JOIN answers AS a ON a.id = r.id
WHERE r.attempt_number > 1 AND a.is_valid;

CREATE TEMP TABLE excess_correct_ids ON COMMIT DROP AS
SELECT ranked.id, ranked.user_id
FROM (
    SELECT
        a.id,
        a.user_id,
        ROW_NUMBER() OVER (
            PARTITION BY a.user_id ORDER BY a.answered_at, a.id
        ) AS correct_number
    FROM answers AS a
    JOIN affected_users AS u ON u.user_id = a.user_id
    LEFT JOIN group_answer_rank AS r ON r.id = a.id
    WHERE a.is_correct AND a.is_valid
      AND (r.id IS NULL OR r.attempt_number = 1)
) AS ranked
CROSS JOIN correction_target AS target
WHERE ranked.correct_number > target.maximum_correct;

-- This result is saved in the server-side correction log before the update.
SELECT 'target_correct_per_user' AS item, maximum_correct AS value
FROM correction_target;
SELECT 'affected_users' AS item, COUNT(*) AS value FROM affected_users;
SELECT 'duplicate_answers' AS item, COUNT(*) AS value FROM duplicate_answer_ids;
SELECT 'additional_correct_answers' AS item, COUNT(*) AS value
FROM excess_correct_ids;
SELECT id, user_id, 'cross_group_duplicate' AS reason
FROM duplicate_answer_ids
UNION ALL
SELECT id, user_id, 'above_correct_average' AS reason
FROM excess_correct_ids
ORDER BY user_id, id;

UPDATE answers
SET is_valid = false
WHERE id IN (
    SELECT id FROM duplicate_answer_ids
    UNION
    SELECT id FROM excess_correct_ids
);

SELECT
    u.user_id,
    COUNT(a.id) FILTER (WHERE a.is_correct AND a.is_valid) AS correct_after
FROM affected_users AS u
LEFT JOIN answers AS a ON a.user_id = u.user_id
GROUP BY u.user_id
ORDER BY u.user_id;

COMMIT;
