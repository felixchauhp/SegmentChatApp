# client.py
import socket
import json
import uuid
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk, simpledialog
from sync import add_unsynced_content, sync_to_server, go_online, go_offline, start_livestreaming, stop_livestreaming, peer_status, sync_from_server, set_visitor_mode, set_authenticated_mode, go_invisible, app
from p2p import listen_for_connections, peer_connect, send_message_to_all_peers, send_message_to_peer, peer_connections
from utils import log_event
from message_log import log_message

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5000
PEER_PORT = 6000 + int(uuid.uuid4().int % 1000)
USERNAME = None
SESSION_ID = str(uuid.uuid4())

class ChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Segment Chat - Port {PEER_PORT}")
        self.root.geometry("800x600")
        self.root.minsize(400, 300)
        self.peers = []
        self.server_socket = None
        self.current_channel = "general"
        self.channels = ["general"]
        self.owned_channels = []
        self.is_visitor = False
        self.messages = {}
        self.create_widgets()
        self.start_networking()
        self.start_channel_sync()
        app = self

    def create_widgets(self):
        main_frame = tk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = tk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        login_frame = tk.LabelFrame(left_frame, text="Login")
        login_frame.pack(fill=tk.X, pady=5)
        tk.Label(login_frame, text="Username:").pack(pady=2)
        self.username_entry = tk.Entry(login_frame)
        self.username_entry.pack(fill=tk.X, padx=5)
        tk.Button(login_frame, text="Login as User", command=self.login_authenticated).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(login_frame, text="Join as Visitor", command=self.login_visitor).pack(side=tk.LEFT, padx=5, pady=5)

        peer_frame = tk.LabelFrame(left_frame, text="Peers")
        peer_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.peer_listbox = tk.Listbox(peer_frame, height=10, width=20)
        self.peer_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        tk.Button(peer_frame, text="Refresh Peers", command=self.refresh_peer_list).pack(pady=5)

        right_frame = tk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        channel_frame = tk.LabelFrame(right_frame, text="Channels")
        channel_frame.pack(fill=tk.X, pady=5)
        self.channel_var = tk.StringVar(value=self.current_channel)
        self.channel_menu = ttk.OptionMenu(channel_frame, self.channel_var, self.current_channel, *self.channels, command=self.switch_channel)
        self.channel_menu.pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(channel_frame, text="New Channel", command=self.create_channel).pack(side=tk.LEFT, padx=5, pady=5)

        self.chat_frame = tk.LabelFrame(right_frame, text=f"Chat (Channel: {self.current_channel})")
        self.chat_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.chat_area = scrolledtext.ScrolledText(self.chat_frame, height=15, width=50)
        self.chat_area.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        message_frame = tk.Frame(self.chat_frame)
        message_frame.pack(fill=tk.X, pady=5)
        self.message_entry = tk.Entry(message_frame, width=40)
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        tk.Button(message_frame, text="Send", command=self.send_channel_message).pack(side=tk.LEFT, padx=5)
        tk.Button(message_frame, text="Delete Last", command=self.delete_last_message).pack(side=tk.LEFT, padx=5)

        control_frame = tk.Frame(right_frame)
        control_frame.pack(fill=tk.X, pady=5)
        tk.Button(control_frame, text="Send to Peer", command=self.send_to_peer).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Broadcast", command=self.broadcast_message).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Go Online", command=self.go_online_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Go Offline", command=self.go_offline_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Go Invisible", command=self.go_invisible_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Start Livestream", command=self.start_livestream_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Stop Livestream", command=self.stop_livestream_ui).pack(side=tk.LEFT, padx=2)
        tk.Button(control_frame, text="Exit", command=self.exit_ui).pack(side=tk.RIGHT, padx=2)

    def login_authenticated(self):
        global USERNAME
        USERNAME = self.username_entry.get().strip()
        if not USERNAME:
            messagebox.showerror("Error", "Username cannot be empty!")
            return
        self.is_visitor = False
        self.username_entry.config(state="disabled")
        self.submit_info()
        self.get_channel_list()
        self.connect_to_all_peers()
        set_authenticated_mode()
        self.message_entry.config(state="normal")
        log_event(f"Logged in as authenticated user: {USERNAME}")

    def login_visitor(self):
        global USERNAME
        USERNAME = self.username_entry.get().strip() or f"Visitor_{SESSION_ID[:8]}"
        self.is_visitor = True
        self.username_entry.config(state="disabled")
        self.submit_info(visitor=True)
        self.get_channel_list()
        self.connect_to_all_peers()
        set_visitor_mode()
        self.message_entry.config(state="disabled")
        self.chat_area.insert(tk.END, "[INFO] Joined as visitor. You can only view messages.\n")
        log_event(f"Joined as visitor: {USERNAME}")

    def create_socket(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((SERVER_HOST, SERVER_PORT))
            s.settimeout(None)
            return s
        except Exception as e:
            error_msg = f"[ERROR] Failed to connect to server: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            raise

    def submit_info(self, visitor=False):
        data = {
            "type": "submit_info",
            "username": USERNAME,
            "port": PEER_PORT,
            "session_id": SESSION_ID,
            "visitor": visitor,
            "invisible": peer_status["invisible"]
        }
        try:
            self.server_socket.sendall(json.dumps(data).encode('utf-8'))
            self.server_socket.settimeout(10)
            response = self.server_socket.recv(1024).decode('utf-8')
            self.chat_area.insert(tk.END, f"[SERVER RESPONSE] {response}\n")
            log_event(f"Submitted info: {data}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Failed to submit info: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)

    def update_status(self, online=True, invisible=False):
        data = {
            "type": "update_status",
            "port": PEER_PORT,
            "online": online,
            "invisible": invisible
        }
        try:
            self.server_socket.sendall(json.dumps(data).encode('utf-8'))
            self.server_socket.settimeout(10)
            response = self.server_socket.recv(1024).decode('utf-8')
            log_event(f"Updated status: online={online}, invisible={invisible}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Failed to update status: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)

    def get_peer_list(self):
        try:
            data = {"type": "get_list"}
            self.server_socket.sendall(json.dumps(data).encode('utf-8'))
            self.server_socket.settimeout(10)
            response = self.server_socket.recv(4096).decode('utf-8')
            if not response:
                raise ValueError("Empty response from server")
            peer_data = json.loads(response)
            if not isinstance(peer_data, list):
                raise ValueError(f"Expected a list of peers, got: {peer_data}")
            self.peers = peer_data
            self.update_peer_listbox()
            self.server_socket.settimeout(None)
            return self.peers
        except Exception as e:
            error_msg = f"[ERROR] Failed to fetch peer list: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)
            self.peers = []
            return []

    def get_channel_list(self, retries=3):
        for attempt in range(retries):
            try:
                data = {"type": "get_channel_list"}
                self.server_socket.sendall(json.dumps(data).encode('utf-8'))
                self.server_socket.settimeout(10)
                response = self.server_socket.recv(4096).decode('utf-8')
                if not response:
                    raise ValueError("Empty response from server")
                new_channels = json.loads(response)
                if not isinstance(new_channels, list):
                    raise ValueError(f"Expected list of channels, got: {new_channels}")
                if new_channels != self.channels:
                    self.channels = new_channels
                    self.update_channel_menu()
                    self.chat_area.insert(tk.END, f"[SERVER] Updated channels: {self.channels}\n")
                    log_event(f"Updated channel list: {self.channels}")
                self.server_socket.settimeout(None)
                return
            except Exception as e:
                error_msg = f"[ERROR] Failed to fetch channel list (attempt {attempt+1}/{retries}): {type(e).__name__}: {str(e)}"
                self.chat_area.insert(tk.END, f"{error_msg}\n")
                # print(error_msg)
                # log_event(error_msg)
                if attempt == retries - 1:
                    self.channels = ["general"]
                    self.update_channel_menu()
                    # self.chat_area.insert(tk.END, "[ERROR] Using default channel list: ['general']\n")
                    log_event("Using default channel list: ['general']")
        self.server_socket.settimeout(None)

    def update_peer_listbox(self):
        self.peer_listbox.delete(0, tk.END)
        if not isinstance(self.peers, list):
            self.chat_area.insert(tk.END, f"[ERROR] Invalid peer list format: {self.peers}\n")
            return
        for peer in self.peers:
            try:
                status = "Visitor" if peer['visitor'] else "User"
                self.peer_listbox.insert(tk.END, f"{peer['username']} ({status}) @ {peer['ip']}:{peer['port']}")
            except (KeyError, TypeError) as e:
                self.chat_area.insert(tk.END, f"[ERROR] Malformed peer data: {peer}, error: {e}\n")

    def update_channel_menu(self):
        menu = self.channel_menu["menu"]
        menu.delete(0, "end")
        for channel in self.channels:
            menu.add_command(label=channel, command=lambda c=channel: self.channel_var.set(c) or self.switch_channel(c))
        if self.current_channel not in self.channels:
            self.channel_var.set(self.channels[0] if self.channels else "general")
            self.switch_channel(self.channel_var.get())

    def create_channel(self):
        if self.is_visitor:
            messagebox.showwarning("Warning", "Visitors cannot create channels!")
            return
        channel_name = simpledialog.askstring("Create Channel", "Enter channel name:")
        if not channel_name or channel_name in self.channels:
            messagebox.showwarning("Warning", "Channel name invalid or already exists!")
            return
        self.notify_server_new_channel(channel_name)

    def notify_server_new_channel(self, channel_name):
        data = {"type": "create_channel", "channel": channel_name, "username": USERNAME}
        try:
            self.server_socket.sendall(json.dumps(data).encode('utf-8'))
            self.server_socket.settimeout(10)
            response = self.server_socket.recv(1024).decode('utf-8')
            self.chat_area.insert(tk.END, f"[SERVER RESPONSE] {response}\n")
            self.channels.append(channel_name)
            self.owned_channels.append(channel_name)
            self.update_channel_menu()
            self.channel_var.set(channel_name)
            self.switch_channel(channel_name)
            log_event(f"Created channel: {channel_name} by {USERNAME}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Failed to create channel: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)

    def switch_channel(self, channel):
        self.current_channel = channel
        self.chat_frame.config(text=f"Chat (Channel: {self.current_channel})")
        self.chat_area.delete(1.0, tk.END)
        self.messages[channel] = sync_from_server(self.server_socket, channel)
        if not isinstance(self.messages[channel], list):
            self.messages[channel] = []
        for msg in self.messages[channel]:
            self.chat_area.insert(tk.END, f"{msg}\n")

    def connect_to_all_peers(self):
        self.peers = self.get_peer_list()
        if not self.peers:
            return
        for peer in self.peers:
            if peer['port'] != PEER_PORT and (peer['ip'], peer['port']) not in peer_connections:
                try:
                    peer_connect(peer)
                    self.chat_area.insert(tk.END, f"[P2P] Connected to {peer['username']}\n")
                except Exception as e:
                    self.chat_area.insert(tk.END, f"[P2P ERROR] Failed to connect to {peer['username']}: {e}\n")

    def receive_messages(self, s):
        if not peer_status["online"]:
            return
        try:
            while True:
                message = s.recv(1024).decode('utf-8')
                if not message:
                    break
                try:
                    msg_data = json.loads(message)
                    if msg_data.get("type") == "notification":
                        channel = msg_data.get("channel", "general")
                        msg = msg_data.get("message", "")
                        if channel not in self.messages:
                            self.messages[channel] = []
                        if channel == self.current_channel:
                            self.chat_area.insert(tk.END, f"[New] {msg}\n")
                            self.messages[channel].append(msg)
                        log_message(channel, msg, USERNAME, deleted=False)
                        continue
                    elif msg_data.get("type") == "livestream_start":
                        channel = msg_data.get("channel", "general")
                        msg = msg_data.get("message", "")
                        if channel not in self.messages:
                            self.messages[channel] = []
                        if channel == self.current_channel:
                            self.chat_area.insert(tk.END, f"[Livestream] {msg}\n")
                            self.messages[channel].append(msg)
                        log_message(channel, msg, "system", deleted=False)
                        continue
                    elif msg_data.get("type") == "livestream_stop":
                        channel = msg_data.get("channel", "general")
                        msg = msg_data.get("message", "")
                        if channel not in self.messages:
                            self.messages[channel] = []
                        if channel == self.current_channel:
                            self.chat_area.insert(tk.END, f"[Livestream] {msg}\n")
                            self.messages[channel].append(msg)
                        log_message(channel, msg, "system", deleted=False)
                        continue
                    elif msg_data.get("type") == "delete":
                        channel = msg_data.get("channel", "general")
                        msg = msg_data.get("message", "")
                        if channel == self.current_channel and channel in self.messages:
                            if msg in self.messages[channel]:
                                self.messages[channel].remove(msg)
                                self.chat_area.delete("1.0", tk.END)
                                for m in self.messages[channel]:
                                    self.chat_area.insert(tk.END, f"{m}\n")
                                log_message(channel, msg, USERNAME, deleted=True)
                        continue
                    channel = msg_data.get("channel", "general")
                    if channel not in self.messages:
                        self.messages[channel] = []
                    if channel == self.current_channel:
                        self.chat_area.insert(tk.END, f"[Peer] {msg_data['message']}\n")
                        self.messages[channel].append(msg_data['message'])
                        log_message(channel, msg_data['message'], USERNAME, deleted=False)
                except json.JSONDecodeError:
                    if self.current_channel == "general":
                        self.chat_area.insert(tk.END, f"[Peer] {message}\n")
        except ConnectionError as e:
            self.chat_area.insert(tk.END, f"[ERROR] Connection lost: {type(e).__name__}: {str(e)}\n")
            log_event(f"Connection lost in receive_messages: {e}")
        except Exception as e:
            self.chat_area.insert(tk.END, f"[ERROR] Receiving message: {type(e).__name__}: {str(e)}\n")
            log_event(f"Error receiving message: {e}")

    def start_networking(self):
        self.server_socket = self.create_socket()
        threading.Thread(target=listen_for_connections, args=(PEER_PORT,), daemon=True).start()
        import p2p
        p2p.receive_messages = self.receive_messages

    def start_channel_sync(self):
        self.get_channel_list()
        self.root.after(5000, self.start_channel_sync)

    def send_channel_message(self):
        if self.is_visitor:
            messagebox.showwarning("Warning", "Visitors cannot send messages!")
            return
        message = self.message_entry.get().strip()
        if not message:
            return
        msg_data = {"channel": self.current_channel, "message": f"{USERNAME}: {message}"}
        if not peer_status["online"]:
            add_unsynced_content(self.current_channel, msg_data["message"])
        else:
            self.connect_to_all_peers()
            send_message_to_all_peers(json.dumps(msg_data))
        self.chat_area.insert(tk.END, f"[You] {message}\n")
        if self.current_channel not in self.messages:
            self.messages[self.current_channel] = []
        self.messages[self.current_channel].append(msg_data["message"])
        log_message(self.current_channel, msg_data["message"], USERNAME, deleted=False)
        self.message_entry.delete(0, tk.END)
        log_event(f"Sent message to channel {self.current_channel}: {message}")

    def delete_last_message(self):
        if self.is_visitor:
            messagebox.showwarning("Warning", "Visitors cannot delete messages!")
            return
        if self.current_channel not in self.messages or not self.messages[self.current_channel]:
            messagebox.showwarning("Warning", "No messages to delete!")
            return
        last_message = self.messages[self.current_channel].pop()
        self.chat_area.delete("end-2l", "end-1l")
        log_message(self.current_channel, last_message, USERNAME, deleted=True)
        log_event(f"Deleted message in channel {self.current_channel}: {last_message}")
        msg_data = {"type": "delete", "channel": self.current_channel, "message": last_message}
        send_message_to_all_peers(json.dumps(msg_data))

    def send_to_peer(self):
        if self.is_visitor:
            messagebox.showwarning("Warning", "Visitors cannot send messages!")
            return
        selected = self.peer_listbox.curselection()
        if not selected:
            messagebox.showwarning("Warning", "Select a peer first!")
            return
        peer = self.peers[selected[0]]
        message = self.message_entry.get().strip()
        if not message:
            return
        if (peer['ip'], peer['port']) not in peer_connections:
            try:
                peer_connect(peer)
            except Exception as e:
                self.chat_area.insert(tk.END, f"[P2P ERROR] Failed to connect to {peer['username']}: {e}\n")
                return
        msg_data = {"channel": self.current_channel, "message": f"{USERNAME}: {message}"}
        if not peer_status["online"]:
            add_unsynced_content(self.current_channel, msg_data["message"])
        else:
            try:
                send_message_to_peer(peer, json.dumps(msg_data))
                self.chat_area.insert(tk.END, f"[To {peer['username']}] {message}\n")
            except Exception as e:
                self.chat_area.insert(tk.END, f"[P2P ERROR] Failed to send to {peer['username']}: {e}\n")
        self.message_entry.delete(0, tk.END)
        log_event(f"Sent message to peer {peer['username']}: {message}")

    def broadcast_message(self):
        if self.is_visitor:
            messagebox.showwarning("Warning", "Visitors cannot send messages!")
            return
        message = self.message_entry.get().strip()
        if not message:
            return
        msg_data = {"channel": self.current_channel, "message": f"{USERNAME}: {message}"}
        if not peer_status["online"]:
            add_unsynced_content(self.current_channel, msg_data["message"])
        else:
            self.connect_to_all_peers()
            send_message_to_all_peers(json.dumps(msg_data))
        self.chat_area.insert(tk.END, f"[Broadcast] {message}\n")
        self.message_entry.delete(0, tk.END)
        log_event(f"Broadcast message to channel {self.current_channel}: {message}")

    def refresh_peer_list(self):
        self.peers = self.get_peer_list()
        self.connect_to_all_peers()

    def go_online_ui(self):
        go_online(self.server_socket)
        self.chat_area.insert(tk.END, "[STATUS] Peer is now online.\n")
        self.connect_to_all_peers()
        self.submit_info(visitor=self.is_visitor)
        self.update_status(online=True, invisible=False)
        self.switch_channel(self.current_channel)

    def go_offline_ui(self):
        go_offline()
        self.chat_area.insert(tk.END, "[STATUS] Peer is now offline.\n")
        self.update_status(online=False, invisible=False)

    def go_invisible_ui(self):
        go_invisible()
        self.chat_area.insert(tk.END, "[STATUS] Peer is now invisible.\n")
        self.submit_info(visitor=self.is_visitor)
        self.update_status(online=False, invisible=True)

    def start_livestream_ui(self):
        if self.is_visitor:
            messagebox.showwarning("Warning", "Visitors cannot start livestream!")
            return
        start_livestreaming()
        self.chat_area.insert(tk.END, "[STATUS] Livestream started.\n")
        try:
            data = {
                "type": "start_livestream",
                "channel": self.current_channel,
                "username": USERNAME
            }
            self.server_socket.sendall(json.dumps(data).encode('utf-8'))
            self.server_socket.settimeout(10)
            response = self.server_socket.recv(1024).decode('utf-8')
            self.chat_area.insert(tk.END, f"[SERVER RESPONSE] {response}\n")
            log_event(f"Started livestream in channel {self.current_channel}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Failed to start livestream: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)

    def stop_livestream_ui(self):
        stop_livestreaming()
        self.chat_area.insert(tk.END, "[STATUS] Livestream ended.\n")
        try:
            data = {
                "type": "stop_livestream",
                "channel": self.current_channel,
                "username": USERNAME
            }
            self.server_socket.sendall(json.dumps(data).encode('utf-8'))
            self.server_socket.settimeout(10)
            response = self.server_socket.recv(1024).decode('utf-8')
            self.chat_area.insert(tk.END, f"[SERVER RESPONSE] {response}\n")
            log_event(f"Stopped livestream in channel {self.current_channel}")
            self.server_socket.settimeout(None)
        except Exception as e:
            error_msg = f"[ERROR] Failed to stop livestream: {type(e).__name__}: {str(e)}"
            self.chat_area.insert(tk.END, f"{error_msg}\n")
            log_event(error_msg)

    def exit_ui(self):
        if messagebox.askokcancel("Exit", "Are you sure you want to exit?"):
            data = {"type": "disconnect", "port": PEER_PORT}
            try:
                self.server_socket.sendall(json.dumps(data).encode('utf-8'))
                self.server_socket.close()
            except:
                pass
            self.root.quit()
            log_event(f"Client exited: {USERNAME}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatApp(root)
    root.mainloop()