import sqlite3
import bcrypt
from utils import log_event
import os
from datetime import datetime

DB_FILE = "chat_app.db"

def init_db():
    """Khởi tạo database và các bảng nếu chưa tồn tại."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Tạo bảng users
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL
            )
        ''')
        
        # Tạo bảng messages
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL
            )
        ''')
        
        # Tạo bảng channels
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                name TEXT PRIMARY KEY,
                creator TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Thêm chỉ mục cho cột channel để tăng tốc truy vấn
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_channel ON messages(channel)')
        
        # Thêm kênh mặc định 'general' nếu chưa tồn tại
        cursor.execute("SELECT name FROM channels WHERE name = ?", ("general",))
        if not cursor.fetchone():
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("INSERT INTO channels (name, creator, created_at) VALUES (?, ?, ?)",
                          ("general", "system", timestamp))
        
        conn.commit()
        log_event("Khởi tạo database thành công")
    except Exception as e:
        log_event(f"Lỗi khởi tạo database: {e}")
    finally:
        conn.close()

def register_user(username, password):
    """Đăng ký người dùng mới với mật khẩu băm."""
    if not username or not password:
        return False
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                      (username, password_hash))
        conn.commit()
        log_event(f"Đăng ký người dùng: {username}")
        return True
    except sqlite3.IntegrityError:
        log_event(f"Người dùng {username} đã tồn tại")
        return False
    except Exception as e:
        log_event(f"Lỗi đăng ký người dùng: {e}")
        return False
    finally:
        conn.close()

def login_user(username, password):
    """Xác thực người dùng dựa trên tên và mật khẩu."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        if result and bcrypt.checkpw(password.encode('utf-8'), result[0]):
            log_event(f"Đăng nhập thành công: {username}")
            return True
        log_event(f"Đăng nhập thất bại: {username}")
        return False
    except Exception as e:
        log_event(f"Lỗi đăng nhập: {e}")
        return False
    finally:
        conn.close()

def save_message(channel, sender, message, timestamp=None, status="HOẠT ĐỘNG"):
    """Lưu tin nhắn vào database."""
    if not timestamp:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (channel, sender, message, timestamp, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (channel, sender, message, timestamp, status))
        conn.commit()
        log_event(f"Lưu tin nhắn vào database: kênh={channel}, người gửi={sender}")
    except Exception as e:
        log_event(f"Lỗi lưu tin nhắn: {e}")
    finally:
        conn.close()

def get_messages(channel):
    """Lấy tất cả tin nhắn của một kênh từ database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT sender, message, timestamp, status FROM messages WHERE channel = ? ORDER BY timestamp", (channel,))
        messages = [{"sender": row[0], "message": row[1], "timestamp": row[2], "status": row[3]} for row in cursor.fetchall()]
        log_event(f"Lấy {len(messages)} tin nhắn từ database cho kênh {channel}")
        return messages
    except Exception as e:
        log_event(f"Lỗi lấy tin nhắn: {e}")
        return []
    finally:
        conn.close()

def create_channel(channel, creator):
    """Lưu kênh mới vào database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO channels (name, creator, created_at) VALUES (?, ?, ?)", 
                      (channel, creator, timestamp))
        conn.commit()
        log_event(f"Tạo kênh trong database: {channel} bởi {creator}")
        return True
    except sqlite3.IntegrityError:
        log_event(f"Kênh {channel} đã tồn tại")
        return False
    except Exception as e:
        log_event(f"Lỗi tạo kênh: {e}")
        return False
    finally:
        conn.close()

def get_channels():
    """Lấy danh sách tất cả kênh từ database."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM channels")
        channels = [row[0] for row in cursor.fetchall()]
        log_event(f"Lấy {len(channels)} kênh từ database")
        return channels
    except Exception as e:
        log_event(f"Lỗi lấy danh sách kênh: {e}")
        return []
    finally:
        conn.close()

if __name__ == "__main__":
    if not os.path.exists(DB_FILE):
        init_db()