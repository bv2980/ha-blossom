# Acceptance-test improvements

## Setup UI (user feedback, 2026-09-25)

- [ ] Replace technical membership terminology with clear company/account wording in English and Dutch.
- [ ] Investigate actual API fields for recognizable company and home-installation labels. Current name/email and name/label fallbacks show generic labels and UUIDs; do not assume the API has no names.
- [ ] Show internal identifiers only when needed to distinguish otherwise identical choices.
- [ ] Simplify scope and card descriptions; move developer-oriented explanations to documentation while keeping essential scope limitations clear.
- [ ] Replace raw card type codes such as `msp` with a meaningful translated label, or omit them when they do not help selection.
- [ ] Verify language follows the HA user profile; screenshots show English. Do not assume missing Dutch translations or force Dutch globally.

Implemented for 0.3.0: readable setup wording, no raw card-type code, full IDs hidden unless needed for duplicate labels, and all entities grouped under one HA service device. Live acceptance remains pending.

## Observations

- User reached company/installation selection after login and then card selection: these parts of the live flow succeeded.
- Final submission, entity creation, and session data accuracy still require user acceptance.
- HACS showed old release information; Redownload allowed the update. Root cause is unconfirmed.

Do not put account names, identifiers, credentials, or raw API responses in this file.

## Confirmed live acceptance

- Setup completed on v0.2.1; seven sensors and one refresh button created, new icon visible.
- Available-card sensor shows one card.
- Last completed session energy matches the Blossom app (confirmed by user).
- Manual refresh succeeded: button press at 15:51:28, successful-update timestamp at 15:51:30.
- Still to verify: reload/restart using persisted authentication, automatic periodic updates and token renewal over time, session start and duration accuracy.

- User confirmed integration reload succeeds and data returns without signing in again. Full HA restart and long-term automatic token renewal remain unverified.

## 0.3.0 acceptance still required

- Device page shows status, history entities and controls together.
- Inactive session: start button available and stop button unavailable.
- Start authorizes the connected car with the selected Blossom card.
- Active session: stop button available and start button unavailable.
- Son's car remains unauthorized until his own card is presented.
