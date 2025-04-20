# server.py
import socket
import threading
import json
from tracker import Tracker
from sync import sync_from_server, add_unsynced_content, channel_storage
from utils import log_event
from message_log import log_message

HOST = '0.0.0.0'
PORT = 5000

tracker = Tracker()
lock = threading.Lock()
api_started = False

def handle_client(conn, addr):
    with conn:
        print(f"[+] Connection from {addr}")
        log_event(f"Connection from {addr}")
        try:
            while True:
                conn.settimeout(10)
                data = conn.recv(4096)
                if not data:
                    break

                try:
                    request = json.loads(data.decode('utf-8'))
                except json.JSONDecodeError as e:
                    error_msg = f"[ERROR] Invalid JSON from {addr}: {e}"
                    print(error_msg)
                    log_event(error_msg)
                    continue

                if request['type'] == 'submit_info':
                    with lock:
                        peer_info = {
                            'ip': addr[0],
                            'port': request['port'],
                            'username': request['username'],
                            'session_id': request['session_id'],
                            'visitor': request.get('visitor', False),
                            'invisible': request.get('invisible', False),
                            'online': True
                        }
                        if not tracker.peer_exists(addr[0], request['port']):
                            tracker.add_peer(
                                addr[0], request['port'], request['username'],
                                request['session_id'], request.get('visitor', False),
                                request.get('invisible', False), True
                            )
                            print(f"[TRACKER] Added peer: {peer_info}")
                            conn.sendall(b"Info submitted successfully.")
                        else:
                            conn.sendall(b"Duplicate connection attempt.")

                elif request['type'] == 'get_list':
                    with lock:
                        peers = tracker.get_peers()
                        conn.sendall(json.dumps(peers).encode('utf-8'))
                        log_event(f"Sent peer list to {addr}: {len(peers)} peers")

                elif request['type'] == 'sync_upload':
                    channel = request['channel']
                    message = request['message']
                    add_unsynced_content(channel, message)
                    if channel not in channel_storage:
                        channel_storage[channel] = []
                    channel_storage[channel].append(message)
                    print(f"[SYNC] Added message to {channel}: {message}")
                    conn.sendall(b"Sync upload successful.")
                    notify_clients_new_message(channel, message)

                elif request['type'] == 'sync_download':
                    channel = request['channel']
                    content = sync_from_server(conn, channel)
                    conn.sendall(json.dumps(content).encode('utf-8'))

                elif request['type'] == 'disconnect':
                    with lock:
                        tracker.remove_peer(addr[0], request['port'])
                        print(f"[SERVER] Peer {addr[0]}:{request['port']} disconnected.")
                        conn.sendall(b"Peer disconnected successfully.")

                elif request['type'] == 'create_channel':
                    channel = request['channel']
                    with lock:
                        if channel not in channel_storage:
                            channel_storage[channel] = []
                            print(f"[SERVER] New channel created: {channel} by {request['username']}")
                            conn.sendall(f"Channel {channel} created successfully.".encode('utf-8'))
                        else:
                            conn.sendall(b"Channel already exists.")

                elif request['type'] == 'get_channel_list':
                    with lock:
                        try:
                            channels = list(channel_storage.keys())
                            if not channels:
                                channels = ["general"]
                            conn.sendall(json.dumps(channels).encode('utf-8'))
                            print(f"[SERVER] Sent channel list to {addr}: {channels}")
                            log_event(f"Sent channel list to {addr}: {channels}")
                        except Exception as e:
                            error_msg = f"[ERROR] Failed to send channel list to {addr}: {type(e).__name__}: {str(e)}"
                            print(error_msg)
                            log_event(error_msg)
                            conn.sendall(json.dumps(["general"]).encode('utf-8'))

                elif request['type'] == 'start_livestream':
                    channel = request['channel']
                    username = request['username']
                    notify_livestream_start(channel, username)
                    conn.sendall(b"Livestream started.")

                elif request['type'] == 'stop_livestream':
                    channel = request['channel']
                    username = request['username']
                    notify_livestream_stop(channel, username)
                    conn.sendall(b"Livestream stopped.")

                elif request['type'] == 'update_status':
                    with lock:
                        tracker.update_peer_status(
                            addr[0], request['port'], 
                            online=request.get('online', True),
                            invisible=request.get('invisible', False)
                        )
                        print(f"[TRACKER] Updated status for {addr[0]}:{request['port']}")
                        conn.sendall(b"Status updated.")

                else:
                    error_msg = f"[ERROR] Unknown request type from {addr}: {request['type']}"
                    print(error_msg)
                    log_event(error_msg)
                    conn.sendall(b"Unknown request type.")

        except Exception as e:
            print(f"[!] Error while handling client {addr}: {type(e).__name__}: {str(e)}")
            log_event(f"Error handling client {addr}: {e}")
        finally:
            conn.settimeout(None)

def notify_clients_new_message(channel, message):
    for peer in tracker.get_peers():
        if not peer['online']:
            continue
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((peer['ip'], peer['port']))
            notification = json.dumps({"type": "notification", "channel": channel, "message": message})
            s.sendall(notification.encode('utf-8'))
            s.close()
            log_message(channel, message, peer['username'], deleted=False)
        except Exception as e:
            print(f"[NOTIFY ERROR] Failed to notify {peer['username']}: {type(e).__name__}: {str(e)}")

def notify_livestream_start(channel, username):
    message = f"{username} started livestream in {channel}"
    for peer in tracker.get_peers():
        if not peer['online']:
            continue
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((peer['ip'], peer['port']))
            notification = json.dumps({
                "type": "livestream_start",
                "channel": channel,
                "message": message
            })
            s.sendall(notification.encode('utf-8'))
            s.close()
            log_message(channel, message, username, deleted=False)
            log_event(f"Notified {peer['username']} of livestream start in {channel}")
        except Exception as e:
            print(f"[NOTIFY ERROR] Failed to notify {peer['username']} of livestream: {type(e).__name__}: {str(e)}")

def notify_livestream_stop(channel, username):
    message = f"{username} stopped livestream in {channel}"
    for peer in tracker.get_peers():
        if not peer['online']:
            continue
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect((peer['ip'], peer['port']))
            notification = json.dumps({
                "type": "livestream_stop",
                "channel": channel,
                "message": message
            })
            s.sendall(notification.encode('utf-8'))
            s.close()
            log_message(channel, message, username, deleted=False)
            log_event(f"Notified {peer['username']} of livestream stop in {channel}")
        except Exception as e:
            print(f"[NOTIFY ERROR] Failed to notify {peer['username']} of livestream stop: {type(e).__name__}: {str(e)}")

def start_server():
    global api_started
    if not api_started:
        try:
            threading.Thread(
                target=lambda: __import__('api').app.run(host='0.0.0.0', port=5001),
                daemon=True
            ).start()
            api_started = True
            print("[API] Started on port 5001")
        except Exception as e:
            print(f"[API ERROR] Failed to start API: {type(e).__name__}: {str(e)}")
            log_event(f"Failed to start API: {e}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, PORT))
            s.listen()
            print(f"[SERVER] Listening on {HOST}:{PORT}...")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
            print(f"[SERVER ERROR] Failed to start server: {type(e).__name__}: {str(e)}")
            log_event(f"Failed to start server: {e}")

if __name__ == "__main__":
    channel_storage["general"] = []
    start_server()