#!/usr/bin/env python3
"""
Manual local verification script for testing LinkPlease features step-by-step.
Usage:
    python scripts/manual_test.py [BASE_URL]
"""

import sys
import time
import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    print(f"=== Starting LinkPlease Manual Verification against {base_url} ===")

    with httpx.Client(timeout=10.0) as client:
        # Step 1: Health check / docs
        print("\n1. Testing GET /docs...")
        r = client.get(f"{base_url}/docs")
        print(f"   Status: {r.status_code} {'OK' if r.status_code == 200 else 'FAIL'}")

        # Step 2: Create Rule
        print("\n2. Creating Rule 'PRICE'...")
        rule_payload = {
            "keyword": "PRICE",
            "dm_message": "Here is our official price list: https://example.com/price"
        }
        r = client.post(f"{base_url}/rules", json=rule_payload)
        print(f"   Status: {r.status_code}, Response: {r.json()}")
        rule_id = r.json().get("rule_id")

        # Step 3: Send Webhook Event 1 (New User)
        print("\n3. Sending Webhook Event (User 1 - price query)...")
        evt1 = {
            "event_id": f"evt_manual_1_{int(time.time())}",
            "event_type": "comment.created",
            "sent_at": "2026-08-16T10:00:00Z",
            "data": {
                "comment_id": f"cmt_manual_1_{int(time.time())}",
                "post_id": "post_101",
                "text": "What is the PRICE please?",
                "created_at": "2026-08-16T10:00:00Z",
                "from": {
                    "user_id": "usr_manual_101",
                    "username": "tester_1"
                }
            }
        }
        r = client.post(f"{base_url}/webhook", json=evt1)
        print(f"   Status: {r.status_code}, Response: {r.json()}")

        # Step 4: Duplicate Event ID
        print("\n4. Resending Exact Same Event ID (Duplicate Event Test)...")
        r = client.post(f"{base_url}/webhook", json=evt1)
        print(f"   Status: {r.status_code}, Response: {r.json()}")

        # Step 5: Same User, Different Comment (User Uniqueness Test)
        print("\n5. Sending Second Comment from Same User (Duplicate DM Block Test)...")
        evt2 = {
            "event_id": f"evt_manual_2_{int(time.time())}",
            "event_type": "comment.created",
            "data": {
                "comment_id": f"cmt_manual_2_{int(time.time())}",
                "text": "PRICE list link again please",
                "from": {
                    "user_id": "usr_manual_101",
                    "username": "tester_1"
                }
            }
        }
        r = client.post(f"{base_url}/webhook", json=evt2)
        print(f"   Status: {r.status_code}, Response: {r.json()}")

        # Step 6: Wait & Inspect Stats
        print("\n6. Waiting 3 seconds for background worker processing...")
        time.sleep(3)

        print("\n7. Inspecting GET /stats...")
        r = client.get(f"{base_url}/stats")
        print(f"   Stats Output: {r.json()}")

    print("\n=== Manual Verification Completed Successfully ===")


if __name__ == "__main__":
    main()
