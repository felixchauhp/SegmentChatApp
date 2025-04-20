# utils.py
import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "server_log.txt")

def log_event(message):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        if len(lines) >= 10000:
            with open(LOG_FILE, "w") as f:
                f.write("")
            lines = []
    except FileNotFoundError:
        lines = []

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")