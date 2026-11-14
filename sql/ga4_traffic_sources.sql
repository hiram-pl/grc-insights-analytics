-- Where Insights web visits come from (GA4). UTM-tagged links show up with their
-- utm_source / utm_medium / utm_campaign; everything else is GA4's own classification.
-- engaged_rate = engaged sessions / sessions (engaged = 10s+, 2+ pages, or a key event).
SELECT
    source,
    medium,
    campaign,
    SUM(sessions)::INTEGER                                     AS sessions,
    SUM(new_users)::INTEGER                                    AS new_users,
    SUM(views)::INTEGER                                        AS views,
    ROUND(SUM(engaged_sessions) / NULLIF(SUM(sessions), 0), 2) AS engaged_rate
FROM ga4_traffic_daily
GROUP BY ALL
ORDER BY sessions DESC;
