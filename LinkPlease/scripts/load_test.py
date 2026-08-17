#!/usr/bin/env python3
"""
500-Event Load Test & Simulator Verification Script for LinkPlease.
Triggers the Pseudogram API simulator endpoint, polls truth metrics, 
and compares them against application /stats.
"""

import sys
import time
import json
import httpx

SIMULATE_BASE_URL = "https://pseudogram-api.onrender.com"


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/load_test.py <YOUR_APP_WEBHOOK_URL> <PSEUDOGRAM_API_KEY>")
        print("Example: python scripts/load_test.py https://my-app.onrender.com/webhook key_abc123")
        sys.exit(1)

    webhook_url = sys.argv[1]
    api_key = sys.argv[2]
    app_base_url = webhook_url.rsplit("/webhook", 1)[0]

    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    print("==================================================")
    print("      LinkPlease 500-Event Load Test Suite       ")
    print("==================================================")
    print(f"Target App Webhook: {webhook_url}")
    print(f"Target App Base URL: {app_base_url}")
    print(f"Simulator Service:  {SIMULATE_BASE_URL}")

    with httpx.Client(timeout=30.0) as client:
        # Step 1: Start simulation
        sim_payload = {
            "webhook_url": webhook_url,
            "count": 500,
            "duration_seconds": 10
        }
        print("\n[1/3] Triggering simulator: POST /v1/simulate/start...")
        try:
            r = client.post(f"{SIMULATE_BASE_URL}/v1/simulate/start", json=sim_payload, headers=headers)
            print(f"      Simulator Start HTTP Status: {r.status_code}")
            if r.status_code not in (200, 201, 202):
                print(f"      Simulator Start Error: {r.text}")
                sys.exit(1)
            
            sim_data = r.json()
            run_id = sim_data.get("run_id")
            print(f"      Simulation started with run_id: {run_id}")
        except Exception as e:
            print(f"      Failed to trigger simulation: {e}")
            sys.exit(1)

        # Step 2: Poll simulation status until complete
        print("\n[2/3] Waiting for simulation to complete and processing queue...")
        truth_data = None
        for attempt in range(60):
            time.sleep(3)
            try:
                truth_res = client.get(f"{SIMULATE_BASE_URL}/v1/simulate/{run_id}/truth", headers=headers)
                if truth_res.status_code == 200:
                    truth_data = truth_res.json()
                    status = truth_data.get("status", "running")
                    print(f"      Polling simulation status: {status} (elapsed: {(attempt+1)*3}s)...")
                    if status in ("completed", "finished", "done"):
                        break
            except Exception as e:
                print(f"      Polling error: {e}")

        print("\n[3/3] Fetching application /stats to compare results...")
        try:
            stats_res = client.get(f"{app_base_url}/stats")
            stats = stats_res.json() if stats_res.status_code == 200 else {}
        except Exception as e:
            print(f"      Failed to fetch /stats: {e}")
            stats = {}

        print("\n==================================================")
        print("                 LOAD TEST REPORT                 ")
        print("==================================================")
        print("Simulator Ground Truth:")
        print(json.dumps(truth_data, indent=2) if truth_data else "  N/A")
        print("\nApplication /stats Output:")
        print(json.dumps(stats, indent=2))
        print("==================================================")


if __name__ == "__main__":
    main()
