-- Open rate by quarter for both email channels, side by side.
-- Both rates are SUM(openers) / SUM(delivered), never an average of per-email rates.
WITH substack AS (
    SELECT date_trunc('quarter', emailed_at)::DATE              AS quarter,
           SUM(unique_openers) / SUM(recipients)                AS open_rate,
           COUNT(*)                                             AS emails
    FROM email_posts
    GROUP BY 1
),
mailchimp AS (
    SELECT date_trunc('quarter', sent_at)::DATE                 AS quarter,
           SUM(unique_opens) / SUM(delivered)                   AS open_rate,
           COUNT(*)                                             AS emails
    FROM mc_campaigns
    GROUP BY 1
)
SELECT
    quarter,
    ROUND(m.open_rate, 3)  AS mailchimp_open_rate,
    m.emails               AS mailchimp_emails,
    ROUND(s.open_rate, 3)  AS substack_open_rate,
    s.emails               AS substack_emails
FROM mailchimp m
FULL OUTER JOIN substack s USING (quarter)
WHERE quarter >= DATE '2024-10-01'
ORDER BY quarter;
