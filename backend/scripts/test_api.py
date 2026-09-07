import requests
import json
import sys

# --- CONFIGURATION (read from environment; never hardcode secrets) ---
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://YOUR-PROJECT.supabase.co")
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "your-anon-key")
PASSWORD = os.environ.get("CYBERGUARD_PASSWORD", "")
EMAIL = os.environ.get("CYBERGUARD_EMAIL", "admin@cyberguard.local")
BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")

if not PASSWORD:
    sys.exit("Set CYBERGUARD_PASSWORD (plus SUPABASE_URL / SUPABASE_ANON_KEY) environment variables first.")
# ---------------------------------------------

def get_token():
    print("🔐 Fetching Supabase Auth Token...")
    res = requests.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                        headers={"apikey": ANON_KEY, "Content-Type": "application/json"},
                        json={"email": EMAIL, "password": PASSWORD})
    if res.status_code != 200:
        print(f"❌ Failed to get token: {res.status_code} - {res.text}")
        sys.exit(1)
    print("✅ Token acquired successfully.\n")
    return res.json()["access_token"]

def test_endpoint(name, url, payload, headers):
    print(f"🚀 Testing: {name}")
    try:
        res = requests.post(url, headers=headers, json=payload)
        print(f"   Status: {res.status_code}")
        if res.ok:
            data = res.json()
            print(f"   Severity: {data.get('severity')} | Score: {data.get('risk_score')}")
            print(f"   Explanation: {data.get('explanation', '')[:100]}...")
        else:
            print(f"   ❌ Error: {res.text}")
    except Exception as e:
        print(f"   ❌ Connection Error: {e} (Is the backend running on port 8000?)")
    print("-" * 50)

def main():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Phishing (Critical)
    test_endpoint("Phishing (Critical)", f"{BASE_URL}/analysis/email", {
        "sender": "security-alert@micr0soft-verify.xyz",
        "subject": "URGENT: Verify your account immediately",
        "body": "Your account will be suspended. Click http://185.220.101.7/login to verify."
    }, headers)

    # 2. Phishing (Benign)
    test_endpoint("Phishing (Benign)", f"{BASE_URL}/analysis/email", {
        "sender": "registrar@university.edu",
        "subject": "Examination timetable published",
        "body": "The timetable is on the student portal. No action required."
    }, headers)

    # 3. Impersonation (CEO)
    test_endpoint("Impersonation (CEO)", f"{BASE_URL}/analysis/impersonation", {
        "claimed_identity": "Chief Executive Officer",
        "message": "Urgent and confidential. Purchase three gift cards and send me the codes. Do not inform finance."
    }, headers)

    # 4. Account Takeover (Impossible Travel)
    test_endpoint("Account Takeover", f"{BASE_URL}/analysis/account-takeover", {
        "events": [
            {"user": "john", "ip": "10.0.0.1", "location": "US", "device": "Win", "status": "success", "timestamp": "2026-09-08T09:00:00Z"},
            {"user": "john", "ip": "185.220.101.7", "location": "RU", "device": "Linux", "status": "failed", "timestamp": "2026-09-08T09:35:00Z"},
            {"user": "john", "ip": "185.220.101.7", "location": "RU", "device": "Linux", "status": "success", "timestamp": "2026-09-08T09:36:00Z"}
        ]
    }, headers)

    # 5. Network Attack (C2 Port)
    test_endpoint("Network Attack", f"{BASE_URL}/analysis/network", {
        "flows": [{"source_ip": "192.168.1.50", "dest_ip": "45.33.32.156", "port": 4444, "bytes_out": 15000000, "protocol": "TCP"}],
        "api_logs": []
    }, headers)

if __name__ == "__main__":
    main()
