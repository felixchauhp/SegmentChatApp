import socket
import threading
import json
from tracker import Tracker
from sync import channel_storage
from utils import log_event
from message_log import log_message
from database import init_db, save_message
from datetime import datetime

HOST = '0.0.0.0'
PORT = 5000

tracker = Tracker()
lock = threading.Lock()
api_started = False
livestream_status = {}  # Theo dõi tất cả peer đang livestream {username: channel}
channel_livestreamers = {}  # Theo dõi danh sách peer đang livestream trong mỗi kênh {channel: [username]}

def handle_client(conn, addr):
    with conn:
        print(f"[+] Kết nối từ {addr}")
        log_event(f"Kết nối từ {addr}")
        buffer = ""
        try:
            while True:
                conn.settimeout(30)  # Tăng timeout lên 30 giây
                data = conn.recv(8192).decode('utf-8')
                if not data:
                    break
                buffer += data
                while '\n' in buffer:
                    message, buffer = buffer.split('\n', 1)
                    if not message:
                        continue
                    try:
                        request = json.loads(message)
                        print(f"[SERVER] Nhận yêu cầu từ {addr}: {request}")
                        log_event(f"Nhận yêu cầu từ {addr}: {request}")
                    except json.JSONDecodeError as e:
                        error_msg = f"[ERROR] JSON không hợp lệ từ {addr}: {e}"
                        print(error_msg)
                        log_event(error_msg)
                        conn.sendall((json.dumps({"error": "JSON không hợp lệ", "request_id": "unknown"}) + '\n').encode('utf-8'))
                        continue

                    with lock:
                        request_id = request.get("request_id", "unknown")
                        try:
                            if request['type'] == 'register':
                                from database import register_user
                                username = request['username']
                                password = request['password']
                                if not username or not password:
                                    conn.sendall((json.dumps({"error": "Tên người dùng hoặc mật khẩu trống", "request_id": request_id}) + '\n').encode('utf-8'))
                                    continue
                                if register_user(username, password):
                                    conn.sendall((json.dumps({"status": "Đăng ký thành công", "request_id": request_id}) + '\n').encode('utf-8'))
                                    log_event(f"Đăng ký thành công: {username}")
                                else:
                                    conn.sendall((json.dumps({"error": "Tên người dùng đã tồn tại", "request_id": request_id}) + '\n').encode('utf-8'))
                            
                            elif request['type'] == 'login':
                                from database import login_user
                                username = request['username']
                                password = request['password']
                                if not username or not password:
                                    conn.sendall((json.dumps({"error": "Tên người dùng hoặc mật khẩu trống", "request_id": request_id}) + '\n').encode('utf-8'))
                                    continue
                                if login_user(username, password):
                                    conn.sendall((json.dumps({"status": "Đăng nhập thành công", "request_id": request_id}) + '\n').encode('utf-8'))
                                    log_event(f"Đăng nhập thành công: {username}")
                                else:
                                    conn.sendall((json.dumps({"error": "Tên người dùng hoặc mật khẩu không đúng", "request_id": request_id}) + '\n').encode('utf-8'))
                                    log_event(f"Đăng nhập thất bại: {username}")
                            
                            elif request['type'] == 'submit_info':
                                from database import login_user
                                username = request['username']
                                password = request.get('password', '')
                                if not request.get('visitor', False):
                                    if not password:
                                        conn.sendall((json.dumps({"error": "Thiếu mật khẩu xác thực", "request_id": request_id}) + '\n').encode('utf-8'))
                                        continue
                                    if not login_user(username, password):
                                        conn.sendall((json.dumps({"error": "Tên người dùng hoặc mật khẩu không đúng", "request_id": request_id}) + '\n').encode('utf-8'))
                                        continue
                                peer_info = {
                                    'ip': addr[0],
                                    'port': request['port'],
                                    'username': username,
                                    'session_id': request['session_id'],
                                    'visitor': request.get('visitor', False),
                                    'invisible': request.get('invisible', False),
                                    'online': True
                                }
                                if tracker.peer_exists(addr[0], request['port']):
                                    tracker.remove_peer(addr[0], request['port'])
                                    log_event(f"Xóa peer cũ: IP={addr[0]}, Port={request['port']}")
                                tracker.add_peer(
                                    addr[0], request['port'], username,
                                    request['session_id'], request.get('visitor', False),
                                    request.get('invisible', False), True
                                )
                                print(f"[TRACKER] Thêm/Cập nhật peer: {peer_info}")
                                log_event(f"Thêm/Cập nhật peer: {peer_info}")
                                conn.sendall((json.dumps({"status": "success", "message": "Thông tin được gửi thành công", "request_id": request_id}) + '\n').encode('utf-8'))

                            elif request['type'] == 'get_list':
                                peers = tracker.get_peers()
                                if not peers:
                                    log_event("Trả về danh sách peer rỗng")
                                response = json.dumps(peers)
                                conn.sendall((response + '\n').encode('utf-8'))
                                print(f"[SERVER] Gửi danh sách peer đến {addr}: {len(peers)} peer")
                                log_event(f"Gửi danh sách peer đến {addr}: {len(peers)} peer")

                            elif request['type'] == 'sync_upload':
                                channel = request['channel']
                                message = request['message']
                                from database import get_channels
                                if channel not in get_channels():
                                    from database import create_channel
                                    create_channel(channel, request.get('username', 'system'))
                                    channel_storage[channel] = {'messages': [], 'creator': request.get('username', 'system')}
                                channel_storage[channel]['messages'].append(message)
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                save_message(channel, request.get('username', 'system'), message, timestamp)
                                print(f"[SYNC] Thêm tin nhắn vào {channel}: {message}")
                                log_event(f"Thêm tin nhắn vào kênh {channel}: {message}")
                                conn.sendall((json.dumps({"status": "success", "message": "Đồng bộ tải lên thành công", "request_id": request_id}) + '\n').encode('utf-8'))
                                notify_clients_new_message(channel, message)

                            elif request['type'] == 'sync_download':
                                channel = request['channel']
                                if not isinstance(channel, str):
                                    error_msg = f"[ERROR] Kênh không hợp lệ trong sync_download: {channel}"
                                    print(error_msg)
                                    log_event(error_msg)
                                    conn.sendall((json.dumps({"error": "Kênh không hợp lệ", "request_id": request_id}) + '\n').encode('utf-8'))
                                    continue
                                try:
                                    conn.settimeout(0.1)
                                    while True:
                                        try:
                                            conn.recv(4096)
                                        except socket.timeout:
                                            break
                                    conn.settimeout(30)
                                except:
                                    pass
                                from database import get_messages
                                messages = [f"{msg['sender']}: {msg['message']} [{msg['timestamp']}]" for msg in get_messages(channel)]
                                response = json.dumps(messages)
                                conn.sendall((response + '\n').encode('utf-8'))
                                print(f"[SYNC] Gửi {len(messages)} tin nhắn cho kênh {channel} đến {addr}")
                                log_event(f"Gửi {len(messages)} tin nhắn cho kênh {channel} đến {addr}")

                            elif request['type'] == 'disconnect':
                                try:
                                    channel = livestream_status.get(request['username'])
                                    if channel:
                                        del livestream_status[request['username']]
                                        if channel in channel_livestreamers:
                                            channel_livestreamers[channel].remove(request['username'])
                                            if not channel_livestreamers[channel]:
                                                del channel_livestreamers[channel]
                                            else:
                                                new_primary = channel_livestreamers[channel][0]
                                                notify_new_primary_streamer(channel, new_primary)
                                        notify_livestream_stop(channel, request['username'])
                                    tracker.remove_peer(addr[0], request['port'])
                                    print(f"[SERVER] Peer {addr[0]}:{request['port']} đã ngắt kết nối.")
                                    log_event(f"Peer {addr[0]}:{request['port']} đã ngắt kết nối")
                                    conn.sendall((json.dumps({"status": "success", "message": "Peer ngắt kết nối thành công", "request_id": request_id}) + '\n').encode('utf-8'))
                                except Exception as e:
                                    error_msg = f"[ERROR] Không thể ngắt kết nối peer {addr[0]}:{request['port']}: {e}"
                                    print(error_msg)
                                    log_event(error_msg)
                                break

                            elif request['type'] == 'create_channel':
                                channel = request['channel']
                                username = request['username']
                                from database import create_channel
                                if create_channel(channel, username):
                                    if channel not in channel_storage:
                                        channel_storage[channel] = {'messages': [], 'creator': username}
                                    print(f"[SERVER] Tạo kênh mới: {channel} bởi {username}")
                                    log_event(f"Tạo kênh mới: {channel} bởi {username}")
                                    conn.sendall((json.dumps({"status": "success", "message": f"Kênh {channel} được tạo thành công", "request_id": request_id}) + '\n').encode('utf-8'))
                                    notify_channel_creation(channel, username)
                                else:
                                    conn.sendall((json.dumps({"error": "Kênh đã tồn tại", "request_id": request_id}) + '\n').encode('utf-8'))

                            elif request['type'] == 'get_channel_list':
                                try:
                                    from database import get_channels
                                    channels = get_channels()
                                    if not channels:
                                        channels = ["general"]
                                    response = json.dumps(channels)
                                    conn.sendall((response + '\n').encode('utf-8'))
                                    print(f"[SERVER] Gửi danh sách kênh đến {addr}: {channels}")
                                    log_event(f"Gửi danh sách kênh đến {addr}: {channels}")
                                except Exception as e:
                                    error_msg = f"[ERROR] Không thể gửi danh sách kênh đến {addr}: {type(e).__name__}: {str(e)}"
                                    print(error_msg)
                                    log_event(error_msg)
                                    conn.sendall((json.dumps(["general"], request_id=request_id) + '\n').encode('utf-8'))

                            elif request['type'] == 'start_livestream':
                                channel = request['channel']
                                username = request['username']
                                target_peers = request.get('target_peers', [])  # Lấy danh sách target_peers
                                livestream_status[username] = channel
                                if channel not in channel_livestreamers:
                                    channel_livestreamers[channel] = []
                                if username not in channel_livestreamers[channel]:
                                    channel_livestreamers[channel].append(username)
                                if len(channel_livestreamers[channel]) == 1:
                                    notify_new_primary_streamer(channel, username)
                                notify_livestream_start(channel, username, target_peers)  # Chuyển tiếp target_peers
                                conn.sendall((json.dumps({"status": "success", "message": "Livestream bắt đầu", "request_id": request_id}) + '\n').encode('utf-8'))
                                print(f"[SERVER] Livestream bắt đầu trong {channel} bởi {username}")
                                log_event(f"Livestream bắt đầu trong {channel} bởi {username}")

                            elif request['type'] == 'stop_livestream':
                                channel = request['channel']
                                username = request['username']
                                if livestream_status.get(username) == channel:
                                    del livestream_status[username]
                                if channel in channel_livestreamers and username in channel_livestreamers[channel]:
                                    channel_livestreamers[channel].remove(username)
                                    if not channel_livestreamers[channel]:
                                        del channel_livestreamers[channel]
                                    else:
                                        new_primary = channel_livestreamers[channel][0]
                                        notify_new_primary_streamer(channel, new_primary)
                                notify_livestream_stop(channel, username)
                                conn.sendall((json.dumps({"status": "success", "message": "Livestream kết thúc", "request_id": request_id}) + '\n').encode('utf-8'))
                                print(f"[SERVER] Livestream kết thúc trong {channel} bởi {username}")
                                log_event(f"Livestream kết thúc trong {channel} bởi {username}")

                            elif request['type'] == 'update_status':
                                try:
                                    tracker.update_peer_status(
                                        addr[0], request['port'],
                                        online=request.get('online', True),
                                        invisible=request.get('invisible', False)
                                    )
                                    print(f"[TRACKER] Cập nhật trạng thái cho {addr[0]}:{request['port']}")
                                    log_event(f"Cập nhật trạng thái cho {addr[0]}:{request['port']}")
                                    conn.sendall((json.dumps({"status": "success", "message": "Trạng thái được cập nhật", "request_id": request_id}) + '\n').encode('utf-8'))
                                except Exception as e:
                                    error_msg = f"[ERROR] Không thể cập nhật trạng thái cho {addr[0]}:{request['port']}: {e}"
                                    print(error_msg)
                                    log_event(error_msg)
                                    conn.sendall((json.dumps({"error": "Không thể cập nhật trạng thái", "request_id": request_id}) + '\n').encode('utf-8'))

                            else:
                                error_msg = f"[ERROR] Loại yêu cầu không xác định từ {addr}: {request['type']}"
                                print(error_msg)
                                log_event(error_msg)
                                conn.sendall((json.dumps({"error": "Loại yêu cầu không xác định", "request_id": request_id}) + '\n').encode('utf-8'))
                        except Exception as e:
                            error_msg = f"[ERROR] Xử lý yêu cầu {request.get('type', 'unknown')} từ {addr}: {type(e).__name__}: {str(e)}"
                            print(error_msg)
                            log_event(error_msg)
                            conn.sendall((json.dumps({"error": f"Yêu cầu thất bại: {str(e)}", "request_id": request_id}) + '\n').encode('utf-8'))
        except socket.timeout:
            print(f"[SERVER] Hết thời gian chờ cho client {addr}")
            log_event(f"Hết thời gian chờ cho client {addr}")
        except Exception as e:
            print(f"[SERVER] Lỗi xử lý client {addr}: {type(e).__name__}: {str(e)}")
            log_event(f"Lỗi xử lý client {addr}: {e}")
        finally:
            conn.settimeout(None)
            conn.close()

def notify_clients_new_message(channel, message):
    for peer in tracker.get_peers():
        if not peer['online']:
            log_event(f"Bỏ qua thông báo cho peer offline {peer['username']}")
            continue
        for attempt in range(3):  # Thử gửi 3 lần
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((peer['ip'], peer['port']))
                notification = json.dumps({"type": "notification", "channel": channel, "message": message})
                s.sendall((notification + '\n').encode('utf-8'))
                s.close()
                log_message(channel, message, peer['username'], deleted=False)
                log_event(f"Thông báo {peer['username']} về tin nhắn mới trong {channel}")
                break
            except Exception as e:
                log_event(f"Không thể thông báo {peer['username']} về tin nhắn mới (lần {attempt+1}/3): {type(e).__name__}: {str(e)}")
                if attempt == 2:
                    log_event(f"Bỏ qua thông báo tin nhắn mới cho {peer['username']} sau 3 lần thất bại")

def notify_channel_creation(channel, username):
    message = f"[SYSTEM] Kênh '{channel}' được tạo bởi {username}"
    for peer in tracker.get_peers():
        if not peer['online']:
            log_event(f"Bỏ qua thông báo tạo kênh cho peer offline {peer['username']}")
            continue
        for attempt in range(3):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((peer['ip'], peer['port']))
                notification = json.dumps({
                    "type": "channel_creation",
                    "channel": channel,
                    "message": message
                })
                s.sendall((notification + '\n').encode('utf-8'))
                s.close()
                log_message(channel, message, "system", deleted=False)
                log_event(f"Thông báo {peer['username']} về việc tạo kênh: {channel}")
                break
            except Exception as e:
                log_event(f"Không thể thông báo {peer['username']} về việc tạo kênh (lần {attempt+1}/3): {type(e).__name__}: {str(e)}")
                if attempt == 2:
                    log_event(f"Bỏ qua thông báo tạo kênh cho {peer['username']} sau 3 lần thất bại")

def notify_livestream_start(channel, username, target_peers):
    message = f"{username} bắt đầu livestream trong {channel}"
    for peer in tracker.get_peers():
        if not peer['online']:
            log_event(f"Bỏ qua thông báo bắt đầu livestream cho peer offline {peer['username']}")
            continue
        for attempt in range(3):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((peer['ip'], peer['port']))
                notification = json.dumps({
                    "type": "livestream_start",
                    "channel": channel,
                    "message": message,
                    "username": username,
                    "target_peers": target_peers  # Chuyển tiếp danh sách target_peers
                })
                s.sendall((notification + '\n').encode('utf-8'))
                s.close()
                log_message(channel, message, username, deleted=False)
                log_event(f"Thông báo {peer['username']} về livestream bắt đầu trong {channel}")
                break
            except Exception as e:
                log_event(f"Không thể thông báo {peer['username']} về livestream bắt đầu (lần {attempt+1}/3): {type(e).__name__}: {str(e)}")
                if attempt == 2:
                    log_event(f"Bỏ qua thông báo livestream bắt đầu cho {peer['username']} sau 3 lần thất bại")

def notify_livestream_stop(channel, username):
    message = f"{username} dừng livestream trong {channel}"
    for peer in tracker.get_peers():
        if not peer['online']:
            log_event(f"Bỏ qua thông báo dừng livestream cho peer offline {peer['username']}")
            continue
        for attempt in range(3):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((peer['ip'], peer['port']))
                notification = json.dumps({
                    "type": "livestream_stop",
                    "channel": channel,
                    "message": message,
                    "username": username
                })
                s.sendall((notification + '\n').encode('utf-8'))
                s.close()
                log_message(channel, message, username, deleted=False)
                log_event(f"Thông báo {peer['username']} về livestream dừng trong {channel}")
                break
            except Exception as e:
                log_event(f"Không thể thông báo {peer['username']} về livestream dừng (lần {attempt+1}/3): {type(e).__name__}: {str(e)}")
                if attempt == 2:
                    log_event(f"Bỏ qua thông báo livestream dừng cho {peer['username']} sau 3 lần thất bại")

def notify_new_primary_streamer(channel, primary_username):
    message = f"[SYSTEM] {primary_username} là peer chính livestream trong {channel}"
    for peer in tracker.get_peers():
        if not peer['online']:
            log_event(f"Bỏ qua thông báo peer chính cho peer offline {peer['username']}")
            continue
        for attempt in range(3):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((peer['ip'], peer['port']))
                notification = json.dumps({
                    "type": "new_primary_streamer",
                    "channel": channel,
                    "message": message,
                    "primary_username": primary_username
                })
                s.sendall((notification + '\n').encode('utf-8'))
                s.close()
                log_message(channel, message, "system", deleted=False)
                log_event(f"Thông báo {peer['username']} về peer chính mới: {primary_username}")
                break
            except Exception as e:
                log_event(f"Không thể thông báo {peer['username']} về peer chính mới (lần {attempt+1}/3): {type(e).__name__}: {str(e)}")
                if attempt == 2:
                    log_event(f"Bỏ qua thông báo peer chính mới cho {peer['username']} sau 3 lần thất bại")

def start_server():
    global api_started
    init_db()
    # Khởi tạo channel_storage từ database
    from database import get_channels
    for channel in get_channels():
        if channel not in channel_storage:
            channel_storage[channel] = {'messages': [], 'creator': None}
    if "general" not in channel_storage:
        channel_storage["general"] = {'messages': [], 'creator': None}
    
    if not api_started:
        try:
            threading.Thread(
                target=lambda: __import__('api').app.run(host='0.0.0.0', port=5001),
                daemon=True
            ).start()
            api_started = True
            print("[API] Khởi động trên cổng 5001")
            log_event("API khởi động trên cổng 5001")
        except Exception as e:
            print(f"[API ERROR] Không thể khởi động API: {type(e).__name__}: {str(e)}")
            log_event(f"Không thể khởi động API: {e}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen()
            print(f"[SERVER] Lắng nghe trên {HOST}:{PORT}...")
            log_event(f"Server khởi động trên {HOST}:{PORT}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
            print(f"[SERVER ERROR] Không thể khởi động server: {type(e).__name__}: {str(e)}")
            log_event(f"Không thể khởi động server: {e}")

if __name__ == "__main__":
    start_server()