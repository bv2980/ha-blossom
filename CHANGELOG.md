# Changelog

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
