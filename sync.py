import json
import threading
import time
import socket
from utils import log_event
from message_log import log_message
from database import save_message, get_messages
from datetime import datetime

unsynced_content = {}
channel_sync_status = {}
peer_status = {
    "online": True,
    "livestreaming": False,
    "invisible": False,
    "visitor": False
}
channel_storage = {"general": {'messages': [], 'creator': None}}
app = None

def add_unsynced_content(channel, message):
    if not isinstance(channel, str) or not channel.strip():
        log_event(f"Kênh không hợp lệ trong add_unsynced_content: {channel}")
        return
    if channel not in unsynced_content:
        unsynced_content[channel] = []
    if message and message not in unsynced_content[channel]:
        unsynced_content[channel].append(message)
        channel_sync_status[channel] = False
        log_event(f"Thêm tin nhắn chưa đồng bộ vào kênh {channel}: {message}")
        # Đảm bảo kênh tồn tại trong channel_storage và database
        if channel not in channel_storage:
            from database import create_channel
            create_channel(channel, app.USERNAME if app and hasattr(app, 'USERNAME') else "system")
            channel_storage[channel] = {'messages': [], 'creator': app.USERNAME if app else None}

def sync_to_server(server_socket):
    for channel, messages in list(unsynced_content.items()):
        for msg in messages:
            request_id = str(app.request_counter) if app and hasattr(app, 'request_counter') else "unknown"
            data = {"type": "sync_upload", "channel": channel, "message": msg, "request_id": request_id}
            if app and hasattr(app, 'request_counter'):
                app.request_counter += 1
            try:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sender = app.USERNAME if app and hasattr(app, 'USERNAME') else "system"
                save_message(channel, sender, msg, timestamp)
                
                server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
                server_socket.settimeout(5)
                response = server_socket.recv(1024).decode('utf-8').strip()
                
                log_event(f"Đồng bộ tin nhắn lên server: {msg} trong kênh {channel}, phản hồi: {response}")
                log_message(channel, msg, sender, deleted=False)
                server_socket.settimeout(None)
            except Exception as e:
                print(f"[SYNC ERROR] Không thể đồng bộ {channel}: {type(e).__name__}: {str(e)}")
                log_event(f"Không thể đồng bộ tin nhắn: {msg} trong kênh {channel}: {e}")
                return False
        channel_sync_status[channel] = True
    unsynced_content.clear()
    print("[SYNC] Tất cả nội dung chưa đồng bộ đã được tải lên.")
    return True

def sync_from_server(server_socket, channel, retries=3):
    if not isinstance(channel, str) or not channel.strip():
        log_event(f"Kênh không hợp lệ trong sync_from_server: {channel}")
        return []
    
    # Lấy tin nhắn cục bộ từ database trước
    local_messages = [f"{msg['sender']}: {msg['message']} [{msg['timestamp']}]" for msg in get_messages(channel)]
    log_event(f"Lấy {len(local_messages)} tin nhắn cục bộ từ database cho kênh {channel}")

    for attempt in range(retries):
        try:
            server_socket.settimeout(0.1)
            while True:
                try:
                    server_socket.recv(4096)
                except socket.timeout:
                    break
            server_socket.settimeout(20)
            
            request_id = str(app.request_counter) if app and hasattr(app, 'request_counter') else "unknown"
            request = {"type": "sync_download", "channel": channel, "request_id": request_id}
            if app and hasattr(app, 'request_counter'):
                app.request_counter += 1
            server_socket.sendall((json.dumps(request) + '\n').encode('utf-8'))
            
            response = ""
            while True:
                chunk = server_socket.recv(8192).decode('utf-8')
                if not chunk:
                    break
                response += chunk
                if '\n' in response:
                    response = response.split('\n')[0]
                    break
            if not response:
                log_event(f"Không có phản hồi từ server cho kênh {channel}, lần thử {attempt+1}, trả về tin nhắn cục bộ")
                return local_messages
            
            try:
                server_messages = json.loads(response)
            except json.JSONDecodeError as e:
                log_event(f"Phản hồi JSON không hợp lệ cho kênh {channel}: {response}, lỗi: {e}")
                raise ValueError(f"Phản hồi JSON không hợp lệ: {e}")
            
            if not isinstance(server_messages, list):
                log_event(f"Kỳ vọng danh sách tin nhắn, nhận được: {server_messages}")
                raise ValueError(f"Kỳ vọng danh sách tin nhắn, nhận được: {server_messages}")
            
            # Lọc tin nhắn để đảm bảo chỉ thuộc về kênh yêu cầu
            filtered_messages = [msg for msg in server_messages]
            log_event(f"Lấy {len(filtered_messages)} tin nhắn từ server cho kênh {channel}")
            print(f"[SYNC] Lấy nội dung từ server cho {channel}: {filtered_messages}")
            all_messages = list(set(local_messages + filtered_messages))
            server_socket.settimeout(None)
            log_event(f"Kết hợp {len(all_messages)} tin nhắn cho kênh {channel}")
            return all_messages
        except Exception as e:
            print(f"[SYNC ERROR] Không thể lấy nội dung kênh (lần thử {attempt+1}/{retries}): {type(e).__name__}: {str(e)}")
            log_event(f"Không thể lấy nội dung cho kênh {channel}: {e}")
            if attempt == retries - 1:
                log_event(f"Không thể đồng bộ kênh {channel}, trả về tin nhắn cục bộ")
                return local_messages
            time.sleep(1)
    server_socket.settimeout(None)
    return local_messages

def go_offline():
    peer_status["online"] = False
    peer_status["invisible"] = False
    print("[STATUS] Peer hiện đang offline.")
    log_event("Peer đã offline")

def go_online(server_socket):
    peer_status["online"] = True
    peer_status["invisible"] = False
    print("[STATUS] Peer hiện đang online. Đang đồng bộ nội dung lưu trữ...")
    log_event("Peer đã online")
    sync_to_server(server_socket)

def go_invisible():
    peer_status["invisible"] = True
    peer_status["online"] = False
    print("[STATUS] Peer hiện đang ẩn danh.")
    log_event("Peer đã ẩn danh")

def set_visitor_mode():
    peer_status["visitor"] = True
    peer_status["online"] = True
    peer_status["invisible"] = False
    print("[STATUS] Peer hiện đang ở chế độ khách.")
    log_event("Peer vào chế độ khách")

def set_authenticated_mode():
    peer_status["visitor"] = False
    peer_status["online"] = True
    peer_status["invisible"] = False
    print("[STATUS] Peer hiện đang ở chế độ xác thực.")
    log_event("Peer vào chế độ xác thực")

def start_livestreaming():
    peer_status["livestreaming"] = True
    print("[STATUS] Livestream bắt đầu.")
    log_event("Livestream bắt đầu")

def stop_livestreaming():
    peer_status["livestreaming"] = False
    print("[STATUS] Livestream kết thúc.")
    log_event("Livestream kết thúc")