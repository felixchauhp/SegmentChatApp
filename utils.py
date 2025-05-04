import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "server_log.txt")

def log_event(message):
    """Ghi sự kiện vào file log với dấu thời gian."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    try:
        with open(LOG_FILE, "r", encoding='utf-8') as f:
            lines = f.readlines()
        if len(lines) >= 10000:
            with open(LOG_FILE, "w", encoding='utf-8') as f:
                f.write("")
            lines = []
    except FileNotFoundError:
        lines = []
    except UnicodeDecodeError as e:
        error_msg = f"Không thể đọc file log do lỗi mã hóa: {type(e).__name__}: {str(e)}"
        print(error_msg)
        lines = []

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
    except UnicodeEncodeError as e:
        error_msg = f"Không thể ghi thông điệp log do lỗi mã hóa: {type(e).__name__}: {str(e)}"
        print(error_msg)
    except Exception as e:
        print(f"Lỗi ghi log: {type(e).__name__}: {str(e)}")