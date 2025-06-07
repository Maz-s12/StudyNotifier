# study_email_bot.py
import os
import imaplib
from flask import Flask, request
import smtplib
from email.message import EmailMessage
from openai import OpenAI
from twilio.rest import Client
import json
import requests
from dotenv import load_dotenv
load_dotenv()
POWER_AUTOMATE_WEBHOOK = os.getenv("POWER_AUTOMATE")
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
twilio_auth = os.getenv("TWILIO_AUTH_TOKEN")
twilio_phone = os.getenv("TWILIO_PHONE")
your_phone = os.getenv("YOUR_PHONE")
twilio_client = Client(twilio_sid, twilio_auth)

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

def send_sms(msg):
    message = twilio_client.messages.create(
        body=msg,
        from_=twilio_phone,
        to=your_phone
    )
    print(message.sid)

    return message.sid

def notify_related_email(summary, reason):
    sms_text = f""" Study-related email received:
Summary: {summary}
Reason: {reason}
Reply YES to enroll them or NO to ignore."""
    print("Sending SMS:\n", sms_text)
    send_sms(sms_text)

# Flask App
app = Flask(__name__)

@app.route("/email", methods=["POST"])
def email_handler():
    global last_candidate
    data = request.json
    subject = data.get("subject", "")
    body = data.get("body", "")
    from_email = data.get("from_email", "")
    from_name = extract_name_from_email(from_email)

    decision, reason, summary = classify_email(subject, body)

    if decision == "YES":
        last_candidate = {"from": from_email, "name": from_name}
        notify_related_email(summary, reason)

    return "Processed", 200

@app.route("/sms", methods=["POST"])
def sms_reply():
    global last_candidate
    body = request.form.get("Body", "").strip().lower()

    if body == "yes" and last_candidate:
        payload = {
            "to_email": last_candidate["from"],
            "name": last_candidate["name"]
        }

        response = requests.post(POWER_AUTOMATE_WEBHOOK, json=payload)
        print("✅ Sent to Power Automate:", response.status_code, response.text)
        last_candidate.clear()

    elif body == "no":
        print("❌ Ignored candidate email")
        last_candidate.clear()

    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)