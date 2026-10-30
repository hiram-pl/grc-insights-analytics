-- List size over time (recipients per send). Flat = no net subscriber growth.
SELECT
    date_trunc('month', emailed_at)   AS month,
    MAX(recipients)                   AS recipients,
    COUNT(*)                          AS emails_sent
FROM email_posts
GROUP BY 1
ORDER BY 1;
