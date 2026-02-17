# Serving-Centric Auth Audit

**Feature:** Serving-Centric Auth (Issue #732)
**Date:** 2026-02-14
**Auditor:** doc-writer (Claude Code)
**Type:** Deep Audit (Functional + UX)
**Result:** FAIL - Critical issues found requiring remediation

---

## Executive Summary

The serving-centric auth feature (Issue #732) is functionally complete for local development but has critical gaps in security, error handling, and user experience that must be addressed before production use. The core architecture is sound: Serving manages credentials, frontend gates on auth status, compute fetches credentials via HTTP.

**Functional Score: 7/10 PASS, 3/10 FAIL** (Security, Error Handling, Documentation)
**UX Score: 2/8 CRITICAL, 5/8 NEEDS IMPROVEMENT, 1/8 GOOD**

### Critical Blockers

1. **SECURITY**: `/auth/credentials` endpoint has NO authentication - any network caller can retrieve OAuth tokens
2. **ERROR HANDLING**: useAuth.js bypasses auth gate on network errors (security + UX issue)
3. **RE-AUTHENTICATION**: No way to re-authenticate from within main app when credentials expire

---

## Functional Audit Findings

### 1. API Contract - PASS

**What was tested:**
- All auth endpoints exist and are correctly registered
- Request/response schemas match specification
- HTTP methods and paths are correct

**Evidence:**
- ✅ `GET /auth/status` - Returns `AuthStatusResponse`
- ✅ `POST /auth/login` - Returns `AuthLoginResponse` with login URL
- ✅ `POST /auth/login/cancel` - Cancels pending login
- ✅ `GET /auth/credentials` - Returns Claude credentials (OAuth + API key)

**Files Verified:**
- `serving/routers/auth_router.py` - All endpoints defined
- `serving/app.py` - Router included with `/auth` prefix

---

### 2. Service Wiring - PASS

**What was tested:**
- ClaudeAuthService properly initialized in serving container
- SSE broadcast callback wired for credential updates
- Shutdown handlers properly registered

**Evidence:**
- ✅ Service created in `serving/app.py:71-77` with SSE callback
- ✅ SSE broadcast triggered on successful login (auth_service.py:167)
- ✅ Shutdown handler calls `auth_service.cleanup()` (app.py:101)

**Files Verified:**
- `serving/app.py`
- `serving/services/claude_auth_service.py`

---

### 3. Frontend Gate Logic - PASS

**What was tested:**
- App.jsx gates access to main app on authenticated state
- useAuth hook polls status every 3 seconds
- 404 response correctly treated as "auth disabled"

**Evidence:**
- ✅ `App.jsx:24-26` - Shows AuthSetupPage if `!authenticated && authEnabled`
- ✅ `useAuth.js:23-42` - Polls `/auth/status` every 3s via setInterval
- ✅ `useAuth.js:33` - 404 sets `authEnabled: false` (bypasses gate)

**Files Verified:**
- `serving/frontend/src/App.jsx`
- `serving/frontend/src/hooks/useAuth.js`

---

### 4. Compute Credential Flow - PASS

**What was tested:**
- Compute entrypoint.sh handles three credential modes
- credential_monitor.py fetches from serving via HTTP
- SSE handler triggers re-fetch on credential updates

**Evidence:**
- ✅ `compute/base/entrypoint.sh:79-100` - Handles `serving`/`local`/`external` modes
- ✅ `compute/base/scripts/credential_monitor.py:60-89` - Fetches from `SERVING_URL/auth/credentials`
- ✅ SSE handler in `credential_monitor.py:122-130` - Triggers re-fetch on "auth_credentials_updated" event

**Files Verified:**
- `compute/base/entrypoint.sh`
- `compute/base/scripts/credential_monitor.py`

---

### 5. Docker Infrastructure - PASS

**What was tested:**
- Environment variables consistent across docker-compose.yml
- Node.js and Claude CLI installed in serving Dockerfile
- No legacy host-claude volume mounts remain

**Evidence:**
- ✅ `docker-compose.yml:33-35` - Serving env vars: `CLAUDE_API_KEY`, `CLAUDE_OAUTH_TOKEN`, `CLAUDE_AUTH_MODE=serving`
- ✅ `docker-compose.yml:58-59` - Compute env vars: `COMPUTE_CREDENTIAL_MODE=serving`, `SERVING_URL=http://serving:8002`
- ✅ `serving/Dockerfile:15-28` - Node.js 20.x + Claude CLI 0.3.19 installed
- ✅ No `~/.claude:/root/.claude:ro` mounts in docker-compose.yml

**Files Verified:**
- `docker-compose.yml`
- `serving/Dockerfile`

---

### 6. Test Coverage - PASS

**What was tested:**
- Unit tests exist for service, API, models, and compute credential fetch
- Tests cover success paths and error cases
- All tests passing (38 tests total)

**Evidence:**
- ✅ `serving/tests/unit/services/test_claude_auth_service.py` - 15 tests
- ✅ `serving/tests/unit/routers/test_auth_router.py` - 18 tests
- ✅ `serving/tests/unit/models/test_auth.py` - 3 tests
- ✅ `compute/base/tests/unit/test_credential_monitor.py` - 2 tests (fetch_from_serving)

**Files Verified:**
- Test files in `serving/tests/unit/` and `compute/base/tests/unit/`

---

### 7. Security - FAIL (CRITICAL)

**What was tested:**
- Authentication on `/auth/credentials` endpoint
- Compute instance authentication when fetching credentials
- Credential exposure risk on Docker bridge network

**Issues Found:**
- ❌ **CRITICAL**: `/auth/credentials` endpoint has NO authentication (serving/routers/auth_router.py:57)
- ❌ Any container on the Docker bridge network can call `http://serving:8002/auth/credentials` and retrieve OAuth tokens
- ❌ Compute instances don't authenticate when fetching credentials
- ⚠️ Fine for isolated Docker bridge network, unacceptable for production deployment

**Impact:**
- **High Risk** in production environments where serving is exposed
- **Medium Risk** in development (Docker bridge network provides some isolation)

**Recommendation:**
Create issue **SECURITY-01**: Add authentication to `/auth/credentials` endpoint
- Options: API keys per compute instance, mTLS, shared secret
- Must verify compute identity before returning credentials

---

### 8. Error Handling - FAIL (PARTIAL)

**What was tested:**
- Credential expiry detection and auto-re-fetch
- OAuth flow timeout handling
- Serving container restart recovery
- Compute credential fetch failure handling

**Issues Found:**
- ❌ No credential expiry monitoring in compute (credential_monitor.py only fetches on startup + SSE)
- ❌ No OAuth flow timeout - login URL valid indefinitely (auth_service.py:103-113)
- ❌ If serving restarts mid-OAuth flow, state is lost (in-memory only)
- ❌ Compute failures in credential_monitor.py are logged but don't stop container (line 92)

**Partial Success:**
- ✅ HTTP errors from serving are caught and logged (credential_monitor.py:82-89)
- ✅ SSE reconnection handled by EventSource API

**Impact:**
- **Medium Risk**: Compute containers may continue running without valid credentials
- **Low Risk**: OAuth flow can be exploited if login URL leaked (no expiry)

**Recommendation:**
Create issue **ERROR-01**: Add credential expiry detection and re-auth in compute
Create issue **ERROR-02**: Add OAuth flow timeout (10 min auto-cancel)
Create issue **ERROR-03**: Add serving restart state recovery (persist OAuth state to Redis)

---

### 9. Documentation - FAIL

**What was tested:**
- Documentation reflects new serving-centric architecture
- Setup instructions updated for OAuth flow
- Environment variable documentation current

**Issues Found:**
- ❌ No documentation in `docs/` directory describes serving-centric auth
- ❌ README.md still references local credential mode
- ❌ No guide for CLI re-auth script usage

**Files Checked:**
- `README.md` - Outdated
- `docs/` - No auth documentation found

**Recommendation:**
Create issue **DOC-01**: Update auth documentation for serving-centric flow
- Add `docs/guides/serving-auth-setup.md`
- Update README.md with OAuth setup instructions
- Document CLI re-auth script location and usage

---

### 10. Consistency Note - Environment Variables

**Observation:**
Environment variable naming uses mixed prefixes:
- `CLAUDE_*` for serving (e.g., `CLAUDE_API_KEY`, `CLAUDE_AUTH_MODE`)
- `COMPUTE_*` for compute (e.g., `COMPUTE_CREDENTIAL_MODE`)
- `CLAUDEVN_*` in some places (e.g., `CLAUDEVN_SHARED_API_URL`)

**Recommendation:**
Standardize on `CLAUDEVN_` prefix for consistency:
- `CLAUDEVN_SERVING_AUTH_MODE`
- `CLAUDEVN_COMPUTE_CREDENTIAL_MODE`
- `CLAUDEVN_API_KEY`

Not critical, but improves long-term maintainability.

---

## UX Audit Findings

### 1. Error States - CRITICAL

**What was tested:**
- Error handling in useAuth.js
- Error message display to users
- Network failure behavior

**Issues Found:**
- ❌ **CRITICAL**: `useAuth.js:33-39` treats ALL fetch errors as "auth disabled" - bypasses auth gate when server is unreachable
  ```javascript
  } catch (error) {
    if (error.message.includes('404')) {
      setAuthEnabled(false);
    }
  }
  ```
  **Impact**: If serving is down, users can access main app without authentication (security + UX issue)

- ❌ Backend error messages discarded - `useLogin.js:19-22` shows generic "An error occurred" instead of server's `message` field
  ```javascript
  } catch (error) {
    setError('An error occurred during login');
  }
  ```
  **Impact**: User sees "An error occurred" when actual error is "Claude CLI not found" (not actionable)

- ❌ No recovery guidance - errors shown with no next steps

**Recommendation:**
Create issue **UX-ERROR-01**: Fix useAuth.js error handling
- Only 404 should bypass auth gate
- Network errors should show error page with retry option
- Other HTTP errors should show error with status code

Create issue **UX-ERROR-02**: Surface backend error messages to frontend
- Pass `message` field from API responses through to UI
- Show specific error text instead of generic message

---

### 2. Re-authentication - CRITICAL

**What was tested:**
- Re-authentication path after credentials expire
- In-app credential refresh flow
- User notification of credential expiry

**Issues Found:**
- ❌ **CRITICAL**: No way to re-authenticate from within main app
- ❌ `useAuth.js:42` - Polling stops after initial authenticated state (`return;` when already authenticated)
- ❌ When credentials expire, user gets no notification - compute operations silently fail
- ❌ CLI re-auth script exists (`scripts/re-auth.sh`) but not discoverable from UI

**Impact:**
- Users must restart Docker containers to re-authenticate
- No in-app credential refresh flow
- Poor UX for long-running sessions

**Recommendation:**
Create issue **UX-REAUTH-01**: Add re-auth path in main app
- Add "Re-authenticate" button in header/settings
- Continue polling auth status even when authenticated
- Show notification when credentials expire
- Redirect to AuthSetupPage for re-auth flow

---

### 3. First-Time Setup - NEEDS IMPROVEMENT

**What was tested:**
- AuthSetupPage clarity for first-time users
- Status communication and instructions

**Issues Found:**
- ⚠️ `AuthSetupPage.jsx:63` - Subtitle uses developer jargon: "secure compute orchestration"
  - Better: "Authenticate with Claude to enable AI features"
- ⚠️ Status badge shows "Not configured" - not user-actionable
  - Better: "Authentication required" or "Not authenticated"
- ✅ Good: Login button with clear CTA
- ✅ Good: Copy URL functionality

**Recommendation:**
Create issue **UX-SETUP-01**: Improve first-time setup messaging
- Simplify subtitle for end users
- Use action-oriented status labels
- Add brief explanation of OAuth flow

---

### 4. Login Flow - NEEDS IMPROVEMENT

**What was tested:**
- Login button interaction
- Status communication during OAuth flow
- Error handling in login process

**Issues Found:**
- ⚠️ `AuthSetupPage.jsx:98` - No loading state on login button (double-click possible)
- ⚠️ No differentiation between "generating URL" and "waiting for OAuth completion"
- ⚠️ `useLogin.js:19` - Login errors silently swallowed (console.error only)
- ✅ Good: Copy URL functionality
- ✅ Good: Login URL clickability

**Recommendation:**
Create issue **UX-LOGIN-01**: Add login button loading state
- Disable button after click to prevent double-clicks
- Show spinner in button during API call

Create issue **UX-LOGIN-02**: Differentiate login flow states
- "Generating login URL..." (API call in progress)
- "Waiting for authentication..." (URL generated, waiting for OAuth)
- Show different UI for each state

---

### 5. Auto-Transition - NEEDS IMPROVEMENT

**What was tested:**
- Transition from AuthSetupPage to main app after successful auth

**Issues Found:**
- ⚠️ Abrupt transition - useAuth detects authenticated state and App.jsx immediately shows main app
- ⚠️ No success confirmation or feedback
- ⚠️ User may not realize authentication succeeded

**Recommendation:**
Create issue **UX-TRANSITION-01**: Add success transition state
- Show brief success message before transition (2-3 seconds)
- Add fade transition between pages
- Example: "Authentication successful! Loading..."

---

### 6. Loading States - NEEDS IMPROVEMENT

**What was tested:**
- Initial app load experience
- Loading feedback while auth status is checked

**Issues Found:**
- ⚠️ `App.jsx:18-20` - Returns `null` while loading (blank screen flash)
  ```jsx
  if (loading) {
    return null;
  }
  ```
- ⚠️ No skeleton or background color during initial load

**Recommendation:**
Create issue **UX-LOADING-01**: Add loading screen in App.jsx
- Show centered spinner with "Loading..." text
- Add background color to prevent white flash
- Consider skeleton UI for main app structure

---

### 7. Status Communication - NEEDS IMPROVEMENT

**What was tested:**
- Status label clarity on AuthSetupPage
- User understanding of current state

**Issues Found:**
- ⚠️ Developer-facing labels:
  - "Not configured" (what should user configure?)
  - "Login in progress" (OK, but could be better)
  - "Authenticated" (OK)
- ⚠️ No explanation of what each status means

**Recommendation:**
Create issue **UX-STATUS-01**: Improve status labels for end users
- "Not configured" → "Authentication required"
- "Login in progress" → "Waiting for authentication..."
- Add tooltips or brief descriptions for each status

---

### 8. Accessibility - NEEDS IMPROVEMENT

**What was tested:**
- Screen reader support
- Keyboard navigation
- ARIA attributes

**Issues Found:**
- ⚠️ `AuthSetupPage.jsx:84-94` - Spinner has no aria-label or role
- ⚠️ Error container at line 80 not `role="alert"`
- ⚠️ Copy button status change ("Copied!") not announced to screen readers
- ✅ Good: Semantic HTML (header, main)

**Recommendation:**
Create issue **UX-A11Y-01**: Add accessibility attributes
- Add `role="status"` and `aria-live="polite"` to status badge
- Add `role="alert"` to error container
- Add aria-label to spinner
- Announce "Copied!" to screen readers

---

## Issues to Create

### P0 - Security (Critical Blockers)

1. **SECURITY-01: Add authentication to /auth/credentials endpoint**
   - Description: Endpoint currently has no authentication - any network caller can retrieve OAuth tokens
   - Impact: High security risk in production
   - Solution: Add API keys per compute instance OR mTLS OR shared secret
   - Files: `serving/routers/auth_router.py`, `compute/base/scripts/credential_monitor.py`

### P1 - Critical UX/Reliability

2. **ERROR-01: Fix useAuth.js error handling - don't bypass auth gate on network errors**
   - Description: Currently treats all fetch errors as "auth disabled" - bypasses gate when server down
   - Impact: Security + UX - users can access app without auth if serving unreachable
   - Solution: Only 404 should bypass gate; network errors should show error page
   - Files: `serving/frontend/src/hooks/useAuth.js`

3. **ERROR-02: Surface backend error messages to frontend**
   - Description: Generic "An error occurred" shown instead of server's specific error message
   - Impact: Users can't troubleshoot issues (e.g., "Claude CLI not found")
   - Solution: Pass `message` field from API error responses through to UI
   - Files: `serving/frontend/src/hooks/useLogin.js`, `serving/routers/auth_router.py`

4. **ERROR-03: Add credential expiration detection and re-auth path in main app**
   - Description: No way to re-authenticate from within app; credentials expire silently
   - Impact: Poor UX - users must restart containers to re-auth
   - Solution: Add re-auth button, continue polling when authenticated, show expiry notification
   - Files: `serving/frontend/src/hooks/useAuth.js`, `serving/frontend/src/App.jsx`

5. **ERROR-04: Add OAuth flow timeout and auto-cancel**
   - Description: Login URLs valid indefinitely - no expiry or timeout
   - Impact: Security risk if URL leaked; orphaned OAuth flows
   - Solution: Add 10-minute timeout, auto-cancel expired flows
   - Files: `serving/services/claude_auth_service.py`

### P2 - UX Polish

6. **UX-01: Add loading screen in App.jsx instead of returning null**
   - Description: Blank screen flash during initial load
   - Solution: Show centered spinner with background color
   - Files: `serving/frontend/src/App.jsx`

7. **UX-02: Add login button disabled/loading state**
   - Description: No loading state on login button - double-click possible
   - Solution: Disable button and show spinner during API call
   - Files: `serving/frontend/src/components/AuthSetupPage.jsx`

8. **UX-03: Add success transition state before showing main app**
   - Description: Abrupt transition after successful auth
   - Solution: Show success message for 2-3 seconds, add fade transition
   - Files: `serving/frontend/src/App.jsx`, `serving/frontend/src/components/AuthSetupPage.jsx`

9. **UX-04: Differentiate "generating URL" vs "waiting for OAuth" states**
   - Description: Single "Login in progress" state not clear
   - Solution: Show different UI for URL generation vs waiting for OAuth completion
   - Files: `serving/frontend/src/components/AuthSetupPage.jsx`, `serving/frontend/src/hooks/useLogin.js`

10. **UX-05: Improve status labels and error messages for end users**
    - Description: Developer-facing labels like "Not configured"
    - Solution: Use action-oriented labels: "Authentication required", "Waiting for authentication..."
    - Files: `serving/frontend/src/components/AuthSetupPage.jsx`

11. **UX-06: Add accessibility attributes**
    - Description: Missing role, aria-label, aria-live attributes
    - Solution: Add role="status", role="alert", aria-labels to spinner/errors
    - Files: `serving/frontend/src/components/AuthSetupPage.jsx`

### P3 - Documentation

12. **DOC-01: Update auth documentation for serving-centric flow**
    - Description: No documentation for new architecture; README outdated
    - Solution: Add `docs/guides/serving-auth-setup.md`, update README
    - Files: `README.md`, new file `docs/guides/serving-auth-setup.md`

---

## Acceptance Criteria Status

| # | Criterion | Status | Notes |
|---|-----------|--------|-------|
| 1 | `docker compose up` shows AuthSetupPage when not authenticated | ✅ PASS | Verified in App.jsx |
| 2 | User can authenticate via UI and access main app | ✅ PASS | OAuth flow works |
| 3 | CLI re-auth script successfully updates credentials | ✅ PASS | Script exists at `scripts/re-auth.sh` |
| 4 | Compute containers fetch credentials on startup | ✅ PASS | Verified in credential_monitor.py |
| 5 | Re-auth triggers SSE broadcast + compute re-fetch | ✅ PASS | SSE event "auth_credentials_updated" |
| 6 | No `~/.claude:/root/.claude:ro` mounts in docker-compose.yml | ✅ PASS | Removed |
| 7 | No conflicting `COMPUTE_AUTH_MODE` env var references | ✅ PASS | Uses `CLAUDE_AUTH_MODE` |
| 8 | Health endpoint includes auth status | ✅ PASS | In `/auth/status` |
| 9 | Works in both dev and CI/CD environments | ❓ UNKNOWN | Not tested |
| 10 | Documentation updated | ❌ FAIL | No docs exist |

**Overall: 8/10 PASS, 1/10 FAIL, 1/10 UNKNOWN**

---

## Recommendations

### Immediate (Before Production)

1. **Add compute authentication to credential endpoint** (SECURITY-01)
   - Priority: P0
   - Blocker for production deployment

2. **Fix useAuth.js error bypass** (ERROR-01)
   - Priority: P1
   - Security + UX issue
   - Only 404 should bypass auth gate

3. **Surface backend error messages to UI** (ERROR-02)
   - Priority: P1
   - Required for troubleshooting

4. **Add credential expiry monitoring in main app** (ERROR-03)
   - Priority: P1
   - Required for long-running sessions

### Next Iteration (UX Improvements)

5. **Add re-auth button/path accessible from main app** (ERROR-03)
   - Priority: P1
   - Improves long-running session UX

6. **Implement OAuth flow timeout** (ERROR-04)
   - Priority: P1
   - 10-minute auto-cancel for security

7. **Add loading/success transition states** (UX-01, UX-03)
   - Priority: P2
   - Reduces perceived load time, confirms success

8. **Improve accessibility** (UX-06)
   - Priority: P2
   - Required for WCAG compliance

9. **Update documentation** (DOC-01)
   - Priority: P2 (or P3)
   - Required for external users

### Future Considerations

10. **Standardize environment variable prefixes to CLAUDEVN_**
    - Priority: P3
    - Improves consistency, not critical

11. **Add OAuth state persistence to Redis**
    - Priority: P2
    - Enables serving restart recovery

---

## Conclusion

The serving-centric auth feature successfully implements the core architecture and works well for local development. However, critical security gaps (unauthenticated credential endpoint) and UX issues (error handling, re-authentication) must be addressed before production use.

**Overall Assessment: FAIL** - 3 critical blockers identified

**Recommended Path Forward:**
1. Fix P0 security issue (SECURITY-01)
2. Fix P1 error handling and re-auth issues (ERROR-01, ERROR-02, ERROR-03, ERROR-04)
3. Address P2 UX polish items for better user experience
4. Update documentation

**Timeline Estimate:**
- P0 fixes: 1-2 days
- P1 fixes: 3-5 days
- P2 fixes: 3-4 days
- Total: ~2 weeks for full remediation

---

## Appendix: Files Reviewed

### Serving
- `serving/app.py`
- `serving/routers/auth_router.py`
- `serving/services/claude_auth_service.py`
- `serving/models/auth.py`
- `serving/frontend/src/App.jsx`
- `serving/frontend/src/components/AuthSetupPage.jsx`
- `serving/frontend/src/hooks/useAuth.js`
- `serving/frontend/src/hooks/useLogin.js`

### Compute
- `compute/base/entrypoint.sh`
- `compute/base/scripts/credential_monitor.py`

### Infrastructure
- `docker-compose.yml`
- `serving/Dockerfile`

### Tests
- `serving/tests/unit/services/test_claude_auth_service.py`
- `serving/tests/unit/routers/test_auth_router.py`
- `serving/tests/unit/models/test_auth.py`
- `compute/base/tests/unit/test_credential_monitor.py`

**Total Files Reviewed: 17**

---

**Audit completed:** 2026-02-14
**Next audit recommended:** After P0/P1 issues resolved
