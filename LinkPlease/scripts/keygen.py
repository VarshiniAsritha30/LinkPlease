#!/usr/bin/env python3
"""
Helper script to apply for and generate an API key from the Pseudogram Mock API.
"""

import sys
import httpx

BASE_URL = "https://pseudogram-api.onrender.com"


def main():
    print("Generating Pseudogram API Key...")
    name = "Vijay Kumar"
    email = "vijay@example.com"

    apply_payload = {
        "name": name,
        "email": email,
        "phone": "+919876543210",
        "whatsapp": "+919876543210",
        "linkedin_url": "https://linkedin.com/in/vijaykumar"
    }

    with httpx.Client(timeout=30.0) as client:
        # Step 1: Apply
        print(f"Applying at {BASE_URL}/v1/apply...")
        try:
            r = client.post(f"{BASE_URL}/v1/apply", json=apply_payload)
            print(f"Apply status: {r.status_code}, response: {r.text}")
        except Exception as e:
            print(f"Apply request failed: {e}")

        # Step 2: Keygen
        print(f"Generating key at {BASE_URL}/v1/keygen...")
        try:
            r = client.post(f"{BASE_URL}/v1/keygen", json={"email": email})
            print(f"Keygen status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                api_key = data.get("api_key")
                print("\n==========================================")
                print(f"SUCCESS! Your Pseudogram API Key:")
                print(f"PSEUDOGRAM_API_KEY={api_key}")
                print("==========================================\n")
            else:
                print(f"Keygen failed: {r.text}")
        except Exception as e:
            print(f"Keygen request failed: {e}")


if __name__ == "__main__":
    main()
