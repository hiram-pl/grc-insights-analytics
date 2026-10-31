-- Which Mailchimp campaigns sent readers to Insights, and how many clicks each.
-- Clicks are total clicks (not unique people) and can include security-scanner clicks.
SELECT
    c.sent_at::DATE                      AS sent_on,
    COALESCE(c.title, l.campaign_slug)   AS campaign,
    c.audience,
    c.delivered,
    SUM(l.clicks)::INTEGER               AS insights_clicks
FROM mc_link_clicks l
LEFT JOIN mc_campaign_ids i ON i.campaign_num = l.campaign_num
LEFT JOIN mc_campaigns c    ON c.campaign_uid = i.campaign_uid
WHERE l.is_insights
GROUP BY ALL
ORDER BY sent_on NULLS LAST;
