# Session Persistence & Health Check Protocol

## Goal Description
Implement the "Golden Hour 2.0" and "Session Persistence Protocol" requirements:
1.  **Session Health Check**: Detect if session is dead (returned to captcha) before scanning.
2.  **Heartbeat**: Keep session alive with HEAD requests.
3.  **Anti-Ban**: Sleep 2 minutes if captcha fails 3 times.

## Proposed Changes

### 1. Session Health & Heartbeat
#### [MODIFY] [src/elite_sniper_v2.py](file:///d:/ai/sniper/src/elite_sniper_v2.py)
-   **`check_session_health`**: Implement logic to scan page content for 'captcha', 'verification', 'validating'.
    -   If detected inside the loop, mark session as POISONED and break.
-   **Heartbeat**: Ensure the Javascript keep-alive script is active and effective (already in `create_context`, will verify frequency).

### 2. Anti-Ban Logic
#### [MODIFY] [src/elite_sniper_v2.py](file:///d:/ai/sniper/src/elite_sniper_v2.py)
-   **Captcha Attempts**: Increase to **5** (User requirement).
-   **Escalation**: Trigger 2-minute sleep only after **5 consecutive failures** (Extreme Case).
-   **Health Check**: Use validated selectors from `sniberhtmel` (Fact-Based):
    -   `#appointment_captcha_month` (Month Gate)
    -   `#appointment_newAppointmentForm_captchaText` (Booking Gate)
    -   `div.global-error` (Generic Error)

### 3. Existing Implementation Status
-   **Golden Hour 30s Sleep**: [DONE] Implemented in `get_sleep_interval`.
-   **Month Priority [4, 5, 2, 3]**: [DONE] Implemented in `generate_month_urls`.
-   **Session Persistence**: [DONE] Implemented via `current_max_age = 2700`.

## Verification Plan
1.  **Code Review**: Verify `check_session_health` is called before scanning months.
2.  **Logic Check**: Confirm 2-minute sleep triggers on 3rd failure.
