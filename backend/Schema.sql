CREATE TABLE IF NOT EXISTS audio_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename TEXT NOT NULL,
    language_code TEXT NOT NULL,
    transcript TEXT,
    summary TEXT,
    audio_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE audio_notes
    ADD COLUMN IF NOT EXISTS audio_path TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed',
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS claim_token UUID,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS gnani_job_id TEXT;

ALTER TABLE audio_notes
    ALTER COLUMN transcript DROP NOT NULL;