#!/usr/bin/env python3
"""
Quick smoke tests for production security hardening.
Tests: security headers, input validation, rate limiting, health check.

Usage:
  python3 scripts/test_security.py                          # test production
  python3 scripts/test_security.py http://localhost:5001    # test locally
"""
import sys
import requests
import time

BASE_URL = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else "https://kyll-portfolio-production.up.railway.app"

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94m→\033[0m"

def check(label, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  {status} {label}" + (f"  ({detail})" if detail else ""))
    return condition


print(f"\n{'='*55}")
print(f"  Security Tests — {BASE_URL}")
print(f"{'='*55}")


# ── 1. Health Check ──────────────────────────────────────
print(f"\n{INFO} Health Check")
r = requests.get(f"{BASE_URL}/api/health")
check("Returns 200", r.status_code == 200, f"got {r.status_code}")
data = r.json()
check("Status healthy", data.get("status") == "healthy", data.get("status"))
check("Database ok", data.get("checks", {}).get("database", {}).get("status") == "ok")
check("OpenAI configured", data.get("checks", {}).get("openai") == "configured")


# ── 2. Security Headers ──────────────────────────────────
print(f"\n{INFO} Security Headers")
headers = r.headers
check("X-Content-Type-Options", headers.get("X-Content-Type-Options") == "nosniff",
      headers.get("X-Content-Type-Options"))
check("X-Frame-Options", headers.get("X-Frame-Options") == "DENY",
      headers.get("X-Frame-Options"))
check("X-XSS-Protection", "1" in headers.get("X-XSS-Protection", ""),
      headers.get("X-XSS-Protection"))
check("Referrer-Policy", bool(headers.get("Referrer-Policy")),
      headers.get("Referrer-Policy"))


# ── 3. Input Validation ──────────────────────────────────
print(f"\n{INFO} Input Validation")

# Empty message
r = requests.post(f"{BASE_URL}/api/chat/message",
                  json={"message": "", "conversation_id": None})
check("Rejects empty message", r.status_code == 400, f"got {r.status_code}")

# Message too long (>2000 chars)
r = requests.post(f"{BASE_URL}/api/chat/message",
                  json={"message": "x" * 2001})
check("Rejects message >2000 chars", r.status_code == 400, f"got {r.status_code}")

# Invalid visitor_id in analytics (special chars)
r = requests.post(f"{BASE_URL}/api/analytics/track",
                  json={"visitor_id": "<script>alert(1)</script>", "page": "/test"})
check("Rejects XSS in visitor_id", r.status_code == 400, f"got {r.status_code}")

# Invalid page path
r = requests.post(f"{BASE_URL}/api/analytics/track",
                  json={"visitor_id": "test-visitor", "page": "'; DROP TABLE page_views;--"})
check("Rejects SQL injection in page", r.status_code == 400, f"got {r.status_code}")

# Valid analytics track
r = requests.post(f"{BASE_URL}/api/analytics/track",
                  json={"visitor_id": "test-visitor-123", "page": "/test"})
check("Accepts valid analytics data", r.status_code == 200, f"got {r.status_code}")


# ── 4. Rate Limiting ─────────────────────────────────────
print(f"\n{INFO} Rate Limiting (analytics endpoint — 60/min limit)")
print(f"     Sending 65 rapid requests...")

hit_limit = False
for i in range(65):
    r = requests.post(f"{BASE_URL}/api/analytics/track",
                      json={"visitor_id": f"rate-test-{i}", "page": "/test"})
    if r.status_code == 429:
        hit_limit = True
        check("Rate limit triggered at 429", True, f"after {i+1} requests")
        break

if not hit_limit:
    check("Rate limit triggered", False, "sent 65 requests, never got 429")


# ── 5. Admin Login Rate Limiting ─────────────────────────
print(f"\n{INFO} Admin Login Rate Limiting (5/min limit)")
print(f"     Sending 7 bad login attempts...")

hit_limit = False
for i in range(7):
    r = requests.post(f"{BASE_URL}/api/admin/login",
                      data={"username": "wrong", "password": "wrong"})
    if r.status_code == 429:
        hit_limit = True
        check("Login rate limit triggered at 429", True, f"after {i+1} attempts")
        break
    time.sleep(0.1)

if not hit_limit:
    check("Login rate limit triggered", False, "sent 7 requests, never got 429")


# ── Summary ──────────────────────────────────────────────
print(f"\n{'='*55}\n")
