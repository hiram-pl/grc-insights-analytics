-- Open rate per send day, with how many emails went out that day.
-- Rate = SUM(openers) / SUM(recipients), never an average of per-post rates.
SELECT
    send_day,
    batch_size,
    MAX(recipients)                                   AS recipients,
    ROUND(SUM(unique_openers) / SUM(recipients), 3)   AS open_rate
FROM email_posts
GROUP BY send_day, batch_size
ORDER BY send_day;
