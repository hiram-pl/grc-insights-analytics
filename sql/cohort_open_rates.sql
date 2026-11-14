-- Fatigue or list composition? Open rate per send quarter, split by subscriber cohort
-- (quarter of each subscriber's first Insights email).
-- If open rates fall WITHIN each cohort, the decline is fatigue. If each cohort holds
-- steady but newer, weaker cohorts make up more of the list, it's composition.
-- share = this cohort's fraction of that quarter's deliveries.
SELECT
    send_quarter,
    cohort,
    COUNT(DISTINCT sub_id)                                              AS subscribers,
    COUNT(*)                                                            AS deliveries,
    ROUND(COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY send_quarter), 3) AS share,
    ROUND(AVG(opened::INTEGER), 3)                                      AS open_rate
FROM sub_email_history
GROUP BY send_quarter, cohort
ORDER BY send_quarter, cohort;
