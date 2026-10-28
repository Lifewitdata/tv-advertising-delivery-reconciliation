CREATE VIEW v_visible_airings AS
SELECT l.* FROM airing_logs l CROSS JOIN settings p
WHERE l.aired_at <= p.as_of AND l.ingested_at <= p.as_of;

CREATE VIEW v_canonical_airings AS
WITH variants AS (
    SELECT DISTINCT source_event_id,scheduled_spot_id,station_id,aired_at,duration_seconds,creative_id
    FROM v_visible_airings
), variant_counts AS (
    SELECT source_event_id,COUNT(*) AS variant_count FROM variants GROUP BY source_event_id
), ranked AS (
    SELECT l.*,v.variant_count,
           COUNT(*) OVER (PARTITION BY l.source_event_id) AS raw_record_count,
           ROW_NUMBER() OVER (PARTITION BY l.source_event_id ORDER BY l.ingested_at,l.ingestion_id) AS rn
    FROM v_visible_airings l JOIN variant_counts v ON v.source_event_id=l.source_event_id
)
SELECT * FROM ranked WHERE rn=1;

CREATE VIEW v_airing_review AS
SELECT l.*,s.commitment_id,s.is_makegood,s.scheduled_at,
    CASE
      WHEN l.variant_count>1 THEN 'conflicting_log'
      WHEN s.scheduled_spot_id IS NULL THEN 'unmatched_schedule'
      WHEN c.cancelled=1 THEN 'cancelled_airing'
      WHEN l.station_id<>s.station_id THEN 'wrong_station'
      WHEN l.creative_id<>s.creative_id THEN 'wrong_creative'
      WHEN l.duration_seconds<>s.duration_seconds THEN 'wrong_duration'
      WHEN l.aired_at<s.window_start OR l.aired_at>s.window_end THEN 'off_window'
      ELSE 'qualifying'
    END AS airing_status
FROM v_canonical_airings l
LEFT JOIN scheduled_spots s ON s.scheduled_spot_id=l.scheduled_spot_id
LEFT JOIN commitments c ON c.commitment_id=s.commitment_id;

CREATE VIEW v_slot_delivery AS
SELECT s.scheduled_spot_id,s.commitment_id,s.is_makegood,
       COUNT(a.source_event_id) AS observed_events,
       SUM(CASE WHEN a.airing_status='qualifying' THEN 1 ELSE 0 END) AS qualifying_events,
       MIN(CASE WHEN a.airing_status='qualifying' THEN a.aired_at END) AS first_qualifying_airing
FROM scheduled_spots s LEFT JOIN v_airing_review a ON a.scheduled_spot_id=s.scheduled_spot_id
GROUP BY s.scheduled_spot_id,s.commitment_id,s.is_makegood;

CREATE VIEW v_commitment_delivery AS
WITH delivery AS (
    SELECT commitment_id,SUM(observed_events) AS observed_events,SUM(qualifying_events) AS qualifying_events,
        MAX(CASE WHEN is_makegood=0 AND qualifying_events>0 THEN 1 ELSE 0 END) AS original_delivered,
        MAX(CASE WHEN is_makegood=1 AND qualifying_events>0 THEN 1 ELSE 0 END) AS makegood_delivered,
        MIN(first_qualifying_airing) AS first_qualifying_airing
    FROM v_slot_delivery GROUP BY commitment_id
)
SELECT c.commitment_id,c.booking_line_id,c.cancelled,c.due_at,c.evidence_due_at,
       b.campaign_id,p.advertiser_id,b.station_id,st.market,st.timezone,st.delivery_partner,
       b.daypart,b.duration_seconds,b.unit_rate_cents,
       CASE WHEN c.due_at<=s.as_of AND c.cancelled=0 THEN 1 ELSE 0 END AS due_commitment,
       CASE WHEN c.cancelled=0 AND d.qualifying_events>0 THEN 1 ELSE 0 END AS delivered,
       COALESCE(d.original_delivered,0) AS original_delivered,
       COALESCE(d.makegood_delivered,0) AS makegood_delivered,
       COALESCE(d.observed_events,0) AS observed_events,
       COALESCE(d.qualifying_events,0) AS qualifying_events,d.first_qualifying_airing,
       CASE WHEN c.due_at<=s.as_of AND c.cancelled=0 AND d.qualifying_events>0
            THEN b.unit_rate_cents ELSE 0 END AS expected_billable_cents,
       CASE WHEN c.cancelled=1 THEN 'cancelled'
            WHEN c.due_at>s.as_of THEN 'not_due'
            WHEN d.original_delivered=1 THEN 'original_delivered'
            WHEN d.makegood_delivered=1 THEN 'makegood_delivered'
            WHEN c.evidence_due_at>s.as_of THEN 'awaiting_log'
            ELSE 'undelivered' END AS delivery_status
FROM commitments c JOIN booking_lines b ON b.booking_line_id=c.booking_line_id
JOIN campaigns p ON p.campaign_id=b.campaign_id JOIN stations st ON st.station_id=b.station_id
CROSS JOIN settings s LEFT JOIN delivery d ON d.commitment_id=c.commitment_id;
