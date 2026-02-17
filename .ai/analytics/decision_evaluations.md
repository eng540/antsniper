# Decision Evaluations

## Decision: NAV-001 - Switch to href-based Selectors

**Made**: 2026-02-17T13:33:38Z  
**Type**: ARCHITECTURAL  
**Owner**: navigation  
**Status**: APPROVED

### Context
Images blocked by resource handler caused image-based selectors (`img[src*='go-next']`) to fail visibility checks, triggering URL fallback navigation.

### Decision
Changed navigation selectors from image-based to href-pattern matching:
```python
navigation_selector = "a[onclick*='startCommitRequest'][href*='appointment_showMonth']"
```

### Rationale
- Images never load due to resource blocking
- href attributes always present in DOM
- More reliable than depending on visual elements

### Expected Outcomes
- Eliminate "DOM buttons not found" warnings
- Reduce fallback to URL navigation
- Maintain session cookies better with DOM clicks

### Evaluation Status
**PENDING** - Cannot test due to NET-001 blocker

### Evidence References
- Event: NAV-001 decision
- Incident: Navigation fallback pattern
- Code: Commit ca14e02

---

## Decision: NET-001 - Run Outside Docker (Temporary)

**Made**: 2026-02-17T13:33:38Z  
**Type**: DEPLOYMENT  
**Owner**: deployment  
**Status**: TEMPORARY

### Context
Docker container cannot reach external internet (75% packet loss, 60s timeouts on all requests).

### Decision
Run bot directly on host machine using `python src/main.py` until Docker networking is resolved.

### Rationale
- Host machine connectivity confirmed working (TcpTestSucceeded: True)
- Attack window at 18:00 approaching (<2 hours)
- Long-term Docker fix requires more investigation time
- Immediate operational need > architectural purity

### Trade-offs
✅ **Gains**:
- Immediate operational capability
- Proven connectivity
- Fast deployment

❌ **Costs**:
- Loses container isolation
- Manual dependency management
- Less portable deployment

### Expected Outcomes
- Bot connects successfully
- Can test NAV-001 fix
- Ready for 18:00 attack window

### Long-term Plan
Configure `docker-compose.yml` with `network_mode: "host"` after validating solution.

### Evaluation Status
**APPROVED FOR IMMEDIATE USE**

### Evidence References
- Event: NET-001 decision
- Incident: NET-001 (Docker network isolation)
- Test: TcpTestSucceeded on host, timeout in container
