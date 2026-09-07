#!/usr/bin/env bash
# Usage: bash scripts/test_samples.sh <bearer_token> [base_url]
TOKEN="$1"; BASE="${2:-http://localhost:8000/api/v1}"
show() { python3 -c "import sys,json;d=json.load(sys.stdin);print('severity=',d.get('severity'),' score=',d.get('risk_score'),' type=',d.get('threat_type'))"; }
post() { curl -s -X POST "$BASE/$1" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$2" | show; }

echo "[1] phishing critical   "; post analysis/email '{"sender":"security-alert@micr0soft-verify.xyz","subject":"URGENT: Verify your account immediately","body":"Your account will be suspended within 24 hours. Click here http://185.220.101.7/login to verify your password and restore access."}'
echo "[2] phishing benign     "; post analysis/email '{"sender":"registrar@university.edu","subject":"Examination timetable published","body":"The timetable is on the student portal. No password or payment information is required."}'
echo "[3] url malicious       "; post analysis/url '{"url":"http://secure-account-verification.micr0soft-support.xyz/auth/session?id=88213"}'
echo "[4] url benign          "; post analysis/url '{"url":"https://www.github.com/login"}'
echo "[5] impersonation CEO   "; post analysis/impersonation '{"claimed_identity":"Chief Executive Officer","message":"Urgent and confidential. Purchase three gift cards and send me the codes. Do not inform finance."}'
echo "[6] impersonation benign"; post analysis/impersonation '{"claimed_identity":"Team Lead","message":"Please submit weekly reports by Friday. Template is in the shared drive."}'
echo "[7] account takeover    "; post analysis/account-takeover '{"events":[{"user":"john.doe","ip":"10.0.1.45","location":"New York, US","device":"Windows-Chrome","status":"success","timestamp":"2026-09-08T09:00:00Z"},{"user":"john.doe","ip":"185.220.101.7","location":"Moscow, RU","device":"Linux-Firefox","status":"failed","timestamp":"2026-09-08T09:35:00Z"},{"user":"john.doe","ip":"185.220.101.7","location":"Moscow, RU","device":"Linux-Firefox","status":"failed","timestamp":"2026-09-08T09:35:30Z"},{"user":"john.doe","ip":"185.220.101.7","location":"Moscow, RU","device":"Linux-Firefox","status":"failed","timestamp":"2026-09-08T09:36:00Z"},{"user":"john.doe","ip":"185.220.101.7","location":"Moscow, RU","device":"Linux-Firefox","status":"success","timestamp":"2026-09-08T09:37:00Z"}]}'
echo "[8] network attack      "; post analysis/network '{"flows":[{"source_ip":"192.168.1.50","dest_ip":"45.33.32.156","port":4444,"bytes_out":15000000,"protocol":"TCP"}],"api_logs":[]}'
echo "[9] media manipulated   "; curl -s -F "file=@../evidence/media/manipulated.png" -H "Authorization: Bearer $TOKEN" "$BASE/analysis/media" | show
echo "[10] media benign       "; curl -s -F "file=@../evidence/media/benign.png" -H "Authorization: Bearer $TOKEN" "$BASE/analysis/media" | show
