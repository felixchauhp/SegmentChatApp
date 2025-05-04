import socket
import json
import uuid
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk, simpledialog
from sync import add_unsynced_content, sync_to_server, go_online, go_offline, start_livestreaming, stop_livestreaming, peer_status, sync_from_server, set_visitor_mode, set_authenticated_mode, go_invisible, app
from p2p import listen_for_connections, peer_connect, send_message_to_all_peers, send_message_to_peer, peer_connections, video_connections, create_video_label, receive_video, set_global_app
from utils import log_event
from message_log import log_message
from database import init_db
import cv2
from PIL import Image, ImageTk
import os
import hashlib

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5000
USERNAME = None
SESSION_FILE = "session.txt"  # File lưu SESSION_ID
MESSAGES_FILE = "messages.json"  # File lưu tin nhắn cục bộ
PEER_PORT = 6000  # Giá trị mặc định cho PEER_PORT

def load_session_id():
    """Đọc SESSION_ID từ file, tạo mới nếu không tồn tại"""
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r') as f:
                return f.read().strip()
        session_id = str(uuid.uuid4())
        with open(SESSION_FILE, 'w') as f:
            f.write(session_id)
        return session_id
    except Exception as e:
        log_event(f"Lỗi khi đọc/ghi SESSION_ID: {type(e).__name__}: {str(e)}")
        return str(uuid.uuid4())

def get_stable_port(username):
    """Tạo PEER_PORT ổn định dựa trên hash của username"""
    if not username:
        return 6000 + int(uuid.uuid4().int % 1000)
    hash_obj = hashlib.sha256(username.encode())
    port_offset = int(hash_obj.hexdigest(), 16) % 1000
    return 6000 + port_offset

def load_messages():
    """Đọc tin nhắn từ file messages.json"""
    try:
        if os.path.exists(MESSAGES_FILE):
            with open(MESSAGES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        log_event(f"Lỗi khi đọc tin nhắn từ {MESSAGES_FILE}: {type(e).__name__}: {str(e)}")
        return {}

def save_messages(messages):
    """Lưu tin nhắn vào file messages.json"""
    try:
        with open(MESSAGES_FILE, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        log_event(f"Đã lưu tin nhắn vào {MESSAGES_FILE}")
    except Exception as e:
        log_event(f"Lỗi khi lưu tin nhắn vào {MESSAGES_FILE}: {type(e).__name__}: {str(e)}")

SESSION_ID = load_session_id()

class ChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Segment Chat - Đang chờ đăng nhập")
        self.root.geometry("900x600")
        self.root.minsize(400, 300)
        self.peers = []
        self.server_socket = None
        self.current_channel = "general"
        self.channels = ["general"]
        self.owned_channels = []
        self.is_visitor = False
        self.messages = load_messages()  # Khôi phục tin nhắn từ file
        self.displayed_messages = {}
        self.request_counter = 0
        self.last_reconnect = 0
        self.password = None
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.cap = None
        self.video_windows = {}
        self.is_streaming = False
        self.is_primary_streamer = False
        self.primary_streamer = None
        self.video_window = None
        self.video_frame = None
        self.create_login_widgets()
        globals()['app'] = self
        set_global_app(self)

    def create_login_widgets(self):
        self.login_frame = tk.Frame(self.root, bg="#2F3136")
        self.login_frame.pack(expand=True, fill=tk.BOTH)

        center_frame = tk.Frame(self.login_frame, bg="#2F3136")
        center_frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(center_frame, text="Đăng nhập vào Segment Chat", font=("Helvetica", 16, "bold"), bg="#2F3136", fg="#DCDDDE").pack(pady=10)

        tk.Label(center_frame, text="Tên người dùng:", font=("Helvetica", 12), bg="#2F3136", fg="#DCDDDE").pack(pady=5)
        self.username_entry = tk.Entry(center_frame, font=("Helvetica", 12), width=30, bg="#36393F", fg="#DCDDDE", insertbackground="#DCDDDE")
        self.username_entry.pack(pady=5)
        self.username_entry.focus()

        tk.Label(center_frame, text="Mật khẩu:", font=("Helvetica", 12), bg="#2F3136", fg="#DCDDDE").pack(pady=5)
        self.password_entry = tk.Entry(center_frame, font=("Helvetica", 12), width=30, show="*", bg="#36393F", fg="#DCDDDE", insertbackground="#DCDDDE")
        self.password_entry.pack(pady=5)
        self.password_entry.bind("<Return>", lambda event: self.login_authenticated())

        self.show_password = tk.BooleanVar()
        tk.Checkbutton(center_frame, text="Hiện mật khẩu", variable=self.show_password, command=self.toggle_password, bg="#2F3136", fg="#DCDDDE", selectcolor="#36393F").pack(pady=5)

        button_frame = tk.Frame(center_frame, bg="#2F3136")
        button_frame.pack(pady=10)
        tk.Button(button_frame, text="Đăng nhập", font=("Helvetica", 12), bg="#7289DA", fg="white", command=self.login_authenticated).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Đăng ký", font=("Helvetica", 12), bg="#5865F2", fg="white", command=self.register_user).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Khách", font=("Helvetica", 12), bg="#FFC107", fg="black", command=self.login_visitor).pack(side=tk.LEFT, padx=5)

    def toggle_password(self):
        if self.show_password.get():
            self.password_entry.config(show="")
        else:
            self.password_entry.config(show="*")

    def create_main_widgets(self):
        self.login_frame.destroy()
        self.root.configure(bg="#2F3136")

        # Sidebar trái
        sidebar_frame = tk.Frame(self.root, bg="#202225", width=220)
        sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)

        # Danh sách kênh
        channel_frame = tk.LabelFrame(sidebar_frame, text="Kênh", font=("Helvetica", 10, "bold"), bg="#202225", fg="#DCDDDE", bd=0)
        channel_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.channel_listbox = tk.Listbox(channel_frame, bg="#202225", fg="#DCDDDE", selectbackground="#7289DA", selectforeground="white", font=("Helvetica", 10), borderwidth=0, highlightthickness=0)
        for channel in self.channels:
            self.channel_listbox.insert(tk.END, f"# {channel}")
        self.channel_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.channel_listbox.bind("<<ListboxSelect>>", self.on_channel_select)
        tk.Button(channel_frame, text="Tạo kênh mới", font=("Helvetica", 10), bg="#5865F2", fg="white", command=self.create_channel).pack(pady=5)

        # Danh sách peer
        peer_frame = tk.LabelFrame(sidebar_frame, text="Peers", font=("Helvetica", 10, "bold"), bg="#202225", fg="#DCDDDE", bd=0)
        peer_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.peer_listbox = tk.Listbox(peer_frame, bg="#202225", fg="#DCDDDE", selectbackground="#7289DA", selectforeground="white", font=("Helvetica", 10), borderwidth=0, highlightthickness=0)
        self.peer_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        tk.Button(peer_frame, text="Làm mới", font=("Helvetica", 10), bg="#5865F2", fg="white", command=self.refresh_peer_list).pack(pady=5)

        # Khu vực chính
        self.main_frame = tk.Frame(self.root, bg="#36393F")
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        # Chat area
        self.chat_frame = tk.LabelFrame(self.main_frame, text=f"Chat (Kênh: {self.current_channel})", font=("Helvetica", 10, "bold"), bg="#36393F", fg="#DCDDDE", bd=0)
        self.chat_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.chat_area = scrolledtext.ScrolledText(self.chat_frame, height=20, bg="#36393F", fg="#DCDDDE", font=("Helvetica", 10), insertbackground="#DCDDDE", borderwidth=0)
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Thanh nhập tin nhắn
        message_frame = tk.Frame(self.chat_frame, bg="#36393F")
        message_frame.pack(fill=tk.X, pady=5)
        self.message_entry = tk.Entry(message_frame, font=("Helvetica", 10), bg="#40444B", fg="#DCDDDE", insertbackground="#DCDDDE")
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        tk.Button(message_frame, text="Gửi", font=("Helvetica", 10), bg="#7289DA", fg="white", command=self.send_channel_message).pack(side=tk.LEFT, padx=5)

        # Thanh điều khiển
        control_frame = tk.Frame(self.main_frame, bg="#36393F")
        control_frame.pack(fill=tk.X, pady=5)
        tk.Button(control_frame, text="Gửi đến Peer", font=("Helvetica", 10), bg="#5865F2", fg="white", command=self.send_to_peer).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Broadcast", font=("Helvetica", 10), bg="#5865F2", fg="white", command=self.broadcast_message).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Online", font=("Helvetica", 10), bg="#43B581", fg="white", command=self.go_online_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Offline", font=("Helvetica", 10), bg="#F04747", fg="white", command=self.go_offline_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Ẩn danh", font=("Helvetica", 10), bg="#FAA61A", fg="white", command=self.go_invisible_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Bắt đầu Livestream", font=("Helvetica", 10), bg="#7289DA", fg="white", command=self.start_livestream_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Dừng Livestream", font=("Helvetica", 10), bg="#F04747", fg="white", command=self.stop_livestream_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Thoát", font=("Helvetica", 10), bg="#F04747", fg="white", command=self.exit_ui).pack(side=tk.RIGHT, padx=2)

    def on_channel_select(self, event):
        selection = self.channel_listbox.curselection()
        if selection:
            channel = self.channel_listbox.get(selection[0]).lstrip("# ")
            self.switch_channel(channel)

    def register_user(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Lỗi", "Tên người dùng và mật khẩu không được để trống!")
            return
        if len(password) < 6:
            messagebox.showerror("Lỗi", "Mật khẩu phải có ít nhất 6 ký tự!")
            return
        if not username.isalnum():
            messagebox.showerror("Lỗi", "Tên người dùng chỉ được chứa chữ cái và số!")
            return
        data = {
            "type": "register",
            "username": username,
            "password": password,
            "request_id": str(self.request_counter)
        }
        self.request_counter += 1
        try:
            self.server_socket = self.create_socket()
            self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            self.server_socket.settimeout(15)
            response = self.server_socket.recv(1024).decode('utf-8').strip()
            response_data = json.loads(response)
            if response_data.get("status") == "Đăng ký thành công":
                messagebox.showinfo("Thành công", "Đăng ký thành công! Vui lòng đăng nhập.")
            else:
                messagebox.showerror("Lỗi", response_data.get("error", "Lỗi đăng ký!"))
            log_event(f"Kết quả đăng ký: {response}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đăng ký: {str(e)}")
            log_event(f"Lỗi đăng ký: {type(e).__name__}: {str(e)}")
        finally:
            if self.server_socket:
                try:
                    self.server_socket.close()
                except:
                    pass
                self.server_socket = None

    def login_authenticated(self):
        global USERNAME, PEER_PORT
        USERNAME = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not USERNAME or not password:
            messagebox.showerror("Lỗi", "Tên người dùng và mật khẩu không được để trống!")
            return

        # Tạo PEER_PORT ổn định dựa trên USERNAME
        PEER_PORT = get_stable_port(USERNAME)
        self.root.title(f"Segment Chat - Port {PEER_PORT}")

        # Ngắt kết nối peer cũ trước khi đăng nhập
        self.disconnect_old_peer()

        data = {
            "type": "login",
            "username": USERNAME,
            "password": password,
            "request_id": str(self.request_counter)
        }
        self.request_counter += 1
        try:
            self.server_socket = self.create_socket()
            self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            self.server_socket.settimeout(15)
            response = ""
            while True:
                chunk = self.server_socket.recv(1024).decode('utf-8')
                if not chunk:
                    raise ValueError("Phản hồi từ server rỗng")
                response += chunk
                if '\n' in response:
                    response = response.split('\n')[0]
                    break
            response_data = json.loads(response)
            if response_data.get("status") == "Đăng nhập thành công":
                self.is_visitor = False
                self.password = password
                self.create_main_widgets()
                self.start_networking()
                self.start_channel_sync()
                self.submit_info(password=password)
                self.get_channel_list()
                # Tải tin nhắn từ server và hợp nhất với tin nhắn cục bộ
                for channel in self.channels:
                    server_messages = sync_from_server(self.server_socket, channel)
                    if not isinstance(server_messages, list):
                        server_messages = []
                    # Hợp nhất tin nhắn từ server với tin nhắn cục bộ
                    current_messages = set(self.messages.get(channel, []))
                    current_messages.update(server_messages)
                    self.messages[channel] = list(current_messages)
                    self.displayed_messages[channel] = set()
                # Hiển thị tin nhắn cho kênh hiện tại
                if self.current_channel in self.messages:
                    for msg in self.messages[self.current_channel]:
                        if msg not in self.displayed_messages.get(self.current_channel, set()):
                            self.chat_area.insert(tk.END, f"{msg}\n")
                            self.displayed_messages.setdefault(self.current_channel, set()).add(msg)
                log_event(f"Tải tin nhắn cho {len(self.channels)} kênh")
                self.connect_to_all_peers()
                set_authenticated_mode()
                self.message_entry.config(state="normal")
                log_event(f"Đăng nhập với tư cách người dùng xác thực: {USERNAME}")
            else:
                messagebox.showerror("Lỗi", response_data.get("error", "Tên người dùng hoặc mật khẩu không đúng!"))
                log_event(f"Đăng nhập thất bại: {USERNAME}")
        except json.JSONDecodeError as e:
            messagebox.showerror("Lỗi", "Phản hồi từ server không hợp lệ. Vui lòng thử lại!")
            log_event(f"Lỗi đăng nhập JSONDecodeError: {e}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể đăng nhập: {str(e)}")
            log_event(f"Lỗi đăng nhập: {type(e).__name__}: {str(e)}")
        finally:
            if self.server_socket and self.is_visitor:
                try:
                    self.server_socket.close()
                except:
                    pass
                self.server_socket = None

    def login_visitor(self):
        global USERNAME, PEER_PORT
        USERNAME = self.username_entry.get().strip() or f"Visitor_{SESSION_ID[:8]}"
        self.is_visitor = True
        self.password = None

        # Tạo PEER_PORT ổn định dựa trên USERNAME
        PEER_PORT = get_stable_port(USERNAME)
        self.root.title(f"Segment Chat - Port {PEER_PORT}")

        # Ngắt kết nối peer cũ trước khi đăng nhập
        self.disconnect_old_peer()

        self.create_main_widgets()
        self.start_networking()
        self.start_channel_sync()
        self.submit_info(visitor=True)
        self.get_channel_list()
        # Tải tin nhắn từ server và hợp nhất với tin nhắn cục bộ
        for channel in self.channels:
            server_messages = sync_from_server(self.server_socket, channel)
            if not isinstance(server_messages, list):
                server_messages = []
            # Hợp nhất tin nhắn từ server với tin nhắn cục bộ
            current_messages = set(self.messages.get(channel, []))
            current_messages.update(server_messages)
            self.messages[channel] = list(current_messages)
            self.displayed_messages[channel] = set()
        # Hiển thị tin nhắn cho kênh hiện tại
        if self.current_channel in self.messages:
            for msg in self.messages[self.current_channel]:
                if msg not in self.displayed_messages.get(self.current_channel, set()):
                    self.chat_area.insert(tk.END, f"{msg}\n")
                    self.displayed_messages.setdefault(self.current_channel, set()).add(msg)
        log_event(f"Tải tin nhắn cho {len(self.channels)} kênh")
        self.connect_to_all_peers()
        set_visitor_mode()
        self.message_entry.config(state="disabled")
        self.chat_area.insert(tk.END, "[INFO] Tham gia với tư cách khách. Bạn chỉ có thể xem tin nhắn.\n")
        log_event(f"Tham gia với tư cách khách: {USERNAME}")

    def disconnect_old_peer(self):
        """Ngắt kết nối peer cũ trước khi đăng nhập lại"""
        try:
            temp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            temp_socket.settimeout(5)
            temp_socket.connect((SERVER_HOST, SERVER_PORT))
            data = {
                "type": "disconnect",
                "port": PEER_PORT,
                "username": USERNAME,
                "session_id": SESSION_ID,
                "request_id": str(self.request_counter)
            }
            self.request_counter += 1
            temp_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            log_event(f"Gửi yêu cầu ngắt kết nối peer cũ: {USERNAME}, port {PEER_PORT}")
            temp_socket.close()
        except Exception as e:
            log_event(f"Lỗi khi ngắt kết nối peer cũ: {type(e).__name__}: {str(e)}")

    def create_socket(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(15)
            s.connect((SERVER_HOST, SERVER_PORT))
            s.settimeout(None)
            return s
        except Exception as e:
            error_msg = f"[ERROR] Không thể kết nối đến server: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            raise

    def submit_info(self, visitor=False, password=None):
        global SESSION_ID
        data = {
            "type": "submit_info",
            "username": USERNAME,
            "port": PEER_PORT,
            "session_id": SESSION_ID,
            "visitor": visitor,
            "invisible": peer_status["invisible"],
            "password": password or self.password,
            "request_id": str(self.request_counter)
        }
        self.request_counter += 1
        try:
            self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            self.server_socket.settimeout(15)
            response = ""
            while True:
                chunk = self.server_socket.recv(1024).decode('utf-8')
                if not chunk:
                    raise ValueError("Phản hồi từ server rỗng")
                response += chunk
                if '\n' in response:
                    response = response.split('\n')[0]
                    break
            try:
                response_data = json.loads(response)
                if "error" in response_data:
                    self.chat_area.insert(tk.END, f"[ERROR] {response_data['error']}\n")
                    log_event(f"Xác thực thất bại: {response_data['error']}")
                    raise ValueError(f"Server error: {response_data['error']}")
                else:
                    self.chat_area.insert(tk.END, f"[SERVER RESPONSE] {response_data.get('message', 'Thông tin được gửi thành công')}\n")
                    log_event(f"Gửi thông tin: {data}, phản hồi: {response}")
            except json.JSONDecodeError:
                if "Thông tin được gửi thành công" in response:
                    log_event(f"Gửi thông tin: {data}, phản hồi văn bản: {response}")
                else:
                    raise ValueError(f"Phản hồi không phải JSON: {response}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Không thể gửi thông tin: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            self.reconnect()

    def reconnect(self):
        global SESSION_ID
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            messagebox.showerror("Lỗi", "Đã vượt quá số lần kết nối lại. Vui lòng khởi động lại ứng dụng!")
            log_event("Vượt quá số lần kết nối lại")
            self.exit_ui()
            return
        current_time = time.time()
        if current_time - self.last_reconnect < 5:
            time.sleep(5 - (current_time - self.last_reconnect))
        self.last_reconnect = current_time
        self.reconnect_attempts += 1
        try:
            if self.server_socket:
                self.server_socket.close()
            self.server_socket = self.create_socket()
            self.submit_info(visitor=self.is_visitor, password=self.password)
            self.chat_area.insert(tk.END, "[INFO] Kết nối lại với server.\n")
            log_event(f"Kết nối lại với server với session ID: {SESSION_ID}")
            self.reconnect_attempts = 0
        except Exception as e:
            error_msg = f"[ERROR] Không thể kết nối lại: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            self.root.after(5000, self.reconnect)

    def get_peer_list(self):
        data = {"type": "get_list", "request_id": str(self.request_counter)}
        self.request_counter += 1
        try:
            self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            self.server_socket.settimeout(15)
            response = ""
            while True:
                chunk = self.server_socket.recv(4096).decode('utf-8')
                if not chunk:
                    break
                response += chunk
                if '\n' in response:
                    response = response.split('\n')[0]
                    break
            log_event(f"Phản hồi danh sách peer: {response}")
            if not response:
                raise ValueError("Phản hồi từ server rỗng")
            try:
                peer_data = json.loads(response)
            except json.JSONDecodeError as e:
                log_event(f"Phản hồi JSON không hợp lệ cho danh sách peer: {response}, lỗi: {e}")
                raise ValueError(f"Phản hồi JSON không hợp lệ: {e}")
            if not isinstance(peer_data, list):
                raise ValueError(f"Kỳ vọng danh sách peer, nhận được: {peer_data}")
            if not peer_data:
                log_event("Nhận danh sách peer rỗng từ server")
            self.peers = peer_data
            self.update_peer_listbox()
            self.server_socket.settimeout(None)
            return self.peers
        except Exception as e:
            error_msg = f"[ERROR] Không thể lấy danh sách peer: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            return self.peers

    def get_channel_list(self, retries=3):
        for attempt in range(retries):
            try:
                try:
                    self.server_socket.getpeername()
                except:
                    self.reconnect()
                data = {"type": "get_channel_list", "request_id": str(self.request_counter)}
                self.request_counter += 1
                self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
                self.server_socket.settimeout(20)
                response = ""
                while True:
                    chunk = self.server_socket.recv(8192).decode('utf-8')
                    if not chunk:
                        raise ValueError("Phản hồi từ server rỗng")
                    response += chunk
                    if '\n' in response:
                        response = response.split('\n')[0]
                        break
                log_event(f"Phản hồi danh sách kênh: {response}")
                if not response:
                    raise ValueError("Phản hồi từ server rỗng")
                try:
                    new_channels = json.loads(response)
                except json.JSONDecodeError as e:
                    log_event(f"Phản hồi JSON không hợp lệ cho danh sách kênh: {response}, lỗi: {e}")
                    raise ValueError(f"Phản hồi JSON không hợp lệ: {e}")
                if not isinstance(new_channels, list):
                    raise ValueError(f"Kỳ vọng danh sách kênh, nhận được: {new_channels}")
                if new_channels and new_channels != self.channels:
                    self.channels = new_channels
                    self.update_channel_menu()
                    self.chat_area.insert(tk.END, f"[SERVER] Cập nhật danh sách kênh: {self.channels}\n")
                    log_event(f"Cập nhật danh sách kênh: {self.channels}")
                self.server_socket.settimeout(None)
                return
            except Exception as e:
                error_msg = f"[ERROR] Không thể lấy danh sách kênh (lần thử {attempt+1}/{retries}): {type(e).__name__}: {str(e)}"
                self.chat_area.insert(tk.END, f"{error_msg}\n")
                log_event(error_msg)
                if attempt == retries - 1 and not self.channels:
                    self.channels = ["general"]
                    self.update_channel_menu()
                    log_event("Sử dụng danh sách kênh mặc định: ['general']")
                time.sleep(1)
        self.server_socket.settimeout(None)

    def update_peer_listbox(self):
        self.peer_listbox.delete(0, tk.END)
        if not isinstance(self.peers, list):
            self.chat_area.insert(tk.END, f"[ERROR] Định dạng danh sách peer không hợp lệ: {self.peers}\n")
            return
        for peer in self.peers:
            try:
                status = "Khách" if peer['visitor'] else "Người dùng"
                self.peer_listbox.insert(tk.END, f"{peer['username']} ({status})")
            except (KeyError, TypeError) as e:
                self.chat_area.insert(tk.END, f"[ERROR] Dữ liệu peer không hợp lệ: {peer}, lỗi: {e}\n")

    def update_channel_menu(self):
        self.channel_listbox.delete(0, tk.END)
        for channel in self.channels:
            self.channel_listbox.insert(tk.END, f"# {channel}")

    def create_channel(self):
        if self.is_visitor:
            messagebox.showwarning("Cảnh báo", "Khách không thể tạo kênh!")
            return
        channel_name = simpledialog.askstring("Tạo kênh", "Nhập tên kênh:")
        if not channel_name or channel_name in self.channels:
            messagebox.showwarning("Cảnh báo", "Tên kênh không hợp lệ hoặc đã tồn tại!")
            return
        self.notify_server_new_channel(channel_name)

    def notify_server_new_channel(self, channel_name):
        data = {"type": "create_channel", "channel": channel_name, "username": USERNAME, "request_id": str(self.request_counter)}
        self.request_counter += 1
        try:
            self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            self.server_socket.settimeout(15)
            response = ""
            while True:
                chunk = self.server_socket.recv(1024).decode('utf-8')
                if not chunk:
                    break
                response += chunk
                if '\n' in response:
                    response = response.split('\n')[0]
                    break
            if not response:
                raise ValueError("Phản hồi từ server rỗng")
            response_data = json.loads(response)
            if response_data.get("status") == "success":
                self.channels.append(channel_name)
                self.owned_channels.append(channel_name)
                self.update_channel_menu()
                self.switch_channel(channel_name)
                self.chat_area.insert(tk.END, f"[SERVER RESPONSE] {response_data.get('message', 'Kênh được tạo thành công')}\n")
                log_event(f"Tạo kênh: {channel_name} bởi {USERNAME}")
            else:
                self.chat_area.insert(tk.END, f"[ERROR] {response_data.get('error', 'Không thể tạo kênh')}\n")
                log_event(f"Lỗi tạo kênh: {response_data.get('error')}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Không thể tạo kênh: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            self.reconnect()

    def switch_channel(self, channel):
        if not isinstance(channel, str) or channel not in self.channels:
            self.chat_area.insert(tk.END, f"[ERROR] Kênh không hợp lệ: {channel}\n")
            log_event(f"Kênh không hợp lệ trong switch_channel: {channel}")
            self.channels = ["general"]
            self.update_channel_menu()
            channel = "general"

        self.current_channel = channel
        self.chat_frame.config(text=f"Chat (Kênh: {self.current_channel})")
        
        # Xóa nội dung chat_area
        self.chat_area.delete(1.0, tk.END)
        log_event(f"Chuyển sang kênh: {channel}")

        # Khởi tạo danh sách tin nhắn nếu kênh chưa có
        if channel not in self.messages:
            self.messages[channel] = []
        if channel not in self.displayed_messages:
            self.displayed_messages[channel] = set()

        # Lấy tin nhắn từ server
        server_messages = sync_from_server(self.server_socket, channel)
        if isinstance(server_messages, list):
            current_messages = set(self.messages[channel])
            current_messages.update(server_messages)
            self.messages[channel] = list(current_messages)
            log_event(f"Lấy {len(server_messages)} tin nhắn từ server cho kênh {channel}")
        else:
            log_event(f"Không lấy được tin nhắn hợp lệ từ server cho kênh {channel}, giữ tin nhắn cục bộ")

        # Hiển thị tin nhắn của kênh hiện tại
        self.displayed_messages[channel].clear()
        for msg in self.messages[channel]:
            if msg not in self.displayed_messages[channel]:
                self.chat_area.insert(tk.END, f"{msg}\n")
                self.displayed_messages[channel].add(msg)
        log_event(f"Hiển thị {len(self.messages[channel])} tin nhắn trong kênh {channel}")

        # Xóa các video livestream từ kênh trước (nếu có)
        for peer in list(self.video_windows.keys()):
            label = self.video_windows[peer]
            label.destroy()
        self.video_windows.clear()
        self.is_primary_streamer = False
        self.primary_streamer = None

        # Lưu tin nhắn sau khi chuyển kênh
        save_messages(self.messages)

    def connect_to_all_peers(self):
        self.peers = self.get_peer_list()
        if not self.peers:
            return
        for peer in self.peers:
            if peer['port'] != PEER_PORT and (peer['ip'], peer['port']) not in peer_connections and peer['online']:
                try:
                    peer_connect(peer)
                    self.chat_area.insert(tk.END, f"[P2P] Kết nối với {peer['username']}\n")
                    log_event(f"Đã kết nối với {peer['username']}")
                except Exception as e:
                    self.chat_area.insert(tk.END, f"[P2P ERROR] Không thể kết nối với {peer['username']}: {e}\n")
                    log_event(f"Không thể kết nối với {peer['username']}: {e}")

    def receive_message(self, msg_data, s):
        try:
            if msg_data.get("type") == "notification":
                channel = msg_data.get("channel", "general")
                msg = msg_data.get("message", "")
                if channel not in self.messages:
                    self.messages[channel] = []
                if channel not in self.displayed_messages:
                    self.displayed_messages[channel] = set()
                if msg not in self.messages[channel]:
                    self.messages[channel].append(msg)
                    log_event(f"Nhận tin nhắn thông báo P2P cho kênh {channel}: {msg}")
                if channel == self.current_channel and msg not in self.displayed_messages[channel]:
                    self.chat_area.insert(tk.END, f"[Mới] {msg}\n")
                    self.displayed_messages[channel].add(msg)
                log_message(channel, msg, USERNAME, deleted=False)
            elif msg_data.get("type") == "channel_creation":
                channel = msg_data.get("channel", "general")
                msg = msg_data.get("message", "")
                if channel not in self.channels:
                    self.channels.append(channel)
                    self.update_channel_menu()
                if channel not in self.messages:
                    self.messages[channel] = []
                if channel not in self.displayed_messages:
                    self.displayed_messages[channel] = set()
                if msg not in self.messages[channel]:
                    self.messages[channel].append(msg)
                    log_event(f"Nhận thông báo tạo kênh P2P: {msg}")
                if channel == self.current_channel and msg not in self.displayed_messages[channel]:
                    self.chat_area.insert(tk.END, f"{msg}\n")
                    self.displayed_messages[channel].add(msg)
                log_message(channel, msg, "system", deleted=False)
                self.get_channel_list()
            elif msg_data.get("type") == "livestream_start":
                channel = msg_data.get("channel", "general")
                msg = msg_data.get("message", "")
                streamer = msg_data.get("username")
                if channel not in self.messages:
                    self.messages[channel] = []
                if channel not in self.displayed_messages:
                    self.displayed_messages[channel] = set()
                if msg not in self.messages[channel]:
                    self.messages[channel].append(msg)
                    log_event(f"Nhận thông báo bắt đầu livestream P2P: {msg}")
                if channel == self.current_channel and msg not in self.displayed_messages[channel]:
                    self.chat_area.insert(tk.END, f"[Livestream] {msg}\n")
                    self.displayed_messages[channel].add(msg)
                log_message(channel, msg, "system", deleted=False)
            elif msg_data.get("type") == "livestream_stop":
                channel = msg_data.get("channel", "general")
                msg = msg_data.get("message", "")
                streamer = msg_data.get("username")
                if channel not in self.messages:
                    self.messages[channel] = []
                if channel not in self.displayed_messages:
                    self.displayed_messages[channel] = set()
                if msg not in self.messages[channel]:
                    self.messages[channel].append(msg)
                    log_event(f"Nhận thông báo dừng livestream P2P: {msg}")
                if channel == self.current_channel and msg not in self.displayed_messages[channel]:
                    self.chat_area.insert(tk.END, f"[Livestream] {msg}\n")
                    self.displayed_messages[channel].add(msg)
                log_message(channel, msg, "system", deleted=False)
            elif msg_data.get("type") == "new_primary_streamer":
                channel = msg_data.get("channel", "general")
                msg = msg_data.get("message", "")
                primary_username = msg_data.get("primary_username")
                if channel not in self.messages:
                    self.messages[channel] = []
                if channel not in self.displayed_messages:
                    self.displayed_messages[channel] = set()
                if msg not in self.messages[channel]:
                    self.messages[channel].append(msg)
                    log_event(f"Nhận thông báo peer chính mới: {msg}")
                if channel == self.current_channel and msg not in self.displayed_messages[channel]:
                    self.chat_area.insert(tk.END, f"{msg}\n")
                    self.displayed_messages[channel].add(msg)
                    self.primary_streamer = primary_username
                    if primary_username == USERNAME:
                        self.is_primary_streamer = True
                    else:
                        self.is_primary_streamer = False
                        if self.cap:
                            self.stop_camera()
                            log_event(f"Peer {USERNAME} không còn là peer chính, dừng camera")
                log_message(channel, msg, "system", deleted=False)
            else:
                channel = msg_data.get("channel", "general")
                if channel not in self.messages:
                    self.messages[channel] = []
                if channel not in self.displayed_messages:
                    self.displayed_messages[channel] = set()
                if msg_data['message'] not in self.messages[channel]:
                    self.messages[channel].append(msg_data['message'])
                    log_event(f"Nhận tin nhắn P2P cho kênh {channel}: {msg_data['message']}")
                if channel == self.current_channel and msg_data['message'] not in self.displayed_messages[channel]:
                    self.chat_area.insert(tk.END, f"[Peer] {msg_data['message']}\n")
                    self.displayed_messages[channel].add(msg_data['message'])
                log_message(channel, msg_data['message'], USERNAME, deleted=False)
            # Lưu tin nhắn sau khi nhận
            save_messages(self.messages)
        except Exception as e:
            self.chat_area.insert(tk.END, f"[ERROR] Xử lý tin nhắn: {type(e).__name__}: {str(e)}\n")
            log_event(f"Lỗi xử lý tin nhắn: {type(e).__name__}: {str(e)}")

    def start_networking(self):
        try:
            self.server_socket = self.create_socket()
            threading.Thread(target=listen_for_connections, args=(PEER_PORT,), daemon=True).start()
            log_event("Bắt đầu networking")
        except Exception as e:
            error_msg = f"[ERROR] Không thể bắt đầu networking: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            messagebox.showerror("Lỗi", "Không thể khởi động networking. Vui lòng thử lại!")
            self.exit_ui()

    def start_channel_sync(self):
        self.get_channel_list()
        self.root.after(15000, self.start_channel_sync)

    def send_channel_message(self):
        if self.is_visitor:
            messagebox.showwarning("Cảnh báo", "Khách không thể gửi tin nhắn!")
            return
        message = self.message_entry.get().strip()
        if not message:
            return
        msg_data = {"channel": self.current_channel, "message": f"{USERNAME}: {message}"}
        if not peer_status["online"]:
            add_unsynced_content(self.current_channel, msg_data["message"])
        else:
            self.connect_to_all_peers()
            send_message_to_all_peers(json.dumps(msg_data) + '\n')
        if msg_data["message"] not in self.messages.get(self.current_channel, []):
            self.messages.setdefault(self.current_channel, []).append(msg_data["message"])
            if self.current_channel in self.displayed_messages:
                self.displayed_messages[self.current_channel].add(msg_data["message"])
            self.chat_area.insert(tk.END, f"[Bạn] {message}\n")
        log_message(self.current_channel, msg_data["message"], USERNAME, deleted=False)
        self.message_entry.delete(0, tk.END)
        log_event(f"Gửi tin nhắn đến kênh {self.current_channel}: {message}")
        # Lưu tin nhắn sau khi gửi
        save_messages(self.messages)

    def send_to_peer(self):
        if self.is_visitor:
            messagebox.showwarning("Cảnh báo", "Khách không thể gửi tin nhắn!")
            return
        selected = self.peer_listbox.curselection()
        if not selected:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn một peer trước!")
            return
        peer = self.peers[selected[0]]
        message = self.message_entry.get().strip()
        if not message:
            return
        if (peer['ip'], peer['port']) not in peer_connections:
            try:
                peer_connect(peer)
            except Exception as e:
                self.chat_area.insert(tk.END, f"[P2P ERROR] Không thể kết nối với {peer['username']}: {e}\n")
                return
        msg_data = {"channel": self.current_channel, "message": f"{USERNAME}: {message}"}
        if not peer_status["online"]:
            add_unsynced_content(self.current_channel, msg_data["message"])
        else:
            try:
                send_message_to_peer(peer, json.dumps(msg_data) + '\n')
                self.chat_area.insert(tk.END, f"[Đến {peer['username']}] {message}\n")
            except Exception as e:
                self.chat_area.insert(tk.END, f"[P2P ERROR] Không thể gửi đến {peer['username']}: {e}\n")
        self.message_entry.delete(0, tk.END)
        log_event(f"Gửi tin nhắn đến peer {peer['username']}: {message}")
        # Lưu tin nhắn sau khi gửi
        save_messages(self.messages)

    def broadcast_message(self):
        if self.is_visitor:
            messagebox.showwarning("Cảnh báo", "Khách không thể gửi tin nhắn!")
            return
        message = self.message_entry.get().strip()
        if not message:
            return
        msg_data = {"channel": self.current_channel, "message": f"{USERNAME}: {message}"}
        if not peer_status["online"]:
            add_unsynced_content(self.current_channel, msg_data["message"])
        else:
            self.connect_to_all_peers()
            send_message_to_all_peers(json.dumps(msg_data) + '\n')
        if msg_data["message"] not in self.messages.get(self.current_channel, []):
            self.messages.setdefault(self.current_channel, []).append(msg_data["message"])
            if self.current_channel in self.displayed_messages:
                self.displayed_messages[self.current_channel].add(msg_data["message"])
            self.chat_area.insert(tk.END, f"[Broadcast] {message}\n")
        self.message_entry.delete(0, tk.END)
        log_event(f"Broadcast tin nhắn đến kênh {self.current_channel}: {message}")
        # Lưu tin nhắn sau khi gửi
        save_messages(self.messages)

    def refresh_peer_list(self):
        self.peers = self.get_peer_list()
        self.connect_to_all_peers()

    def start_camera(self):
        try:
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                self.cap.release()
                self.cap = None
                messagebox.showerror("Lỗi", "Không thể mở camera! Có thể camera đang được sử dụng hoặc không khả dụng.")
                log_event("Không thể mở camera: Camera không khả dụng")
                return False
            log_event("Camera mở thành công cho livestream")
            self.is_streaming = True
            create_video_label(USERNAME)
            log_event("Tạo nhãn video cho chính mình (streamer)")
            self.update_video_frame()
            return True
        except Exception as e:
            self.cap = None
            messagebox.showerror("Lỗi", f"Không thể mở camera: {str(e)}")
            log_event(f"Lỗi mở camera: {type(e).__name__}: {str(e)}")
            return False

    def update_video_frame(self):
        if self.is_streaming and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.resize(frame, (320, 240))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)
                if USERNAME in self.video_windows:
                    label = self.video_windows[USERNAME]
                    label.imgtk = imgtk
                    label.configure(image=imgtk)
            self.root.after(10, self.update_video_frame)
        else:
            if USERNAME in self.video_windows:
                label = self.video_windows[USERNAME]
                label.configure(image="")

    def stop_camera(self):
        if self.cap:
            self.is_streaming = False
            self.cap.release()
            self.cap = None
            if USERNAME in self.video_windows:
                label = self.video_windows[USERNAME]
                label.destroy()
                del self.video_windows[USERNAME]
            log_event("Camera dừng")

    def create_video_window(self):
        """Tạo cửa sổ video riêng khi bắt đầu livestream"""
        if self.video_window is None:
            self.video_window = tk.Toplevel(self.root)
            self.video_window.title(f"Livestream - {USERNAME}")
            self.video_window.geometry("400x300")
            self.video_window.configure(bg="#36393F")
            self.video_frame = tk.LabelFrame(self.video_window, text="Livestream Video", font=("Helvetica", 10, "bold"), bg="#36393F", fg="#DCDDDE", bd=0)
            self.video_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            log_event("Tạo cửa sổ video riêng")
            # Gắn sự kiện đóng cửa sổ để dừng livestream
            self.video_window.protocol("WM_DELETE_WINDOW", self.stop_livestream_ui)

    def close_video_window(self):
        """Đóng cửa sổ video khi dừng livestream"""
        if self.video_window is not None:
            self.video_window.destroy()
            self.video_window = None
            self.video_frame = None
            log_event("Đóng cửa sổ video riêng")

    def go_online_ui(self):
        go_online(self.server_socket)
        sync_to_server(self.server_socket)
        self.chat_area.insert(tk.END, "[STATUS] Peer hiện đang online.\n")
        self.connect_to_all_peers()
        self.submit_info(visitor=self.is_visitor, password=self.password)
        self.update_status(online=True, invisible=False)
        
        # Tải tin nhắn mới từ server mà không reset chat_area
        new_messages = sync_from_server(self.server_socket, self.current_channel)
        if isinstance(new_messages, list):
            # Tích hợp tin nhắn mới vào danh sách hiện tại
            current_messages = set(self.messages.get(self.current_channel, []))
            current_messages.update(new_messages)
            self.messages[self.current_channel] = list(current_messages)
            log_event(f"Lấy {len(new_messages)} tin nhắn từ server cho kênh {self.current_channel}")
            
            # Hiển thị chỉ các tin nhắn mới
            for msg in new_messages:
                if msg not in self.displayed_messages.get(self.current_channel, set()):
                    self.chat_area.insert(tk.END, f"{msg}\n")
                    self.displayed_messages.setdefault(self.current_channel, set()).add(msg)
        else:
            log_event(f"Không lấy được tin nhắn hợp lệ từ server cho kênh {self.current_channel}, giữ tin nhắn cục bộ")
        
        log_event("Làm mới tin nhắn sau khi online, giữ lại tin nhắn cũ")
        # Lưu tin nhắn sau khi online
        save_messages(self.messages)

    def go_offline_ui(self):
        go_offline()
        self.chat_area.insert(tk.END, "[STATUS] Peer hiện đang offline.\n")
        log_event(f"Peer {USERNAME} đã offline")
        if self.update_status(online=False, invisible=False):
            for addr, conn in list(peer_connections.items()):
                try:
                    conn.close()
                    peer_connections.pop(addr)
                    log_event(f"Đóng kết nối P2P đến {addr}")
                except Exception as e:
                    log_event(f"Lỗi đóng kết nối P2P đến {addr}: {e}")
            for addr, conn in list(video_connections.items()):
                try:
                    conn.close()
                    video_connections.pop(addr)
                    log_event(f"Đóng kết nối video đến {addr}")
                except Exception as e:
                    log_event(f"Lỗi đóng kết nối video đến {addr}: {e}")
        else:
            self.chat_area.insert(tk.END, "[ERROR] Không thể cập nhật trạng thái offline\n")
        # Lưu tin nhắn sau khi offline
        save_messages(self.messages)

    def go_invisible_ui(self):
        go_invisible()
        self.chat_area.insert(tk.END, "[STATUS] Peer hiện đang ẩn danh.\n")
        self.submit_info(visitor=self.is_visitor, password=self.password)
        self.update_status(online=False, invisible=True)
        log_event(f"Peer {USERNAME} đã ẩn danh")
        # Lưu tin nhắn sau khi ẩn danh
        save_messages(self.messages)

    def start_livestream_ui(self):
        if self.is_visitor:
            messagebox.showwarning("Cảnh báo", "Khách không thể bắt đầu livestream!")
            return
        try:
            # Tạo cửa sổ video riêng
            self.create_video_window()
            # Khởi động camera
            if not self.start_camera():
                self.chat_area.insert(tk.END, "[ERROR] Không thể bắt đầu livestream do lỗi camera.\n")
                log_event("Hủy livestream do lỗi camera")
                self.close_video_window()
                return

            self.peers = self.get_peer_list()
            target_peers = [
                {"username": peer['username'], "ip": peer['ip'], "port": peer['port']}
                for peer in self.peers if peer['port'] != PEER_PORT and peer['username'] != USERNAME
            ]
            data = {
                "type": "start_livestream",
                "channel": self.current_channel,
                "username": USERNAME,
                "request_id": str(self.request_counter),
                "target_peers": target_peers
            }
            self.request_counter += 1
            self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            self.server_socket.settimeout(15)
            response = ""
            while True:
                chunk = self.server_socket.recv(1024).decode('utf-8')
                if not chunk:
                    break
                response += chunk
                if '\n' in response:
                    response = response.split('\n')[0]
                    break
            if not response:
                raise ValueError("Phản hồi từ server rỗng")
            response_data = json.loads(response)
            if response_data.get("status") == "success":
                start_livestreaming()
                self.is_streaming = True
                self.is_primary_streamer = True
                self.chat_area.insert(tk.END, "[STATUS] Livestream bắt đầu (chỉ xem cục bộ).\n")
                log_event(f"Bắt đầu livestream cục bộ trong kênh {self.current_channel}")
            else:
                messagebox.showerror("Lỗi", response_data.get("error", "Không thể bắt đầu livestream!"))
                log_event(f"Lỗi bắt đầu livestream: {response_data.get('error')}")
                self.stop_camera()
                self.close_video_window()
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Không thể bắt đầu livestream: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            self.stop_camera()
            self.close_video_window()
            self.reconnect()
        # Lưu tin nhắn sau khi bắt đầu livestream
        save_messages(self.messages)

    def stop_livestream_ui(self):
        stop_livestreaming()
        self.is_streaming = False
        self.is_primary_streamer = False
        self.stop_camera()
        self.close_video_window()
        self.chat_area.insert(tk.END, "[STATUS] Livestream kết thúc.\n")
        try:
            data = {
                "type": "stop_livestream",
                "channel": self.current_channel,
                "username": USERNAME,
                "request_id": str(self.request_counter)
            }
            self.request_counter += 1
            self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            self.server_socket.settimeout(15)
            response = ""
            while True:
                chunk = self.server_socket.recv(1024).decode('utf-8')
                if not chunk:
                    break
                response += chunk
                if '\n' in response:
                    response = response.split('\n')[0]
                    break
            if not response:
                raise ValueError("Phản hồi từ server rỗng")
            response_data = json.loads(response)
            if response_data.get("status") == "success":
                self.chat_area.insert(tk.END, f"[SERVER RESPONSE] {response_data.get('message', 'Livestream kết thúc')}\n")
                log_event(f"Kết thúc livestream trong kênh {self.current_channel}")
            else:
                error_msg = response_data.get("error", "Không thể kết thúc livestream!")
                self.chat_area.insert(tk.END, f"[ERROR] {error_msg}\n")
                log_event(f"Lỗi kết thúc livestream: {error_msg}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Không thể kết thúc livestream: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            self.reconnect()
        # Lưu tin nhắn sau khi dừng livestream
        save_messages(self.messages)

    def update_status(self, online=True, invisible=False):
        data = {
            "type": "update_status",
            "port": PEER_PORT,
            "username": USERNAME,
            "session_id": SESSION_ID,
            "online": online,
            "invisible": invisible,
            "request_id": str(self.request_counter)
        }
        self.request_counter += 1
        try:
            self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
            self.server_socket.settimeout(15)
            response = ""
            while True:
                chunk = self.server_socket.recv(1024).decode('utf-8')
                if not chunk:
                    break
                response += chunk
                if '\n' in response:
                    response = response.split('\n')[0]
                    break
            if not response:
                raise ValueError("Phản hồi từ server rỗng")
            log_event(f"Cập nhật trạng thái: online={online}, invisible={invisible}, phản hồi: {response}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Không thể cập nhật trạng thái: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            return False
        # Lưu tin nhắn sau khi cập nhật trạng thái
        save_messages(self.messages)
        return True

    def exit_ui(self):
        if messagebox.askokcancel("Thoát", "Bạn có chắc chắn muốn thoát?"):
            self.stop_camera()
            self.close_video_window()
            for peer in list(self.video_windows.keys()):
                label = self.video_windows[peer]
                label.destroy()
            self.video_windows.clear()
            data = {
                "type": "disconnect",
                "port": PEER_PORT,
                "username": USERNAME,
                "session_id": SESSION_ID,
                "request_id": str(self.request_counter)
            }
            self.request_counter += 1
            try:
                self.server_socket.sendall((json.dumps(data) + '\n').encode('utf-8'))
                self.server_socket.close()
            except Exception as e:
                log_event(f"Lỗi khi ngắt kết nối với server: {type(e).__name__}: {str(e)}")
            for addr, conn in list(peer_connections.items()):
                try:
                    conn.close()
                    peer_connections.pop(addr)
                    log_event(f"Đóng kết nối P2P với {addr}")
                except Exception as e:
                    log_event(f"Lỗi khi đóng kết nối P2P với {addr}: {type(e).__name__}: {str(e)}")
            for addr, conn in list(video_connections.items()):
                try:
                    conn.close()
                    video_connections.pop(addr)
                    log_event(f"Đóng kết nối video với {addr}")
                except Exception as e:
                    log_event(f"Lỗi khi đóng kết nối video với {addr}: {type(e).__name__}: {str(e)}")
            # Lưu tin nhắn trước khi thoát
            save_messages(self.messages)
            self.root.quit()
            log_event(f"Client thoát: {USERNAME}")

if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    app = ChatApp(root)
    root.mainloop()