# Changelog

## 0.5.0

- Add a read-only calendar for the maximum of 20 loaded recent charging sessions.
- Add options for the charging card, idle refresh interval and location visibility.
- Refresh active sessions every minute while retaining ten-second command confirmation.
- Add an automation-friendly binary active-session sensor.
- Add active-session status, vehicle current and vehicle phase sensors.
- Translate charging-command states and retain privacy-safe confirmation timing attributes.
- Report a Home Assistant repair warning when the selected card is no longer available.

## 0.4.3

- Show the selected Blossom account and charging card in the main Sensors section.
- Translate raw OCPP charger states into readable English and Dutch values.
- Add the active-session last-update timestamp and bounded charger/session details.
- Keep account and card identifiers out of entity states and diagnostics.

## 0.4.2

- Read active-session start, energy and remuneration type from Blossom's observed nested
  `session` object.
- Add the home-charger status returned by Blossom.
- Extend privacy-safe diagnostics with nested active-session field names, never values.

## 0.4.1

- Show the integration software version in the Home Assistant device information.
- Redact the stored card label from downloadable diagnostics.
- Report active-session field names without their values for safe API diagnosis.
- Fetch cards, recent sessions and active-session state concurrently after scope validation.
- Refresh legacy card labels from live Blossom data during setup.
- Clarify that the recent-session count is the number of loaded records, capped at 20.

## 0.4.0

- Confirm Start and Stop every 10 seconds for at most one minute without resending commands.
- Add last-session amount, home reimbursement, end time and session type.
- Add active-session start and energy when Blossom returns them.
- Add privacy-safe command timing and downloadable diagnostics.
- Refresh the selected card label from live data so old technical suffixes disappear.

## 0.3.1

- Accept an empty successful response from Blossom charging commands.
- Wait two seconds before refreshing status after a start or stop command.

## 0.3.0

- Group all Blossom entities under one Home Assistant service device.
- Add active home-session status and explicit start/stop buttons.
- Start uses the selected card and selected account/installation context.
- Replace technical setup labels and full UUIDs with readable choices.
- Keep internal IDs visible only when two choices have the same label.

## 0.2.1

- New original blossom-and-lightning icon, with standard and high-resolution assets.

## 0.2.0

- Experimental email/password login with PKCE, isolated login cookies and callback checks.
- Refresh-token storage per account entry, serialized renewal and HA reauthentication.
- Explicit membership, installation and card selection.
- Read-only recent history, last completed session measurements and manual refresh.
- English and Dutch UI text, synthetic tests and GitHub validation.
- No charging commands. Live account acceptance remains a separate deployment test.

## 0.1.0

- Installation-only HA setup and unload test, distributed through HACS.
