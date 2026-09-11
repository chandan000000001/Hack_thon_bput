# CYBERGUARD API Regression Matrix

Run: 2026-09-11 05:25:41 against `http://localhost:8000/api/v1`

**Result: 41 passed, 0 failed**

| # | Assertion | Result | Detail |
|---|-----------|--------|--------|
| 1 | Supabase password grant login | PASS | no access_token |
| 2 | GET /health shallow liveness 200 | PASS | status 200 |
| 3 | GET /health/deep authenticated diagnostics 200 | PASS | status 200 |
| 4 | GET /dashboard/summary 200 with numeric counters | PASS | status 200 |
| 5 | GET /auth/me returns role admin | PASS | status 200 role=admin |
| 6 | POST /analysis/email malicious -> severity high|critical | PASS | status 200 severity=critical |
| 7 | POST /analysis/email benign -> severity safe|low | PASS | status 200 severity=safe |
| 8 | POST /analysis/email hi phishing -> severity high|critical + lang indicator | PASS | status 200 severity=critical lang_present=True |
| 9 | POST /analysis/email te phishing -> severity high|critical + lang indicator | PASS | status 200 severity=critical lang_present=True |
| 10 | POST /analysis/email or phishing -> severity high|critical + lang indicator | PASS | status 200 severity=critical lang_present=True |
| 11 | POST /analysis/email benign Hindi -> severity safe|low + lang indicator | PASS | status 200 severity=safe lang_present=True |
| 12 | POST /analysis/url malicious -> severity high|critical | PASS | status 200 severity=high |
| 13 | POST /analysis/url benign -> severity safe|low | PASS | status 200 severity=safe |
| 14 | POST /analysis/impersonation fake-CEO -> severity high|critical | PASS | status 200 severity=critical |
| 15 | POST /analysis/impersonation benign-CFO -> severity <= medium | PASS | status 200 severity=low |
| 16 | POST /analysis/impersonation benign-CFO explanation leading band matches final band | PASS | explanation='Low Risk: The message exhibits typical a' |
| 17 | POST /analysis/account-takeover impossible-travel -> severity high|critical | PASS | status 200 severity=high |
| 18 | POST /analysis/network C2 port 4444 -> risk_score >= 40 | PASS | status 200 score=40 |
| 19 | POST /analysis/media upload -> 200 sync | 202 queued | PASS | status 200 |
| 20 | POST /analysis/media manipulated.png -> severity high|critical | PASS | status 200 severity=high |
| 21 | POST /analysis/media real_camera_whatsapp.jpg -> severity safe|low | PASS | status 200 severity=safe |
| 22 | POST /analysis/media real_camera_whatsapp.jpg explanation leading band matches final band | PASS | explanation='Safe Risk: The image achieves a 0.95 aut' |
| 23 | GET /alerts non-empty | PASS | status 200 count=50 |
| 24 | GET /alerts/{id} 200 (id=f4137c47-acfc-4651-b827-b858db17c779) | PASS | status 200 |
| 25 | PATCH /alerts/{id}/status acknowledged 200 | PASS | status 200 |
| 26 | POST /incidents 201 (linked to alert) | PASS | status 201 |
| 27 | PATCH /incidents/{id}/status TRIAGE -> CONTAINMENT 200 | PASS | status 200 got=CONTAINMENT |
| 28 | PATCH /incidents/{id}/status CONTAINMENT -> ERADICATION 200 | PASS | status 200 got=ERADICATION |
| 29 | PATCH /incidents/{id}/status ERADICATION -> RECOVERY 200 | PASS | status 200 got=RECOVERY |
| 30 | PATCH /incidents/{id}/status RECOVERY -> CLOSED 200 | PASS | status 200 got=CLOSED |
| 31 | PATCH /incidents/{id}/status TRIAGE -> RECOVERY 400 | PASS | status 400 detail=Cannot transition from TRIAGE to RECOVERY. Must go through CONTAINMENT and ERADICATION first. |
| 32 | POST /incidents/{id}/escalate 200 | PASS | status 200 |
| 33 | Incident timeline grows after mutations | PASS | before=1 after=6 |
| 34 | GET /responses/catalog non-empty | PASS | status 200 count=10 |
| 35 | POST /responses/execute without approval -> 403 | PASS | status 403 |
| 36 | POST /responses/execute with approval -> 200 | PASS | status 200 |
| 37 | GET /audit/logs non-empty and includes mutations | PASS | status 200 count=23 contains_alert=True |
| 38 | POST /assistant/chat returns non-empty reply | PASS | status 200 |
| 39 | GET /admin/users lists the admin email | PASS | status 200 |
| 40 | Cross-tenant event GET -> 404 | PASS | status 404 |
| 41 | Cross-tenant media re-analysis -> 404 | PASS | status 404 |
