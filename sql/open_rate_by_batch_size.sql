-- Do crowded send days get lower open rates?
-- Restricted to Oct 2025+ so all groups come from the same era of the list.
SELECT
    CASE WHEN batch_size = 1 THEN '1 (solo)'
         WHEN batch_size <= 4 THEN '2-4'
         ELSE '5+' END                                AS emails_that_day,
    COUNT(*)                                          AS posts,
    COUNT(DISTINCT send_day)                          AS send_days,
    ROUND(SUM(unique_openers) / SUM(recipients), 3)   AS open_rate
FROM email_posts
WHERE emailed_at >= TIMESTAMPTZ '2025-10-01'
GROUP BY 1
ORDER BY 1;
