# CYBERGUARD API Regression Matrix

Run: 2026-09-09 01:05:01 against `http://localhost:8000/api/v1`

**Result: 24 passed, 0 failed**

| # | Assertion | Result | Detail |
|---|-----------|--------|--------|
| 1 | Supabase password grant login | PASS | no access_token |
| 2 | GET /dashboard/summary 200 with numeric counters | PASS | status 200 |
| 3 | GET /auth/me returns role admin | PASS | status 200 role=admin |
| 4 | POST /analysis/email malicious -> severity high|critical | PASS | status 200 severity=critical |
| 5 | POST /analysis/email benign -> severity safe|low | PASS | status 200 severity=safe |
| 6 | POST /analysis/url malicious -> severity high|critical | PASS | status 200 severity=high |
| 7 | POST /analysis/url benign -> severity safe|low | PASS | status 200 severity=safe |
| 8 | POST /analysis/impersonation fake-CEO -> severity high|critical | PASS | status 200 severity=critical |
| 9 | POST /analysis/account-takeover impossible-travel -> severity high|critical | PASS | status 200 severity=high |
| 10 | POST /analysis/network C2 port 4444 -> risk_score >= 40 | PASS | status 200 score=40 |
| 11 | POST /analysis/media upload -> 200 with manipulation_probability | PASS | status 200 |
| 12 | GET /alerts non-empty | PASS | status 200 count=50 |
| 13 | GET /alerts/{id} 200 (id=db4c298c-a5bb-4fb1-a6c6-bf0a74962729) | PASS | status 200 |
| 14 | PATCH /alerts/{id}/status acknowledged 200 | PASS | status 200 |
| 15 | POST /incidents 201 (linked to alert) | PASS | status 201 |
| 16 | PATCH /incidents/{id}/status investigating 200 | PASS | status 200 |
| 17 | POST /incidents/{id}/escalate 200 | PASS | status 200 |
| 18 | Incident timeline grows after mutations | PASS | before=1 after=3 |
| 19 | GET /responses/catalog non-empty | PASS | status 200 count=10 |
| 20 | POST /responses/execute without approval -> 403 | PASS | status 403 |
| 21 | POST /responses/execute with approval -> 200 | PASS | status 200 |
| 22 | GET /audit/logs non-empty and includes mutations | PASS | status 200 count=3 contains_alert=True |
| 23 | POST /assistant/chat returns non-empty reply | PASS | status 200 |
| 24 | GET /admin/users lists the admin email | PASS | status 200 |
