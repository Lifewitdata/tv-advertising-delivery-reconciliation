CREATE VIEW v_visible_invoices AS
SELECT i.* FROM invoice_lines i CROSS JOIN settings p
WHERE i.issued_at<=p.as_of AND i.ingested_at<=p.as_of;
CREATE VIEW v_visible_credits AS
SELECT k.* FROM credits k CROSS JOIN settings p
WHERE k.issued_at<=p.as_of AND k.ingested_at<=p.as_of;

CREATE VIEW v_invoice_ledger AS
WITH credit_totals AS (
    SELECT invoice_line_id,SUM(amount_cents) AS credited_cents FROM v_visible_credits GROUP BY invoice_line_id
)
SELECT i.*,COALESCE(k.credited_cents,0) AS credited_cents,
       i.amount_cents-COALESCE(k.credited_cents,0) AS net_invoiced_cents,
       ROW_NUMBER() OVER (PARTITION BY i.commitment_id ORDER BY i.issued_at,i.invoice_line_id) AS charge_number
FROM v_visible_invoices i LEFT JOIN credit_totals k ON k.invoice_line_id=i.invoice_line_id;

CREATE VIEW v_commitment_finance AS
WITH invoiced AS (
    SELECT commitment_id,COUNT(*) AS invoice_line_count,SUM(amount_cents) AS gross_invoiced_cents,
           SUM(credited_cents) AS credited_cents,SUM(net_invoiced_cents) AS net_invoiced_cents
    FROM v_invoice_ledger GROUP BY commitment_id
)
SELECT d.*,COALESCE(i.invoice_line_count,0) AS invoice_line_count,
    COALESCE(i.gross_invoiced_cents,0) AS gross_invoiced_cents,
    COALESCE(i.credited_cents,0) AS credited_cents,COALESCE(i.net_invoiced_cents,0) AS net_invoiced_cents,
    COALESCE(i.net_invoiced_cents,0)-d.expected_billable_cents AS billing_difference_cents,
    CASE WHEN COALESCE(i.net_invoiced_cents,0)>d.expected_billable_cents
         THEN COALESCE(i.net_invoiced_cents,0)-d.expected_billable_cents ELSE 0 END AS overbilled_cents,
    CASE WHEN d.expected_billable_cents>COALESCE(i.net_invoiced_cents,0)
         THEN d.expected_billable_cents-COALESCE(i.net_invoiced_cents,0) ELSE 0 END AS underbilled_cents
FROM v_commitment_delivery d LEFT JOIN invoiced i ON i.commitment_id=d.commitment_id;

CREATE VIEW v_exceptions AS
SELECT airing_status AS exception_type,'source_event' AS entity_type,source_event_id AS entity_id,commitment_id
FROM v_airing_review WHERE airing_status<>'qualifying'
UNION ALL
SELECT 'log_replay','source_event',source_event_id,commitment_id FROM v_airing_review
WHERE raw_record_count>1 AND variant_count=1
UNION ALL
SELECT 'duplicate_airing','scheduled_spot',scheduled_spot_id,commitment_id FROM v_slot_delivery WHERE qualifying_events>1
UNION ALL
SELECT 'undelivered_commitment','commitment',d.commitment_id,d.commitment_id
FROM v_commitment_delivery d WHERE delivery_status='undelivered'
UNION ALL
SELECT 'unmatched_invoice','invoice_line',i.invoice_line_id,i.commitment_id
FROM v_invoice_ledger i LEFT JOIN commitments c ON c.commitment_id=i.commitment_id WHERE c.commitment_id IS NULL
UNION ALL
SELECT 'unmatched_credit','credit',k.credit_id,CAST(NULL AS TEXT)
FROM v_visible_credits k LEFT JOIN v_visible_invoices i ON i.invoice_line_id=k.invoice_line_id WHERE i.invoice_line_id IS NULL
UNION ALL
SELECT 'rate_mismatch','invoice_line',i.invoice_line_id,i.commitment_id
FROM v_invoice_ledger i JOIN v_commitment_delivery d ON d.commitment_id=i.commitment_id WHERE i.unit_rate_cents<>d.unit_rate_cents
UNION ALL
SELECT 'quantity_mismatch','invoice_line',i.invoice_line_id,i.commitment_id
FROM v_invoice_ledger i JOIN commitments c ON c.commitment_id=i.commitment_id WHERE i.quantity<>1
UNION ALL
SELECT 'advertiser_mismatch','invoice_line',i.invoice_line_id,i.commitment_id
FROM v_invoice_ledger i JOIN v_commitment_delivery d ON d.commitment_id=i.commitment_id WHERE i.advertiser_id<>d.advertiser_id
UNION ALL
SELECT 'duplicate_charge','invoice_line',i.invoice_line_id,i.commitment_id
FROM v_invoice_ledger i JOIN commitments c ON c.commitment_id=i.commitment_id WHERE i.charge_number>1
UNION ALL
SELECT 'excess_credit','invoice_line',i.invoice_line_id,i.commitment_id FROM v_invoice_ledger i WHERE credited_cents>amount_cents
UNION ALL
SELECT 'unbilled_delivery','commitment',commitment_id,commitment_id FROM v_commitment_finance
WHERE expected_billable_cents>0 AND invoice_line_count=0
UNION ALL
SELECT 'billed_without_delivery','commitment',commitment_id,commitment_id FROM v_commitment_finance
WHERE expected_billable_cents=0 AND net_invoiced_cents>0
UNION ALL
SELECT 'overbilled','commitment',commitment_id,commitment_id FROM v_commitment_finance WHERE overbilled_cents>0
UNION ALL
SELECT 'underbilled','commitment',commitment_id,commitment_id FROM v_commitment_finance WHERE underbilled_cents>0;
