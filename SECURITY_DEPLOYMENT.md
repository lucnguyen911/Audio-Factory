# Audio Factory security deployment

## 1. Supabase

Run `sql/migration_v3.sql` in the Supabase SQL Editor as the project owner.
Test a new key, a migrated v2 key, a revoked key, an expired key, and a key at
`max_devices`. The desktop client uses only:

- `activate_or_verify_license_v3`
- `get_active_app_version_v3`

The `anon` and `authenticated` roles have no direct access to
`audio_licenses` or `app_versions`. Keep the service-role key only on the
admin machine/server. Never place it in the desktop build.

Admin device actions are `admin_remove_license_device_v3(key, hwid_hash)` for
one device and `admin_reset_license_devices_v3(key)` for all devices. Do not
grant either function to desktop roles.

Rollback of the RPC exposure is in `sql/rollback_v3.sql`.

Do not revoke the v2 RPC before old clients update: startup verifies license
before checking updates. Deploy the v3 migration, publish a forced v3 client,
allow the migration window, and only then run `sql/finalize_v3_cutover.sql`.

## 2. Admin bot

The previously embedded Telegram token must be revoked in BotFather because
removing it from the current source does not remove it from Git history or
older copies. Configure the replacement values from `admin_tools/.env.example`
as process environment variables. Do not commit the real `.env`.

## 3. Build and code protection

Run `automated_build.py`. The build stops if PyArmor does not produce protected
copies of the license, HWID, updater, or version modules. PyInstaller produces
an `onedir` application and Inno Setup creates the only supported update
package. There is no plaintext or ZIP/patch fallback.

For release signing, sign the final installer with an Authenticode certificate
before upload. SHA-256 protects integrity in transit; Authenticode additionally
proves the publisher.

Set `AUDIO_FACTORY_SIGN_CERT_SHA1` to a certificate-store thumbprint to make
the build sign both the application EXE and final installer. Optionally set
`AUDIO_FACTORY_TIMESTAMP_URL`; private keys and PFX passwords are never read
from source files.

## 4. Google Drive release

1. Upload only `Audio_Factory_Premium_Setup_vX.Y.Z.exe`.
2. Grant download access to the intended audience.
3. Run:

   `python scripts/prepare_release_metadata.py <installer.exe> <Drive share URL> --enforcement optional`

4. Review `release_metadata.json`, then upsert those exact fields into
   `app_versions`. Keep `is_active=false` until the upload is fully available.
5. Activate one version at a time.

The updater resolves Google Drive confirmation pages, streams to a `.part`
file, checks file size, SHA-256 and the Windows `MZ` header, then atomically
promotes the download. It runs only from a frozen build and only after license
verification.

## 5. Release gate

- Run `python -m unittest -v tests.test_security_v3`.
- Run the existing full test suite in the project virtual environment.
- Install over the previous published AppId and verify the install directory.
- Test optional decline and forced decline.
- Corrupt a download and confirm it is rejected and the `.part` file removed.
- Verify a successful pending marker is cleared on next packaged startup.
