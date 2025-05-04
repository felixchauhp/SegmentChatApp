import socket
import threading
import json
import time
from utils import log_event
import cv2
import pickle
import struct
from PIL import Image, ImageTk
import tkinter as tk
from typing import Dict, Any

peer_connections: Dict[tuple, socket.socket] = {}  # Socket cho tin nhắn JSON
video_connections: Dict[tuple, socket.socket] = {}  # Socket cho video
global_app = None
VIDEO_PORT_OFFSET = 1  # Cổng video = PEER_PORT + 1

def set_global_app(app: Any) -> None:
    global global_app
    global_app = app
    log_event("Đã thiết lập global_app trong p2p.py")

def create_video_label(streamer: str) -> None:
    if global_app is None:
        raise ValueError("global_app chưa được thiết lập")
    if streamer not in global_app.video_windows:
        try:
            label = tk.Label(global_app.video_frame, text=f"Video từ {streamer}", compound="top")
            label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            global_app.video_windows[streamer] = label
            log_event(f"create_video_label: Tạo nhãn video cho {streamer}")
        except Exception as e:
            log_event(f"Lỗi khi tạo nhãn video cho {streamer}: {type(e).__name__}: {str(e)}")

def stream_video(peer: Dict[str, Any], cap) -> None:
    """Gửi khung video qua socket TCP riêng đến peer"""
    if cap is None:
        log_event(f"Không thể gửi video đến {peer['username']}: Camera không được khởi tạo")
        return

    video_port = peer['port'] + VIDEO_PORT_OFFSET
    addr = (peer['ip'], video_port)
    for attempt in range(3):
        if addr not in video_connections:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.settimeout(15)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
                s.connect(addr)
                video_connections[addr] = s
                log_event(f"Kết nối video với {peer['username']} tại {peer['ip']}:{video_port}")
                break
            except Exception as e:
                log_event(f"Lỗi kết nối video với {peer['username']} (lần {attempt+1}/3): {type(e).__name__}: {str(e)}")
                if attempt == 2:
                    log_event(f"Bỏ qua kết nối video với {peer['username']} sau 3 lần thất bại")
                    return
                time.sleep(1)

    conn = video_connections.get(addr)
    if not conn:
        log_event(f"Không tìm thấy kết nối video với {peer['username']}")
        return

    last_frame_time = time.time()
    frame_interval = 1 / 20
    while global_app.is_streaming and cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            log_event("Không thể đọc khung video từ camera")
            break
        frame = cv2.resize(frame, (160, 120))
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
        _, buffer = cv2.imencode('.jpg', frame, encode_param)
        data = pickle.dumps(buffer)
        try:
            conn.sendall(struct.pack("L", len(data)))
            conn.sendall(data)
            log_event(f"Gửi khung video đến {peer['username']} (kích thước: {len(data)} bytes)")
        except socket.timeout:
            log_event(f"Timeout khi gửi khung video đến {peer['username']}, thử lại...")
            continue
        except Exception as e:
            log_event(f"Lỗi gửi khung video đến {peer['username']}: {type(e).__name__}: {str(e)}")
            break
        
        elapsed_time = time.time() - last_frame_time
        sleep_time = max(0, frame_interval - elapsed_time)
        time.sleep(sleep_time)
        last_frame_time = time.time()

    try:
        conn.close()
        video_connections.pop(addr, None)
        log_event(f"Đóng kết nối video với {addr}")
    except:
        pass

def receive_video(conn, streamer: str) -> None:
    """Nhận và hiển thị khung video từ socket TCP riêng"""
    if global_app is None:
        raise ValueError("global_app chưa được thiết lập")
    data = b""
    payload_size = struct.calcsize("L")
    conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
    while global_app.is_streaming:
        try:
            conn.settimeout(15)
            while len(data) < payload_size:
                packet = conn.recv(4096)
                if not packet:
                    log_event(f"Kết nối video với {streamer} bị đóng khi nhận kích thước dữ liệu")
                    return
                data += packet
                log_event(f"Nhận được {len(packet)} bytes từ {streamer}")
            packed_msg_size = data[:payload_size]
            data = data[payload_size:]
            msg_size = struct.unpack("L", packed_msg_size)[0]
            log_event(f"Nhận kích thước khung video từ {streamer}: {msg_size} bytes")

            while len(data) < msg_size:
                packet = conn.recv(4096)
                if not packet:
                    log_event(f"Kết nối video với {streamer} bị đóng khi nhận dữ liệu khung")
                    return
                data += packet
                log_event(f"Nhận thêm {len(packet)} bytes từ {streamer}, tổng cộng {len(data)}/{msg_size} bytes")
            if len(data) < msg_size:
                log_event(f"Không nhận đủ dữ liệu khung từ {streamer}")
                return
            frame_data = data[:msg_size]
            data = data[msg_size:]

            buffer = pickle.loads(frame_data)
            frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            imgtk = ImageTk.PhotoImage(image=img)
            if streamer in global_app.video_windows:
                label = global_app.video_windows[streamer]
                label.imgtk = imgtk
                label.configure(image=imgtk)
                log_event(f"Cập nhật khung video từ {streamer}")
        except socket.timeout:
            log_event(f"Timeout khi nhận dữ liệu video từ {streamer}, tiếp tục chờ...")
            continue
        except Exception as e:
            log_event(f"Lỗi nhận khung video từ {streamer}: {type(e).__name__}: {str(e)}")
            break
    log_event(f"Kết thúc nhận video từ {streamer}")

def peer_connect(peer: Dict[str, Any]) -> None:
    for attempt in range(3):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(15)
            s.connect((peer['ip'], peer['port']))
            peer_connections[(peer['ip'], peer['port'])] = s
            log_event(f"Kết nối P2P với {peer['username']} tại {peer['ip']}:{peer['port']}")
            threading.Thread(target=receive_messages, args=(s,), daemon=True).start()
            return
        except Exception as e:
            log_event(f"Lỗi kết nối P2P với {peer['username']} (lần {attempt+1}/3): {type(e).__name__}: {str(e)}")
            if attempt == 2:
                raise Exception(f"Không thể kết nối P2P với {peer['username']} sau 3 lần thử")
            time.sleep(1)

def send_message_to_peer(peer: Dict[str, Any], message: str) -> None:
    addr = (peer['ip'], peer['port'])
    if addr not in peer_connections:
        peer_connect(peer)
    for attempt in range(3):
        try:
            peer_connections[addr].sendall(message.encode('utf-8'))
            log_event(f"Đã gửi tin nhắn đến {peer['username']}")
            return
        except Exception as e:
            log_event(f"Lỗi gửi tin nhắn đến {peer['username']} (lần {attempt+1}/3): {type(e).__name__}: {str(e)}")
            peer_connections.pop(addr, None)
            if attempt == 2:
                raise Exception(f"Không thể gửi tin nhắn đến {peer['username']} sau 3 lần thử")
            peer_connect(peer)

def send_message_to_all_peers(message: str) -> None:
    for addr, conn in list(peer_connections.items()):
        try:
            conn.sendall(message.encode('utf-8'))
            log_event(f"Đã gửi tin nhắn đến {addr}")
        except Exception as e:
            log_event(f"Lỗi gửi tin nhắn đến {addr}: {type(e).__name__}: {str(e)}")
            peer_connections.pop(addr, None)

def listen_for_connections(port: int) -> None:
    try:
        # Socket cho tin nhắn JSON
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.listen()
        log_event(f"Lắng nghe kết nối P2P trên cổng {port}")

        # Socket cho video
        video_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        video_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        video_s.bind(('0.0.0.0', port + VIDEO_PORT_OFFSET))
        video_s.listen()
        log_event(f"Lắng nghe kết nối video trên cổng {port + VIDEO_PORT_OFFSET}")

        # Thread để chấp nhận kết nối video
        threading.Thread(target=accept_video_connections, args=(video_s,), daemon=True).start()

        # Chấp nhận kết nối tin nhắn
        while True:
            conn, addr = s.accept()
            peer_connections[addr] = conn
            log_event(f"Chấp nhận kết nối P2P từ {addr}")
            threading.Thread(target=receive_messages, args=(conn,), daemon=True).start()
    except socket.error as e:
        log_event(f"Lỗi socket khi lắng nghe P2P trên cổng {port}: {type(e).__name__}: {str(e)}")
        raise Exception(f"Không thể bind cổng {port}: {str(e)}")
    except Exception as e:
        log_event(f"Lỗi lắng nghe P2P: {type(e).__name__}: {str(e)}")
        raise

def accept_video_connections(video_s: socket.socket) -> None:
    while True:
        try:
            conn, addr = video_s.accept()
            video_connections[addr] = conn
            log_event(f"Chấp nhận kết nối video từ {addr}")
        except Exception as e:
            log_event(f"Lỗi chấp nhận kết nối video: {type(e).__name__}: {str(e)}")
            break

def receive_messages(s: socket.socket) -> None:
    if global_app is None:
        raise ValueError("global_app chưa được thiết lập")
    buffer = ""
    last_ping = time.time()
    while True:
        if time.time() - last_ping >= 10:
            try:
                s.sendall((json.dumps({"type": "ping"}) + '\n').encode('utf-8'))
                log_event(f"Gửi ping đến {s.getpeername()}")
                last_ping = time.time()
            except Exception as e:
                log_event(f"Lỗi gửi ping đến {s.getpeername()}: {type(e).__name__}: {str(e)}")
                break

        try:
            s.settimeout(20)
            data = s.recv(1024).decode('utf-8')
            if not data:
                log_event(f"Peer {s.getpeername()} ngắt kết nối (không có dữ liệu)")
                break
            buffer += data
            while '\n' in buffer:
                message, buffer = buffer.split('\n', 1)
                if not message:
                    continue
                try:
                    msg_data = json.loads(message)
                    log_event(f"Nhận tin nhắn từ {s.getpeername()}: {msg_data}")
                    if msg_data.get("type") == "ping":
                        s.sendall((json.dumps({"type": "pong"}) + '\n').encode('utf-8'))
                        log_event(f"Gửi pong đến {s.getpeername()}")
                        continue
                    if msg_data.get("type") == "pong":
                        log_event(f"Nhận pong từ {s.getpeername()}")
                        continue
                    global_app.receive_message(msg_data, s)
                except json.JSONDecodeError as e:
                    log_event(f"Tin nhắn P2P không hợp lệ từ {s.getpeername()}: {e}")
                except Exception as e:
                    log_event(f"Lỗi xử lý tin nhắn từ {s.getpeername()}: {type(e).__name__}: {str(e)}")
        except socket.timeout:
            log_event(f"Timeout khi nhận dữ liệu từ {s.getpeername()}, thử lại...")
            continue
        except socket.error as e:
            log_event(f"Lỗi socket trong receive_messages từ {s.getpeername()}: {type(e).__name__}: {str(e)}")
            break
        except Exception as e:
            log_event(f"Lỗi nhận tin nhắn từ {s.getpeername()}: {type(e).__name__}: {str(e)}")
            break
    try:
        addr = s.getpeername()
        s.close()
        peer_connections.pop(addr, None)
        log_event(f"Đóng kết nối P2P với {addr}")
    except Exception as e:
        log_event(f"Lỗi khi đóng kết nối P2P: {type(e).__name__}: {str(e)}")