# Blossom Energy for Home Assistant

Unofficial custom integration, maintained by bv2980. Not affiliated with Blossom.

## Status: 0.1.0 installation test

This development milestone only tests discovery, UI setup, loading and unloading.
It does not authenticate, retrieve sessions, create entities or control charging.
Target for the first manual acceptance test: Home Assistant Core 2026.9.3 on HAOS.
Live HA acceptance testing is still pending; this is not a public-ready release.

## Architecture

- `custom_components/blossom_energy/`: Home Assistant lifecycle and UI.
- A separate asynchronous Blossom client will be added with authentication.
- Session entities will share a data update coordinator.
- Vehicle-specific authorization rules belong in user automations, not this integration.
- Account IDs, credentials, installation IDs and card IDs must never be hardcoded.

The manifest's cloud-polling classification describes the planned integration.
There is no polling or external traffic in this milestone.

## Install with HACS

1. In HACS, open the three-dot menu > Custom repositories.
2. Add `https://github.com/bv2980/ha-blossom` with type **Integration**.
3. Find Blossom Energy and download version **0.1.0**.
4. Restart Home Assistant Core.
5. Under Settings > Devices & services > Add integration, search for Blossom Energy.
6. Submit the installation-test form. Zero devices/entities is expected.

This repository is experimental and is not part of the default HACS catalogue.
The icon is an original generic charging symbol, not the Blossom company logo.

## Manual installation alternative

1. Keep a current HA backup.
2. Copy the `blossom_energy` folder from `custom_components` into your HA configuration
   directory's `custom_components` folder. On HAOS this is normally
   `/config/custom_components/blossom_energy/` (also accessible as `/homeassistant`
   in some apps). Do not overwrite an existing folder with this name without checking it.
3. Restart Home Assistant Core.
4. Under Settings > Devices & services > Add integration, search for Blossom Energy.
5. Read the installation-test screen and submit.

Do not add anything to configuration.yaml. Do not install Python dependencies manually.

## Acceptance checks

- The setup screen clearly identifies this as an installation test.
- Submitting creates the entry without errors. Zero devices/entities is expected.
- A second attempt to add it is refused.
- Reload the entry and check HA logs for errors from `blossom_energy`.
- Restart HA and confirm the entry loads again.
- Delete the entry and confirm no integration error appears.

Home Assistant may warn that a custom integration has not been tested by Home Assistant;
that generic warning is expected and is different from an exception or setup failure.

Before milestone 2, delete this installation-test entry. The authenticated version will
use verified account identity and support account-based setup instead of this temporary
single installation-test entry. No user data or credentials exist to migrate in 0.1.0.

## Rollback

Delete the test entry under Devices & services. If installed through HACS, remove
the downloaded integration there and restart Core. For a manual installation, remove only the
`custom_components/blossom_energy` folder you installed, then restart Core.

## Next milestones

1. Validated authentication and account/installation/card selection.
2. Read-only recent sessions and sensors, with automated tests using synthetic data.
3. Active sessions and explicit manual authorization.
4. Separate Tesla automation.
5. Public distribution documentation and compatibility checks.

The supplied staging Swagger documentation is incomplete for personal authentication.
Production authentication and response contracts must be verified before implementing
those milestones. Reusing the web app's login flow is not yet a confirmed supported
authentication method for distribution.
