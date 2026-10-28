-- TIMESTAMPTZ values are canonical UTC ISO-8601 strings in SQLite and native
-- timestamp-with-time-zone values in PostgreSQL. Amounts are integer USD cents.
CREATE TABLE settings (as_of TIMESTAMPTZ NOT NULL);
CREATE TABLE advertisers (advertiser_id INTEGER PRIMARY KEY, advertiser_name TEXT NOT NULL, industry TEXT NOT NULL);
CREATE TABLE campaigns (campaign_id INTEGER PRIMARY KEY, advertiser_id INTEGER NOT NULL REFERENCES advertisers(advertiser_id),
    campaign_name TEXT NOT NULL, start_date DATE NOT NULL, end_date DATE NOT NULL, creative_id TEXT NOT NULL);
CREATE TABLE stations (station_id INTEGER PRIMARY KEY, station_name TEXT NOT NULL, market TEXT NOT NULL,
    timezone TEXT NOT NULL, delivery_partner TEXT NOT NULL);
CREATE TABLE booking_lines (booking_line_id TEXT PRIMARY KEY, campaign_id INTEGER NOT NULL REFERENCES campaigns(campaign_id),
    station_id INTEGER NOT NULL REFERENCES stations(station_id), daypart TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds > 0), unit_rate_cents BIGINT NOT NULL CHECK (unit_rate_cents > 0),
    currency TEXT NOT NULL CHECK (currency='USD'));
CREATE TABLE commitments (commitment_id TEXT PRIMARY KEY, booking_line_id TEXT NOT NULL REFERENCES booking_lines(booking_line_id),
    cancelled INTEGER NOT NULL CHECK (cancelled IN (0,1)), due_at TIMESTAMPTZ NOT NULL, evidence_due_at TIMESTAMPTZ NOT NULL);
CREATE TABLE scheduled_spots (scheduled_spot_id TEXT PRIMARY KEY, commitment_id TEXT NOT NULL REFERENCES commitments(commitment_id),
    station_id INTEGER NOT NULL REFERENCES stations(station_id), scheduled_at TIMESTAMPTZ NOT NULL,
    window_start TIMESTAMPTZ NOT NULL, window_end TIMESTAMPTZ NOT NULL, duration_seconds INTEGER NOT NULL,
    creative_id TEXT NOT NULL, is_makegood INTEGER NOT NULL CHECK (is_makegood IN (0,1)), replaces_spot_id TEXT NOT NULL);
-- Unknown business references in event/billing feeds are retained for quarantine.
-- Structural event ingestion IDs remain unique; source_event_id can be replayed.
CREATE TABLE airing_logs (source_event_id TEXT NOT NULL, scheduled_spot_id TEXT NOT NULL, station_id INTEGER NOT NULL,
    aired_at TIMESTAMPTZ NOT NULL, duration_seconds INTEGER NOT NULL, creative_id TEXT NOT NULL,
    ingestion_id TEXT PRIMARY KEY, ingested_at TIMESTAMPTZ NOT NULL);
CREATE TABLE invoice_lines (invoice_line_id TEXT PRIMARY KEY, invoice_id TEXT NOT NULL, commitment_id TEXT NOT NULL,
    advertiser_id INTEGER NOT NULL REFERENCES advertisers(advertiser_id), unit_rate_cents BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0), amount_cents BIGINT NOT NULL CHECK (amount_cents >= 0),
    issued_at TIMESTAMPTZ NOT NULL, ingested_at TIMESTAMPTZ NOT NULL);
CREATE TABLE credits (credit_id TEXT PRIMARY KEY, invoice_line_id TEXT NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0), issued_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL, reason TEXT NOT NULL);
CREATE INDEX idx_logs_event ON airing_logs(source_event_id,ingested_at);
CREATE INDEX idx_logs_schedule ON airing_logs(scheduled_spot_id,ingested_at);
CREATE INDEX idx_schedules_commitment ON scheduled_spots(commitment_id);
CREATE INDEX idx_invoice_commitment ON invoice_lines(commitment_id,issued_at);
CREATE INDEX idx_credits_invoice ON credits(invoice_line_id,ingested_at);
CREATE INDEX idx_commitment_due ON commitments(due_at,booking_line_id);
