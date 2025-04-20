# message_log.py
import os
from datetime import datetime

LOG_DIR = "logs"
MESSAGE_LOG_FILE = os.path.join(LOG_DIR, "message_log.txt")

def log_message(channel, message, sender, deleted=False):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    try:
        with open(MESSAGE_LOG_FILE, "r") as f:
            lines = f.readlines()
        if len(lines) >= 10000:
            with open(MESSAGE_LOG_FILE, "w") as f:
                f.write("")
            lines = []
    except FileNotFoundError:
        lines = []

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "DELETED" if deleted else "ACTIVE"
    log_entry = f"[{timestamp}] Channel: {channel}, Sender: {sender}, Message: {message}, Status: {status}\n"
    with open(MESSAGE_LOG_FILE, "a") as f:
        f.write(log_entry)