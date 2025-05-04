import os
from datetime import datetime
from utils import log_event

LOG_DIR = "logs"
MESSAGE_LOG_FILE = os.path.join(LOG_DIR, "message_log.txt")

def log_message(channel, message, sender, deleted=False):
    """Ghi log tin nhắn vào file để debug (tin nhắn chính được lưu trong database)."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    try:
        with open(MESSAGE_LOG_FILE, "r", encoding='utf-8') as f:
            lines = f.readlines()
        if len(lines) >= 5000:  # Giảm giới hạn để tiết kiệm tài nguyên
            with open(MESSAGE_LOG_FILE, "w", encoding='utf-8') as f:
                f.write("")
            lines = []
    except FileNotFoundError:
        lines = []
    except UnicodeDecodeError as e:
        error_msg = f"Không thể đọc file log tin nhắn do lỗi mã hóa: {type(e).__name__}: {str(e)}"
        print(error_msg)
        log_event(error_msg)
        lines = []

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "ĐÃ XÓA" if deleted else "HOẠT ĐỘNG"
    log_entry = f"[{timestamp}] Kênh: {channel}, Người gửi: {sender}, Tin nhắn: {message}, Trạng thái: {status}\n"
    try:
        with open(MESSAGE_LOG_FILE, "a", encoding='utf-8') as f:
            f.write(log_entry)
    except UnicodeEncodeError as e:
        error_msg = f"Không thể ghi log tin nhắn do lỗi mã hóa: {type(e).__name__}: {str(e)}"
        print(error_msg)
        log_event(error_msg)
    except Exception as e:
        error_msg = f"Lỗi ghi log tin nhắn: {type(e).__name__}: {str(e)}"
        print(error_msg)
        log_event(error_msg)