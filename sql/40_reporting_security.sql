-- Demonstration roles only. Real account provisioning and distribution are separate.
CREATE SCHEMA IF NOT EXISTS tv_reporting;
CREATE TABLE tv_reporting.commitment_summary (
    commitment_id TEXT PRIMARY KEY,advertiser_id INTEGER NOT NULL,campaign_id INTEGER NOT NULL,
    due_commitment INTEGER NOT NULL,delivered INTEGER NOT NULL,
    expected_billable_cents BIGINT NOT NULL,net_invoiced_cents BIGINT NOT NULL
);
CREATE ROLE advertiser_1 NOLOGIN;
CREATE ROLE advertiser_2 NOLOGIN;
ALTER TABLE tv_reporting.commitment_summary ENABLE ROW LEVEL SECURITY;
ALTER TABLE tv_reporting.commitment_summary FORCE ROW LEVEL SECURITY;
CREATE POLICY advertiser_scope ON tv_reporting.commitment_summary FOR SELECT TO advertiser_1,advertiser_2
    USING (advertiser_id=substring(current_user::text FROM '^advertiser_([0-9]+)$')::integer);
REVOKE ALL ON SCHEMA tv_reporting FROM PUBLIC;
REVOKE ALL ON tv_reporting.commitment_summary FROM PUBLIC;
GRANT USAGE ON SCHEMA tv_reporting TO advertiser_1,advertiser_2;
GRANT SELECT ON tv_reporting.commitment_summary TO advertiser_1,advertiser_2;
-- No raw invoices, credits, station feeds or cross-advertiser data are granted.
