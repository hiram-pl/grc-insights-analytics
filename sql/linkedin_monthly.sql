-- LinkedIn company page, month by month. Engagement rate = SUM(engagements) / SUM(impressions).
WITH monthly AS (
    SELECT date_trunc('month', date)::DATE   AS month,
           SUM(impressions)::INTEGER         AS impressions,
           SUM(engagements)                  AS engagements,
           SUM(clicks)                       AS clicks,
           SUM(new_followers)::INTEGER       AS new_followers,
           SUM(page_views)::INTEGER          AS page_views
    FROM li_daily
    GROUP BY 1
),
posts AS (
    SELECT date_trunc('month', created_at)::DATE           AS month,
           COUNT(*)                                        AS posts,
           COUNT(*) FILTER (WHERE promotes_insights)       AS insights_posts
    FROM li_posts
    GROUP BY 1
)
SELECT
    m.month,
    COALESCE(p.posts, 0)                             AS posts,
    COALESCE(p.insights_posts, 0)                    AS insights_posts,
    m.impressions,
    ROUND(m.engagements / NULLIF(m.impressions, 0), 3) AS engagement_rate,
    m.new_followers,
    m.page_views
FROM monthly m
LEFT JOIN posts p USING (month)
ORDER BY m.month;
