# Blossom Energy for Home Assistant

Unofficial custom integration maintained by **bv2980**. Not affiliated with Blossom.

## Version 0.4.2: active-session details and session pricing

Sign in with email/password, explicitly select your Blossom account, home installation and
card, retrieve up to 20 recent sessions, and start or stop a home-charging session. The
integration does not change card or energy-management settings. Compatibility target:
Home Assistant Core **2026.9.3** or newer.

This is experimental. Automated tests use synthetic data. Successful authentication
and the returned data must still be checked against your own account in HA.

## Install or update through HACS

1. In HACS > three-dot menu > Custom repositories, add
   `https://github.com/bv2980/ha-blossom` with type **Integration**.
2. Download the latest release, then restart Home Assistant Core.
3. If upgrading from 0.1.0, delete only the **Blossom Energy — installation test**
   entry under Settings > Devices & services. Keep the integration installed in HACS.
   The old test entry contains no credentials or entities; it has no account to migrate.
4. Add **Blossom Energy** under Settings > Devices & services > Add integration.
5. Enter your Blossom email/password locally in HA. Select the membership and home
   installation that belong together, then select your charging card.

No YAML, shell commands, external service or manual dependency installation is needed.
One installation per Blossom account is currently supported. Different accounts can
have separate entries and token stores. To change membership/installation/card in this
milestone, remove the entry and configure it again.

## What is available

- Available-card count, with card labels/types/IDs in attributes.
- Selected card and whether it still appears in the available-card list.
- Recent-session count, with a maximum of 20 summaries in the `sessions` attribute.
- Last **completed** session start/end, type, energy, duration, displayed amount and home
  reimbursement, when returned.
- Last successful update and a manual refresh button.
- Active home-session status and explicit start/stop buttons on one HA device page.
- Active-session start, energy and Blossom charger status, plus privacy-safe diagnostics.
- Integration version in device information and privacy-safe active-response field diagnostics.

Regular updates are coordinated every 15 minutes. Account scope is validated first;
cards, history and active-session status are then fetched concurrently. After Start or Stop, the integration
checks the active-session endpoint every 10 seconds for at most one minute and stops as
soon as Blossom confirms the requested state. It never resends a charging command.
Session history comes from the employee `recent` endpoint using the selected membership
and installation parameters. It can include home and public charging; it is **not filtered
to the selected card**. The card selection does not prove vehicle identity or authorize a
session. Starting home charging uses the card selected during setup. No complete archive
or monthly total is calculated from this limited window.
Empty history is valid; last-session measurements are unknown until a completed session
with the relevant fields exists. Unavailable data is never replaced with zero.

The amount follows Blossom's web app: home sessions use `hcpPrice`; other sessions use
`mspPrice` including the returned VAT percentage (21% when Blossom omits it). The source
price and VAT are available as bounded attributes for verification.
These session-energy sensors are not cumulative meters for the Energy dashboard.

## Authentication and storage

The asynchronous API client is isolated from Home Assistant. It follows the web app's
Auth0 authorization-code + PKCE flow, validates the callback host/path and OAuth state,
and only sends credentials to the production Auth0 host. It does not fetch the callback
URL. The password is discarded after login. MFA, CAPTCHA and social login are not
supported; the integration reports a sign-in error instead of bypassing them.

This first-party web-login flow is **not a confirmed supported third-party contract**.
Blossom can change it. A supported browser OAuth flow remains the preferred future route
if Blossom supplies a suitable client registration and redirect URI.

Access tokens stay in memory. Refresh tokens are saved with Home Assistant's atomic
storage helper under a separate random key for each entry. This storage is local, not
an encrypted vault: protect HA access and backups. Token refresh is serialized, and a
rotated token is saved before further API requests. An ambiguous refresh timeout requires
a new sign-in instead of blindly replaying a potentially consumed token. A sudden process
or disk failure during rotation may also require signing in again.

No credentials, tokens, raw responses or authentication URLs are logged. Deleting an entry
removes its token store; it does not revoke the login at Blossom. Never upload `.storage`,
HA backups, tokens or real API responses to GitHub.

## Acceptance checks in HA

1. Sign in and verify the membership, installation and available cards are yours.
2. Compare recent session dates, kWh and minutes with the Blossom app. The list can include
   public charging. View the bounded list under the recent-session sensor's attributes.
3. Press **Refresh Blossom data**; verify the last successful update changes.
4. Reload the entry. Confirm entities recover without another password prompt.
5. At a convenient moment, restart HA; confirm saved tokens restore the connection.
6. Report the exact user-facing error and the step if something fails, without secrets.

The generic HA warning about a custom integration is expected. Setup exceptions are not.
If no cards are available or the response format changes, setup stops with an explicit
error. Vehicle-specific automatic charging remains outside this release.

## Architecture and tests

- `api.py`: HA-independent async HTTP, PKCE login, token lifecycle and allowlisted endpoints.
- `models.py`: explicit data validation and privacy-conscious session summaries.
- `config_flow.py`: login, explicit scope/card selection and same-account reauthentication.
- `coordinator.py`: shared updates and bounded command-confirmation polling.
- `sensor.py`, `button.py`: status entities, manual refresh and explicit charging controls.
- `diagnostics.py`: privacy-safe Home Assistant diagnostics without identifiers or tokens.
- `__init__.py`: setup, unloading and token cleanup on removal.

Unit tests cover callback validation, credential destinations, token reuse/rotation,
concurrency, persistence failures, HTTP errors, unknown data shapes and session units.
GitHub Actions additionally tests setup, entities, reauthentication, reload and removal
against real HA 2026.9.3 with mocked cloud calls, and runs HA manifest validation.

Local client tests (Python 3.12+): `pytest tests/unit`.
HA tests require Python 3.14 and `pytest-homeassistant-custom-component==0.13.366`.
No test needs a real Blossom account.

## Removal and rollback

Remove the entry under Devices & services to remove its entities and local token store.
Then remove the integration in HACS and restart Core if you want to uninstall it.
To return to 0.1.0, first remove the authenticated 0.2.0 entry, download 0.1.0 in HACS,
and restart. Version 0.1.0 cannot load authenticated entries from 0.2.0.

## API reference

Endpoint names were checked against [Blossom staging Swagger](https://stg.api.blossom.be/api/docs)
and the public production web app on 2026-09-25. All runtime traffic uses production.
The web app confirms the `start`, `end`, `kwh` and minute-based `duration` fields and
paginated `{data, meta}` history. The implementation deliberately rejects unknown shapes.
The included generic charging icon is original, not Blossom's company logo.
