-- 1. Campaign delivery. One commitment remains one unit despite multiple airings.
SELECT campaign_id,advertiser_id,SUM(due_commitment) AS due_commitments,
 SUM(CASE WHEN due_commitment=1 AND delivered=1 THEN 1 ELSE 0 END) AS delivered_commitments,
 1.0*SUM(CASE WHEN due_commitment=1 AND delivered=1 THEN 1 ELSE 0 END)/NULLIF(SUM(due_commitment),0) AS delivery_rate
FROM v_commitment_finance GROUP BY campaign_id,advertiser_id ORDER BY campaign_id;

-- 2. Station/daypart performance with ranks within market.
WITH station AS (
 SELECT market,station_id,daypart,COUNT(*) AS due_commitments,SUM(delivered) AS delivered
 FROM v_commitment_finance WHERE due_commitment=1 GROUP BY market,station_id,daypart
)
SELECT *,1.0*delivered/due_commitments AS delivery_rate,
 DENSE_RANK() OVER(PARTITION BY market ORDER BY 1.0*delivered/due_commitments) AS underdelivery_rank
FROM station ORDER BY market,underdelivery_rank;

-- 3. Due-date trend and cumulative totals. Recomputed at one knowledge cutoff.
WITH daily AS (
 SELECT SUBSTR(CAST(due_at AS TEXT),1,10) AS due_date,COUNT(*) AS due_commitments,SUM(delivered) AS delivered
 FROM v_commitment_finance WHERE due_commitment=1 GROUP BY SUBSTR(CAST(due_at AS TEXT),1,10)
)
SELECT *,SUM(due_commitments) OVER(ORDER BY due_date ROWS UNBOUNDED PRECEDING) AS cumulative_due,
 SUM(delivered) OVER(ORDER BY due_date ROWS UNBOUNDED PRECEDING) AS cumulative_delivered
FROM daily ORDER BY due_date;

-- 4. Billable value and net billing at the same commitment grain.
SELECT advertiser_id,SUM(expected_billable_cents) AS expected_billable_cents,
 SUM(net_invoiced_cents) AS net_invoiced_cents,SUM(overbilled_cents) AS overbilled_cents,
 SUM(underbilled_cents) AS underbilled_cents
FROM v_commitment_finance GROUP BY advertiser_id ORDER BY advertiser_id;

-- 5. Largest unresolved commitment differences; do not sum repeated exception flags.
SELECT commitment_id,advertiser_id,campaign_id,expected_billable_cents,net_invoiced_cents,billing_difference_cents
FROM v_commitment_finance WHERE billing_difference_cents<>0 ORDER BY ABS(billing_difference_cents) DESC,commitment_id LIMIT 25;

-- 6. Campaign-start cohorts, not user/customer retention.
SELECT SUBSTR(CAST(p.start_date AS TEXT),1,7) AS campaign_start_month,COUNT(*) AS due_commitments,
 SUM(d.delivered) AS delivered,1.0*SUM(d.delivered)/COUNT(*) AS delivery_rate
FROM v_commitment_finance d JOIN campaigns p ON p.campaign_id=d.campaign_id
WHERE due_commitment=1 GROUP BY SUBSTR(CAST(p.start_date AS TEXT),1,7) ORDER BY campaign_start_month;

-- 7. Original delivery versus recovery through authorized replacement spots.
SELECT campaign_id,SUM(due_commitment) AS due_commitments,
 SUM(CASE WHEN due_commitment=1 AND original_delivered=1 THEN 1 ELSE 0 END) AS original_deliveries,
 SUM(CASE WHEN due_commitment=1 AND original_delivered=0 AND makegood_delivered=1 THEN 1 ELSE 0 END) AS recovered_by_makegood
FROM v_commitment_finance GROUP BY campaign_id ORDER BY campaign_id;

-- 8. Exception investigation queue counts.
SELECT exception_type,entity_type,COUNT(*) AS exceptions FROM v_exceptions
GROUP BY exception_type,entity_type ORDER BY exceptions DESC,exception_type;
