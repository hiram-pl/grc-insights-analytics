-- Fatigue curve: open rate by how many Insights emails the subscriber had already received.
-- Split by send quarter so calendar-wide effects (e.g. inbox privacy changes) don't drive it.
SELECT
    send_quarter,
    CASE WHEN prior_emails < 25 THEN '0-24'
         WHEN prior_emails < 50 THEN '25-49'
         ELSE '50+' END                  AS emails_already_received,
    COUNT(DISTINCT sub_id)               AS subscribers,
    COUNT(*)                             AS deliveries,
    ROUND(AVG(opened::INTEGER), 3)       AS open_rate
FROM sub_email_history
GROUP BY ALL
ORDER BY send_quarter, emails_already_received;
