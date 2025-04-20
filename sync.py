# sync.py
import json
import threading
from utils import log_event
from message_log import log_message

unsynced_content = {}
channel_sync_status = {}
peer_status = {
    "online": True,
    "livestreaming": False,
    "invisible": False,
    "visitor": False
}
channel_storage = {"general": []}
app = None

def add_unsynced_content(channel, message):
    if channel not in unsynced_content:
        unsynced_content[channel] = []
    unsynced_content[channel].append(message)
    channel_sync_status[channel] = False
    log_event(f"Added unsynced message to channel {channel}: {message}")

def sync_to_server(server_socket):
    for channel, messages in unsynced_content.items():
        for msg in messages:
            data = {"type": "sync_upload", "channel": channel, "message": msg}
            try:
                server_socket.sendall(json.dumps(data).encode('utf-8'))
                server_socket.settimeout(5)
                server_socket.recv(1024)
                log_event(f"Synced message to server: {msg} in channel {channel}")
                log_message(channel, msg, "system", deleted=False)
                server_socket.settimeout(None)
            except Exception as e:
                print(f"[SYNC ERROR] Failed to sync {channel}: {type(e).__name__}: {str(e)}")
                log_event(f"Failed to sync message: {msg} in channel {channel}")
                return False
        channel_sync_status[channel] = True
    unsynced_content.clear()
    print("[SYNC] All unsynced content uploaded.")
    return True

def sync_from_server(server_socket, channel):
    if app and channel in app.owned_channels and peer_status["online"] and not peer_status["visitor"]:
        content = channel_storage.get(channel, [])
        log_event(f"Fetched {len(content)} messages from channel_hosting (local) for channel {channel}")
        print(f"[SYNC] Fetched local content for {channel}: {content}")
        return content
    try:
        request = {"type": "sync_download", "channel": channel}
        server_socket.sendall(json.dumps(request).encode('utf-8'))
        server_socket.settimeout(5)
        response = server_socket.recv(4096).decode('utf-8')
        if not response:
            raise ValueError("Empty response from server")
        content = json.loads(response)
        log_event(f"Fetched {len(content)} messages from centralized_server for channel {channel}")
        print(f"[SYNC] Fetched content from server for {channel}: {content}")
        server_socket.settimeout(None)
        return content
    except Exception as e:
        print(f"[SYNC ERROR] Failed to fetch channel content: {type(e).__name__}: {str(e)}")
        log_event(f"Failed to fetch content for channel {channel}")
        return channel_storage.get(channel, [])

def go_offline():
    peer_status["online"] = False
    peer_status["invisible"] = False
    print("[STATUS] Peer is now offline.")
    log_event("Peer went offline")

def go_online(server_socket):
    peer_status["online"] = True
    peer_status["invisible"] = False
    print("[STATUS] Peer is now online. Syncing cached content...")
    log_event("Peer went online")
    sync_to_server(server_socket)

def go_invisible():
    peer_status["invisible"] = True
    peer_status["online"] = False
    print("[STATUS] Peer is now invisible.")
    log_event("Peer went invisible")

def set_visitor_mode():
    peer_status["visitor"] = True
    peer_status["online"] = True
    peer_status["invisible"] = False
    print("[STATUS] Peer is now in visitor mode.")
    log_event("Peer entered visitor mode")

def set_authenticated_mode():
    peer_status["visitor"] = False
    peer_status["online"] = True
    peer_status["invisible"] = False
    print("[STATUS] Peer is now in authenticated mode.")
    log_event("Peer entered authenticated mode")

def start_livestreaming():
    peer_status["livestreaming"] = True
    print("[STATUS] Livestream started.")
    log_event("Livestream started")

def stop_livestreaming():
    peer_status["livestreaming"] = False
    print("[STATUS] Livestream ended.")
    log_event("Livestream ended")