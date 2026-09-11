# CYBERGUARD API Regression Matrix

Run: 2026-09-11 22:42:20 against `http://localhost:8000/api/v1`

**Result: 51 passed, 5 failed**

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
| 9 | POST /analysis/email account-review.example.com explanation leading band matches final band | PASS | explanation='Medium Risk: Automated explanation is te' |
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
| 31 | POST /analysis/media ercv.mp3 -> 200 sync | 202 queued | PASS | status 200 |
| 32 | POST /analysis/media ercv.mp3 -> severity in ('medium', 'high', 'critical') | PASS | severity=critical ml_model=['audio_cnn_v1.pt'] simulated=False |
| 33 | POST /analysis/media ercv.mp3 -> ml_model audio_cnn_v1.pt and simulated false | PASS | ml_model=['audio_cnn_v1.pt'] simulated=False |
| 34 | POST /analysis/media tone.wav -> 200 sync | 202 queued | PASS | status 200 |
| 35 | POST /analysis/media tone.wav -> severity in ('safe', 'low') | PASS | severity=low ml_model=['audio_cnn_v1.pt'] simulated=False |
| 36 | POST /analysis/media real_speech.wav -> 200 sync | 202 queued | PASS | status 200 |
| 37 | POST /analysis/media real_speech.wav -> severity in ('safe', 'low') | PASS | severity=safe ml_model=['audio_cnn_v1.pt'] simulated=False |
| 38 | GET /alerts non-empty | PASS | status 200 count=50 |
| 39 | GET /alerts/{id} 200 (id=26b1f429-d6c3-4f84-bfd9-01624d38be1c) | PASS | status 200 |
| 40 | PATCH /alerts/{id}/status acknowledged 200 | PASS | status 200 |
| 41 | POST /incidents 201 (linked to alert) | PASS | status 201 |
| 42 | PATCH /incidents/{id}/status TRIAGE -> CONTAINMENT 200 | FAIL | status 500 got=None |
| 43 | PATCH /incidents/{id}/status CONTAINMENT -> ERADICATION 200 | FAIL | status 500 got=None |
| 44 | PATCH /incidents/{id}/status ERADICATION -> RECOVERY 200 | FAIL | status 500 got=None |
| 45 | PATCH /incidents/{id}/status RECOVERY -> CLOSED 200 | FAIL | status 500 got=None |
| 46 | PATCH /incidents/{id}/status TRIAGE -> RECOVERY 400 | FAIL | status 500 detail=None |
| 47 | POST /incidents/{id}/escalate 200 | PASS | status 200 |
| 48 | Incident timeline grows after mutations | PASS | before=1 after=2 |
| 49 | GET /responses/catalog non-empty | PASS | status 200 count=10 |
| 50 | POST /responses/execute without approval -> 403 | PASS | status 403 |
| 51 | POST /responses/execute with approval -> 200 | PASS | status 200 |
| 52 | GET /audit/logs non-empty and includes mutations | PASS | status 200 count=35 contains_alert=True |
| 53 | POST /assistant/chat returns non-empty reply | PASS | status 200 |
| 54 | GET /admin/users lists the admin email | PASS | status 200 |
| 55 | Cross-tenant event GET -> 404 | PASS | status 404 |
| 56 | Cross-tenant media re-analysis -> 404 | PASS | status 404 |
