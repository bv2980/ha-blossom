# Remote-start response investigation

Inspected on 2026-09-30, without authentication or charging commands:

- Official application: https://app.blossom.be/
- Public bundle: https://app.blossom.be/assets/index-pMlbSzk_.js

The bundle's `useHomeChargingSession` posts a card ID to the home-session Start endpoint.
Its member-aware request wrapper supplies the member and installation query parameters
and selected company header. These match the integration's existing request structure.
The Start handler ignores the returned payload, shows a success notification after a
resolved request and accelerates polling. The boosted poll interval is 2.5 seconds for
30 seconds; its normal interval is 15 seconds. These are observations of this bundle,
not a supported third-party API contract.

The handler does not define the meaning of the unknown 15-character status observed in
the user's sanitized diagnostics. The 46-field response shape does not establish whether
the object is a session, authorization or command result. No status is guessed from its
length, and no unknown status is treated as acceptance or rejection.

Version 0.5.4 therefore offers explicit, temporary capture of just the top-level Start
status. The capture is absent by default, limited to 128 characters, checked for obvious
sensitive patterns and kept separate from persisted/logged evidence. It remains arbitrary
upstream text and must be reviewed before sharing. All other response fields remain subject
to the existing strict allowlist. This is an investigation aid, not a remote-start fix.
