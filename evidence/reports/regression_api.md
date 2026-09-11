# CYBERGUARD API Regression Matrix

Run: 2026-09-11 07:21:36 against `http://localhost:8000/api/v1`

**Result: 49 passed, 0 failed**

| # | Assertion | Result | Detail |
|---|-----------|--------|--------|
| 1 | Supabase password grant login | PASS | no access_token |
| 2 | GET /health shallow liveness 200 | PASS | status 200 |
| 3 | GET /health/deep authenticated diagnostics 200 | PASS | status 200 |
| 4 | GET /dashboard/summary 200 with numeric counters | PASS | status 200 |
| 5 | GET /auth/me returns role admin | PASS | status 200 role=admin |
| 6 | POST /analysis/email malicious -> severity high|critical | PASS | status 200 severity=critical |
| 7 | POST /analysis/email benign -> severity safe|low | PASS | status 200 severity=safe |
| 8 | POST /analysis/email account-review.example.com -> severity >= medium | PASS | status 200 severity=medium |
| 9 | POST /analysis/email account-review.example.com explanation leading band matches final band | PASS | explanation='Medium Risk: The email originates from a' |
| 10 | POST /analysis/email benign preset -> severity safe|low | PASS | status 200 severity=safe |
| 11 | POST /analysis/email hi phishing -> severity high|critical + lang indicator | PASS | status 200 severity=critical lang_present=True |
| 12 | POST /analysis/email te phishing -> severity high|critical + lang indicator | PASS | status 200 severity=critical lang_present=True |
| 13 | POST /analysis/email or phishing -> severity high|critical + lang indicator | PASS | status 200 severity=critical lang_present=True |
| 14 | POST /analysis/email benign Hindi -> severity safe|low + lang indicator | PASS | status 200 severity=safe lang_present=True |
| 15 | POST /analysis/url malicious -> severity high|critical | PASS | status 200 severity=high |
| 16 | POST /analysis/url benign -> severity safe|low | PASS | status 200 severity=safe |
| 17 | POST /analysis/url chatgpt conversation link -> severity safe|low | PASS | status 200 severity=safe |
| 18 | POST /analysis/url drive share link -> severity safe|low | PASS | status 200 severity=safe |
| 19 | POST /analysis/url youtube link -> severity safe|low | PASS | status 200 severity=safe |
| 20 | POST /analysis/url malicious URLhaus 2 -> severity high|critical | PASS | status 200 severity=high |
| 21 | POST /analysis/impersonation fake-CEO -> severity high|critical | PASS | status 200 severity=critical |
| 22 | POST /analysis/impersonation benign-CFO -> severity <= medium | PASS | status 200 severity=low |
| 23 | POST /analysis/impersonation benign-CFO explanation leading band matches final band | PASS | explanation='Low Risk: Automated explanation is tempo' |
| 24 | POST /analysis/account-takeover impossible-travel -> severity high|critical | PASS | status 200 severity=high |
| 25 | POST /analysis/network C2 port 4444 -> risk_score >= 40 | PASS | status 200 score=41 |
| 26 | POST /analysis/media upload -> 200 sync | 202 queued | PASS | status 200 |
| 27 | POST /analysis/media manipulated.png -> severity high|critical | PASS | status 200 severity=high |
| 28 | POST /analysis/media real_camera_whatsapp.jpg -> severity safe|low | PASS | status 200 severity=safe |
| 29 | POST /analysis/media real_camera_whatsapp.jpg explanation leading band matches final band | PASS | explanation='Safe Risk: Automated explanation is temp' |
| 30 | POST /analysis/media erew.jpeg -> severity safe|low | PASS | status 200 severity=low |
| 31 | GET /alerts non-empty | PASS | status 200 count=50 |
| 32 | GET /alerts/{id} 200 (id=dc9179e0-f448-49e7-8472-b87af52bd04e) | PASS | status 200 |
| 33 | PATCH /alerts/{id}/status acknowledged 200 | PASS | status 200 |
| 34 | POST /incidents 201 (linked to alert) | PASS | status 201 |
| 35 | PATCH /incidents/{id}/status TRIAGE -> CONTAINMENT 200 | PASS | status 200 got=CONTAINMENT |
| 36 | PATCH /incidents/{id}/status CONTAINMENT -> ERADICATION 200 | PASS | status 200 got=ERADICATION |
| 37 | PATCH /incidents/{id}/status ERADICATION -> RECOVERY 200 | PASS | status 200 got=RECOVERY |
| 38 | PATCH /incidents/{id}/status RECOVERY -> CLOSED 200 | PASS | status 200 got=CLOSED |
| 39 | PATCH /incidents/{id}/status TRIAGE -> RECOVERY 400 | PASS | status 400 detail=Cannot transition from TRIAGE to RECOVERY. Must go through CONTAINMENT and ERADICATION first. |
| 40 | POST /incidents/{id}/escalate 200 | PASS | status 200 |
| 41 | Incident timeline grows after mutations | PASS | before=1 after=6 |
| 42 | GET /responses/catalog non-empty | PASS | status 200 count=10 |
| 43 | POST /responses/execute without approval -> 403 | PASS | status 403 |
| 44 | POST /responses/execute with approval -> 200 | PASS | status 200 |
| 45 | GET /audit/logs non-empty and includes mutations | PASS | status 200 count=25 contains_alert=True |
| 46 | POST /assistant/chat returns non-empty reply | PASS | status 200 |
| 47 | GET /admin/users lists the admin email | PASS | status 200 |
| 48 | Cross-tenant event GET -> 404 | PASS | status 404 |
| 49 | Cross-tenant media re-analysis -> 404 | PASS | status 404 |
