import threading
import os
import time

# Start Flask app in thread
def start_flask():
    os.system("python discord_bot.py")

# Start Discord bot
def start_discord():
    os.system("python studybot.py")

if __name__ == "__main__":
    print("🚀 Starting Flask in background...")
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    print("🤖 Starting Discord bot...")
    time.sleep(1)  # Give Flask a second to spin up
    start_discord()