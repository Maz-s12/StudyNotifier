import requests
import os
import json

SURVEYMONKEY_TOKEN = "rrO-QkyQB7hoLX17Fl9GSOzWZzXnvh5W.krUjNy-LT2WPdHtwCNB3OXX8M-TjKOSVwPnrvXA6ikBEz9-IAKMG4UZwOjOuNoHANxgQ9DDPn.o09xZnFAx29vGg2SXPiLv"
SURVEY_ID = "190470633"
SEEN_RESPONSES_FILE = "seen_responses.json"

def get_all_responses():
    headers = {
        "Authorization": f"Bearer {SURVEYMONKEY_TOKEN}",
        "Content-Type": "application/json"
    }

    url = f"https://api.surveymonkey.ca/v3/surveys/{SURVEY_ID}/responses/bulk"
    resp = requests.get(url, headers=headers)

    print("🔍 Raw response:")
    print(resp.status_code)
    print(json.dumps(resp.json(), indent=2))

    return [r["id"] for r in resp.json().get("data", [])]

def save_seen_responses(ids):
    with open(SEEN_RESPONSES_FILE, "w") as f:
        json.dump(list(ids), f)
    print(f"✅ Bootstrapped {len(ids)} responses into seen list.")

if __name__ == "__main__":
    seen_ids = get_all_responses()
    save_seen_responses(seen_ids)