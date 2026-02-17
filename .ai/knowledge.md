# Elite Sniper Knowledge Base

## Evidence-Based Knowledge (Derived from events.log)

### DOM Navigation Patterns

**Pattern**: Image-based selectors fail when images are blocked by resource handler
**Evidence**: Event [NAV-001] - Navigation fallback triggered repeatedly
**Solution**: Use href-based selectors instead of img src selectors
**Selector**: `a[onclick*='startCommitRequest'][href*='appointment_showMonth']`
**Confidence**: High (verified against actual HTML)

### Docker Networking

**Pattern**: Container network isolation prevents external connectivity
**Evidence**: Event [NET-001] - 60s timeout on all page.goto() attempts
**Symptom**: Host machine connects successfully, container times out
**Root Cause**: Docker network mode incompatible with Windows networking
**Workaround**: Run bot directly on host (python src/main.py)
**Long-term Fix**: Use `network_mode: "host"` in docker-compose.yml

### Captcha Solving Strategy

**Pattern**: BETA mode ddddocr provides higher accuracy than default
**Evidence**: Multiple successful captcha solves in logs (yesterday 21:15)
**Configuration**: `ddddocr(beta=True)` with image preprocessing
**Success Rate**: ~75% for 6-char captchas, lower for 7+ chars
**Fallback**: Manual mode via Telegram when OCR fails

### Session Management

**Pattern**: Persistent session (Settlement Mode) preserves cookies better than URL injection
**Evidence**: Previous implementation with URL changes caused session resets
**Architecture**: Stay on calendar page, use DOM clicks for navigation
**Benefit**: Reduces captcha frequency, maintains session state

## Pending Investigations

None currently - Docker network issue is blocking testing

## Configuration Tradeoffs

- **HEADLESS vs GUI**: Headless preferred for production, GUI for debugging
- **CapSolver vs ddddocr**: CapSolver disabled to save costs, ddddocr sufficient
- **AUTO vs MANUAL**: AUTO mode faster but needs high OCR accuracy
