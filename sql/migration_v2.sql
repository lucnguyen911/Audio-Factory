-- ============================================================================
-- Audio Factory Premium — Supabase License Schema Migration v2
-- ============================================================================
-- PURPOSE: Migrate from HWID v1 (WMIC-based, client-side PATCH) to
--          HWID v2 (MachineGuid-based, server-side RPC with row locking).
--
-- PREREQUISITES:
--   1. Backup the 'audio_licenses' table before running this script.
--   2. Review the RLS policies — enabling RLS will break any old client
--      that PATCHes 'hwid' directly.
--
-- ROLLBACK: See the bottom of this file for drop/rollback statements.
-- ============================================================================

-- ── 1. Add v2 columns ───────────────────────────────────────────────────────
ALTER TABLE audio_licenses
ADD COLUMN IF NOT EXISTS hwid_v2 TEXT,
ADD COLUMN IF NOT EXISTS hwid_version INTEGER NOT NULL DEFAULT 1,
ADD COLUMN IF NOT EXISTS legacy_hwid TEXT,
ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS migration_completed_at TIMESTAMPTZ;

-- ── 2. Index for v2 lookups ─────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_audio_licenses_hwid_v2
ON audio_licenses(hwid_v2);

-- ── 3. RPC function with row-level locking ──────────────────────────────────
-- SECURITY DEFINER: runs with the function owner's privileges, bypassing RLS.
-- This is intentional — the function contains the controlled activation logic.
CREATE OR REPLACE FUNCTION activate_or_verify_license_v2(
    p_license_key TEXT,
    p_hwid_v2 TEXT,
    p_hwid_version INTEGER DEFAULT 2,
    p_legacy_candidates TEXT[] DEFAULT '{}',
    p_app_version TEXT DEFAULT ''
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_row audio_licenses%ROWTYPE;
    v_candidate TEXT;
BEGIN
    -- ── Lock the row to prevent race conditions ──────────────────────────
    SELECT * INTO v_row
    FROM audio_licenses
    WHERE license_key = p_license_key
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN json_build_object('status', 'LICENSE_NOT_FOUND');
    END IF;

    -- ── Check active status ──────────────────────────────────────────────
    IF NOT COALESCE(v_row.is_active, TRUE) THEN
        RETURN json_build_object('status', 'LICENSE_DISABLED');
    END IF;

    -- ── Check expiration ─────────────────────────────────────────────────
    IF v_row.expired_at IS NOT NULL AND v_row.expired_at < NOW() THEN
        RETURN json_build_object(
            'status', 'LICENSE_EXPIRED',
            'expired_at', v_row.expired_at
        );
    END IF;

    -- ── Case 1: Already has hwid_v2 — verify match ──────────────────────
    IF v_row.hwid_v2 IS NOT NULL THEN
        IF v_row.hwid_v2 = p_hwid_v2 THEN
            UPDATE audio_licenses
            SET last_seen_at = NOW()
            WHERE license_key = p_license_key;

            RETURN json_build_object('status', 'VALID');
        ELSE
            RETURN json_build_object('status', 'DEVICE_MISMATCH');
        END IF;
    END IF;

    -- ── Case 2: No hwid_v2, no legacy hwid — fresh activation ───────────
    IF v_row.hwid IS NULL THEN
        UPDATE audio_licenses
        SET hwid_v2 = p_hwid_v2,
            hwid_version = p_hwid_version,
            activated_at = NOW(),
            last_seen_at = NOW()
        WHERE license_key = p_license_key;

        RETURN json_build_object('status', 'ACTIVATED');
    END IF;

    -- ── Case 3: Has legacy hwid — try migration ─────────────────────────
    IF v_row.hwid IS NOT NULL AND p_legacy_candidates IS NOT NULL THEN
        FOREACH v_candidate IN ARRAY p_legacy_candidates LOOP
            IF v_row.hwid = v_candidate THEN
                UPDATE audio_licenses
                SET hwid_v2 = p_hwid_v2,
                    hwid_version = p_hwid_version,
                    legacy_hwid = v_row.hwid,
                    migration_completed_at = NOW(),
                    last_seen_at = NOW()
                WHERE license_key = p_license_key;

                RETURN json_build_object('status', 'MIGRATED');
            END IF;
        END LOOP;
    END IF;

    -- ── No candidate matched ─────────────────────────────────────────────
    RETURN json_build_object('status', 'LEGACY_DEVICE_MISMATCH');
END;
$$;

-- ── 4. RLS policies ─────────────────────────────────────────────────────────
-- Enable RLS on the table (if not already enabled)
ALTER TABLE audio_licenses ENABLE ROW LEVEL SECURITY;

-- Allow SELECT for anon (needed for legacy client transition)
-- The RPC uses SECURITY DEFINER so it bypasses RLS entirely.
DROP POLICY IF EXISTS "anon_select_own_license" ON audio_licenses;
CREATE POLICY "anon_select_own_license" ON audio_licenses
    FOR SELECT
    USING (true);

-- No INSERT/UPDATE/DELETE policy for anon = anon cannot modify directly.
-- This prevents the old client PATCH from working once RLS is enabled.
-- If you need a transitional period, create a temporary UPDATE policy:
--
-- CREATE POLICY "anon_update_transitional" ON audio_licenses
--     FOR UPDATE
--     USING (true)
--     WITH CHECK (true);
--
-- Remove it after all clients have updated to v2.

-- ── 5. Grant RPC execution to anon role ─────────────────────────────────────
GRANT EXECUTE ON FUNCTION activate_or_verify_license_v2 TO anon;

-- ── 6. (Optional) Admin reset function ──────────────────────────────────────
-- Use this to manually reset a user's HWID when they reinstall Windows
-- or when legacy migration fails.
CREATE OR REPLACE FUNCTION admin_reset_license_hwid(
    p_license_key TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    UPDATE audio_licenses
    SET hwid_v2 = NULL,
        hwid_version = 1,
        legacy_hwid = COALESCE(legacy_hwid, hwid),
        hwid = NULL
    WHERE license_key = p_license_key;

    IF NOT FOUND THEN
        RETURN json_build_object('status', 'NOT_FOUND');
    END IF;

    RETURN json_build_object('status', 'RESET_OK');
END;
$$;

-- Only service_role should be able to call admin_reset
-- GRANT EXECUTE ON FUNCTION admin_reset_license_hwid TO service_role;


-- ============================================================================
-- ROLLBACK (if needed — uncomment and run)
-- ============================================================================
-- ALTER TABLE audio_licenses DROP COLUMN IF EXISTS hwid_v2;
-- ALTER TABLE audio_licenses DROP COLUMN IF EXISTS hwid_version;
-- ALTER TABLE audio_licenses DROP COLUMN IF EXISTS legacy_hwid;
-- ALTER TABLE audio_licenses DROP COLUMN IF EXISTS activated_at;
-- ALTER TABLE audio_licenses DROP COLUMN IF EXISTS last_seen_at;
-- ALTER TABLE audio_licenses DROP COLUMN IF EXISTS migration_completed_at;
-- DROP INDEX IF EXISTS idx_audio_licenses_hwid_v2;
-- DROP FUNCTION IF EXISTS activate_or_verify_license_v2;
-- DROP FUNCTION IF EXISTS admin_reset_license_hwid;
-- DROP POLICY IF EXISTS "anon_select_own_license" ON audio_licenses;
