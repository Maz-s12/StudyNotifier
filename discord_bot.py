import os
import discord
import asyncio
from discord.ext import commands
from discord.ui import View, Button
from discord import ButtonStyle
from dotenv import load_dotenv
from flask import Flask, request
import threading
import requests
from studybot import app  # 👈 Reuse same Flask app
from studybot import poll_survey_responses


load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
SURVEY_CHANNEL_ID = int(os.getenv("DISCORD_SURVEY_CHANNEL_ID"))
EMAIL_CHANNEL_ID = int(os.getenv("DISCORD_EMAIL_CHANNEL_ID"))
POWER_AUTOMATE_WEBHOOK = os.getenv("POWER_AUTOMATE")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Store notification data keyed by message-specific ID
notification_map = {}

class NotificationButtons(discord.ui.View):
    def __init__(self, notification_id):
        super().__init__(timeout=None)
        self.notification_id = notification_id
    
    @discord.ui.button(label="✅ Send Template", style=discord.ButtonStyle.success, custom_id="send_template")
    async def send_template(self, interaction: discord.Interaction, button: discord.ui.Button):
        notification = notification_map.get(self.notification_id)
        if not notification:
            await interaction.response.send_message("⚠️ Notification not found.", ephemeral=True)
            return
        
        # Send to Power Automate
        payload = {
            "to_email": notification["email"],
            "name": notification["name"]
        }
        
        try:
            response = requests.post(POWER_AUTOMATE_WEBHOOK, json=payload)
            if response.status_code == 200:
                await interaction.response.send_message(f"✅ Template email sent to {notification['name']}!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Failed to send template email.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
    
    @discord.ui.button(label="❌ Ignore", style=discord.ButtonStyle.danger, custom_id="ignore")
    async def ignore(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Ignored.", ephemeral=True)

@bot.event
async def on_ready():
    print(f"🤖 Logged in as {bot.user.name}")
    # Verify channels exist
    survey_channel = bot.get_channel(SURVEY_CHANNEL_ID)
    email_channel = bot.get_channel(EMAIL_CHANNEL_ID)
    if not survey_channel:
        print(f"⚠️ Warning: Survey channel {SURVEY_CHANNEL_ID} not found")
    if not email_channel:
        print(f"⚠️ Warning: Email channel {EMAIL_CHANNEL_ID} not found")

@bot.command()
async def test(ctx):
    # Trigger a fake survey post to test the interface
    survey = {"id": "110019162897", "name": "Jane Doe", "age": 28, "link": "https://example.com/survey"}
    await notify_survey(survey)

async def notify_survey(data):
    # Determine which channel to use based on notification type
    if data.get('type') == 'email':
        channel = bot.get_channel(EMAIL_CHANNEL_ID)
    else:
        channel = bot.get_channel(SURVEY_CHANNEL_ID)
    
    if not channel:
        print(f"❌ Channel not found for type: {data.get('type', 'unknown')}")
        return
    
    # Store notification data for button interactions
    notification_id = data.get('id', 'unknown')
    notification_map[notification_id] = data
    
    if data.get('type') == 'email':
        # Format for email notifications
        embed = discord.Embed(
            title="📧 New Study-Related Email",
            color=discord.Color.green()
        )
        embed.add_field(name="From", value=f"{data['name']} ({data['email']})", inline=False)
        embed.add_field(name="Summary", value=data['summary'], inline=False)
        embed.add_field(name="Reason", value=data['reason'], inline=False)
    else:
        # Format for survey notifications
        summary_lines = [f"**New Eligible Survey**"]
        for key, value in data.items():
            if key in ["link", "id", "type"]:
                continue
            summary_lines.append(f"**{key}**: {value}")
        
        if data.get('link'):
            summary_lines.append(f"\n🔗 [View Results]({data.get('link')})")
        
        embed = discord.Embed(
            title="📋 New Survey Response",
            description="\n".join(summary_lines),
            color=discord.Color.blue()
        )
    
    # Use the NotificationButtons class
    view = NotificationButtons(notification_id)
    
    await channel.send(embed=embed, view=view)

# Flask setup
flask_app = Flask(__name__)

@flask_app.route("/notify", methods=["POST"])
def receive_survey():
    data = request.json
    if not data:
        return "Missing payload", 400
    
    # Schedule the coroutine to run in the bot's event loop
    future = asyncio.run_coroutine_threadsafe(notify_survey(data), bot.loop)
    try:
        future.result(timeout=5)  # Wait up to 5 seconds
        return "OK", 200
    except Exception as e:
        print(f"Error processing notification: {e}")
        return "Error processing notification", 500
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    print("✅ Discord bot Flask server is ready at /notify")


if __name__ == "__main__":
    threading.Thread(target=poll_survey_responses, daemon=True).start()
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    bot.run(TOKEN)
    time.sleep(5)
