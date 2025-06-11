# study_email_bot.py
import os
import imaplib
from flask import Flask, request
import smtplib
from email.message import EmailMessage
from openai import OpenAI
import json
import requests
from dotenv import load_dotenv
import time
import threading
import ast

SEEN_RESPONSES_FILE = "seen_responses.json"



def poll_survey_responses():
    print("🔄 Checking for new eligible responses...")

    seen = load_seen_responses()
    new_seen = set(seen)

    print(f"🧠 Seen responses: {len(seen)}")
    responses = get_surveymonkey_responses()
    print(f"📦 Total responses fetched: {len(responses)}")

    for resp in responses:
        resp_id = resp.get("id")
        is_new = resp_id not in seen
        eligible = is_response_eligible(resp)

        print(f"🔍 Response ID: {resp_id} | New: {is_new} | Eligible: {eligible}")

        if is_new and eligible:
            analyze_url = resp.get("analyze_url", "No link")
            summary_text = summarize_answers(resp)
            summary = {
                "summary": summary_text,
                "link": analyze_url,
                "id": resp_id
            }

            print("📬 Sending to /notify:", json.dumps(summary, indent=2))
            response = requests.post(f"{WEBHOOK_BASE}/notify", json=summary)

            new_seen.add(resp_id)

    if new_seen != seen:
        print(f"💾 Updating seen responses file with {len(new_seen)} IDs")
        save_seen_responses(new_seen)
    else:
        print("✅ No new responses to process.")

    # Re-run in 6 hours (or shorter for testing)
    t = threading.Timer(21600, poll_survey_responses)
    t.daemon = True
    t.start()
    
def load_seen_responses():
    if os.path.exists(SEEN_RESPONSES_FILE):
        with open(SEEN_RESPONSES_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_responses(ids):
    with open(SEEN_RESPONSES_FILE, "w") as f:
        json.dump(list(ids), f)
load_dotenv()
POWER_AUTOMATE_WEBHOOK = os.getenv("POWER_AUTOMATE")
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_auth = os.getenv("TWILIO_AUTH_TOKEN")
twilio_phone = os.getenv("TWILIO_PHONE")
your_phone = os.getenv("YOUR_PHONE")
SURVEYMONKEY_TOKEN = os.getenv("SURVEYMONKEY_TOKEN")
SURVEY_ID = os.getenv("YOUR_SURVEY_ID")
WEBHOOK_BASE = os.getenv("FLASK_WEBHOOK")


def get_survey_structure():
    headers = {
        "Authorization": f"Bearer {SURVEYMONKEY_TOKEN}",
        "Content-Type": "application/json"
    }

    url = f"https://api.surveymonkey.ca/v3/surveys/{SURVEY_ID}/details"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("❌ Failed to fetch survey structure")
        return {}

    data = response.json()
    choice_map = {}

    for page in data.get("pages", []):
        for question in page.get("questions", []):
            qid = question["id"]
            choice_map[qid] = {}
            for answer in question.get("answers", {}).get("choices", []):
                if isinstance(answer, dict):
                    answer_id = answer.get("id")
                    answer_text = answer.get("text", "Unknown")
                    if answer_id:
                        choice_map[qid][answer_id] = answer_text

    return choice_map

    
QUESTION_CHOICE_MAP_String = "{'66513594': {}, '66513595': {}, '66513612': {}, '66513611': {}, '66513617': {}, '66513608': {'540728149': 'Yes', '540728150': 'No'}, '66513596': {'540728108': 'Yes', '540728109': 'No'}, '66513597': {'540728111': 'Yes', '540728112': 'No'}, '66513598': {}, '66513599': {'540728118': 'Yes', '540728119': 'No'}, '66513600': {'540728120': 'Pregnancy or breastfeeding', '540728121': 'Removal of the uterus', '540728213': 'Removal of both ovaries', '540728214': 'Removal of the uterus and both ovaries', '540728122': 'Radiation or chemotherapy affecting the uterus or both ovaries', '540728123': 'Menopause', '540728124': 'Hormonal birth control e.g., birth control pill, hormonal intrauterine device (IUD), injections', '540728125': 'Medication, hormones, or drugs (Excluding birth control)', '540728126': 'Excessive physical activity'}, '66513601': {'540728131': 'Yes', '540728132': 'No'}, '66513602': {'540728133': 'Yes', '540728134': 'No'}, '66513613': {'540728186': 'Yes', '540728187': 'No'}, '66513614': {'540728194': 'Yes', '540728195': 'No'}, '66513615': {'540728196': 'Yes', '540728197': 'No'}, '66513603': {'540728135': 'Yes', '540728136': 'No'}, '66513604': {'540728137': 'Yes', '540728138': 'No'}, '66513616': {'540728203': 'Yes', '540728204': 'No'}, '66513605': {'540728140': 'Yes', '540728141': 'No'}, '66513606': {'540728143': 'Yes', '540728144': 'No'}, '66513607': {'540728146': 'Yes', '540728147': 'No'}, '66513609': {}, '66513610': {}}"
QUESTION_CHOICE_MAP = ast.literal_eval(QUESTION_CHOICE_MAP_String)


last_candidate = {}

SYSTEM_PROMPT = """
You are a triage assistant for a research study.
Return a JSON object with:
  decision: "YES", "NO", or "UNSURE"
  reason: a 1-sentence rationale (≤ 30 words).
  summary: a concise summary of the email body (≤ 200 characters).

Rules:
- "YES" if the email is related to the study (e.g., interest, inquiry, follow-up).
- "NO" only if clearly unrelated (e.g., spam, unrelated job offers).
- "UNSURE" for anything ambiguous.
Return *only* a JSON object. No extra commentary.
"""
def is_response_eligible(response):
    for page in response.get("pages", []):
        for question in page.get("questions", []):
            if not question.get("answers"):
                return False
    return True

def classify_email(subject, body):
    response = openai_client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Subject: {subject}\n\nBody:\n{body}"}
        ]
    )
    parsed = json.loads(response.choices[0].message.content)
    print(parsed)
    return parsed["decision"].upper(), parsed["reason"], parsed["summary"]

def extract_name_from_email(email):
    username = email.split("@")[0]
    name = username.replace(".", " ").replace("_", " ").title()
    return name

def notify_related_email(summary, reason, from_email, from_name):
    """Forward email notification to Discord bot"""
    payload = {
        "id": f"email_{int(time.time())}",  # Generate unique ID for this email
        "name": from_name,
        "email": from_email,
        "summary": summary,
        "reason": reason,
        "type": "email"  # Indicate this is an email notification
    }
    
    try:
        # Forward to Discord bot running on port 6000
        response = requests.post(f"{WEBHOOK_BASE}/notify", json=payload, timeout=5)

        if response.status_code == 200:
            print("✅ Forwarded to Discord bot successfully")
        else:
            print(f"❌ Failed to forward to Discord bot: {response.status_code}")
    except Exception as e:
        print(f"❌ Error forwarding to Discord bot: {e}")

# Flask App
app = Flask(__name__)

@app.route("/email", methods=["POST"])
def email_handler():
    data = request.json
    subject = data.get("subject", "")
    body = data.get("body", "")
    from_email = data.get("from_email", "")
    from_name = extract_name_from_email(from_email)

    decision, reason, summary = classify_email(subject, body)

    if decision == "YES":
        notify_related_email(summary, reason, from_email, from_name)

    return "Processed", 200

def get_surveymonkey_responses():
    headers = {
        "Authorization": f"Bearer {SURVEYMONKEY_TOKEN}",
        "Content-Type": "application/json"
    }

    url = f"https://api.surveymonkey.ca/v3/surveys/{SURVEY_ID}/responses/bulk"  # use .ca for Canadian accounts

    print("🔍 Requesting:", url)
    response = requests.get(url, headers=headers)

    print(f"📥 Status: {response.status_code}")
    try:
        payload = response.json()
    except Exception as e:
        print("❌ Failed to parse JSON:", e)
        print("Raw text:", response.text)
        return []

    if response.status_code != 200:
        print("⚠️ Error fetching responses")
        return []

    return payload.get("data", [])
def get_survey_question_map():
    headers = {
        "Authorization": f"Bearer {SURVEYMONKEY_TOKEN}",
        "Content-Type": "application/json"
    }

    url = f"https://api.surveymonkey.ca/v3/surveys/{SURVEY_ID}/details"
    r = requests.get(url, headers=headers)
    
    if r.status_code != 200:
        print("⚠️ Failed to fetch survey details")
        return {}

    data = r.json()
    question_map = {}

    for page in data.get("pages", []):
        for question in page.get("questions", []):
            qid = question["id"]
            title = question.get("headings", [{}])[0].get("heading", "").strip()
            question_map[qid] = title or f"Question {qid}"

    return question_map

QUESTION_MAP = get_survey_question_map()

def summarize_answers(response):
    summary = []

    for page in response.get("pages", []):
        for question in page.get("questions", []):
            qid = question.get("id")
            q_text = QUESTION_MAP.get(qid, f"Question {qid}").strip()
            answers = question.get("answers", [])

            # Skip question text for name/email but keep their value
            if "name" in q_text.lower() and answers:
                summary.append(answers[0].get("text", "N/A"))
                continue
            if "email" in q_text.lower() and answers:
                summary.append(answers[0].get("text", "N/A"))
                continue

            if not answers:
                summary.append(f"{q_text}:\nN/A\n")
                continue

            parts = []
            for a in answers:
                text = a.get("text", "").strip()
                if text:
                    parts.append(text)
                elif "choice_id" in a:
                    choice_id = str(a["choice_id"])
                    label = QUESTION_CHOICE_MAP.get(qid, {}).get(choice_id, "Unknown")
                    parts.append(label)
                else:
                    parts.append("N/A")

            answer_text = "; ".join(parts)
            summary.append(f"{q_text}:\n{answer_text}\n")

    return "\n".join(summary)








def get_single_surveymonkey_response():
    headers = {
        "Authorization": f"Bearer {SURVEYMONKEY_TOKEN}",
        "Content-Type": "application/json"
    }

    url = f"https://api.surveymonkey.ca/v3/surveys/{SURVEY_ID}/responses/bulk?per_page=1"

    print("🔍 Requesting:", url)
    response = requests.get(url, headers=headers)

    print(f"📥 Status: {response.status_code}")
    try:
        data = response.json()
        print(json.dumps(data, indent=2))  # Print entire structure nicely
    except Exception as e:
        print("❌ Error parsing JSON:", e)
        print("Raw response:", response.text)
        return

    if response.status_code != 200:
        print("⚠️ Error fetching response")
        return

    # Optionally extract first response:
    first_response = data.get("data", [])[0] if data.get("data") else {}
    print("\n🧾 First Response:")
    print(json.dumps(first_response, indent=2))


@app.route("/survey-responses", methods=["GET"])
def survey_responses():
    responses = get_surveymonkey_responses()
    return json.dumps(responses, indent=2)
@app.route("/notify", methods=["POST"])
def receive_survey():
    """Receive survey data and forward to Discord bot"""
    data = request.json
    if not data:
        return "Missing payload", 400
    
    try:
        # Forward the request to your Discord bot running on port 6000
        response = requests.post(f"{WEBHOOK_BASE}/notify", json=data, timeout=5)

        
        if response.status_code == 200:
            return "OK", 200
        else:
            return f"Discord bot error: {response.status_code}", 500
            
    except requests.exceptions.RequestException as e:
        print(f"Error forwarding to Discord bot: {e}")
        return "Discord bot unavailable", 503    
def list_surveys():
    headers = {
        "Authorization": f"Bearer {SURVEYMONKEY_TOKEN}",
        "Content-Type": "application/json"
    }
    url = "https://api.surveymonkey.ca/v3/surveys"

    r = requests.get(url, headers=headers)
    print(r.status_code, r.text)

EXPECTED_QUESTION_COUNT = 20  # you can update this if needed

def is_response_eligible(response):
    answered_count = 0
    for page in response.get("pages", []):
        for question in page.get("questions", []):
            if question.get("answers"):
                answered_count += 1
    return answered_count >= EXPECTED_QUESTION_COUNT

if __name__ == "__main__":
    import os
    poll_survey_responses()  # start background loop
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)