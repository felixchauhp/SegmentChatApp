# p2p.py
import socket
import threading
import json
from utils import log_event
from message_log import log_message

peer_connections = {}

def receive_messages(s):
    """Hàm này được ghi đè bởi client.py"""
    pass

def listen_for_connections(peer_port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('0.0.0.0', peer_port))
    s.listen(5)
    print(f"[P2P] Listening on port {peer_port}...")
    while True:
        conn, addr = s.accept()
        print(f"[P2P] Connection established with {addr}")
        log_event(f"P2P connection established with {addr}")
        peer_connections[addr] = conn
        threading.Thread(target=receive_messages, args=(conn,), daemon=True).start()

def peer_connect(peer):
    try:
        print(f"[P2P] Connecting to {peer['username']} at {peer['ip']}:{peer['port']}...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((peer['ip'], peer['port']))
        peer_connections[(peer['ip'], peer['port'])] = s
        print(f"[P2P] Connected to {peer['username']}")
        log_event(f"P2P connected to {peer['username']} at {peer['ip']}:{peer['port']}")
        threading.Thread(target=receive_messages, args=(s,), daemon=True).start()
    except Exception as e:
        print(f"[P2P ERROR] Error connecting to peer: {e}")
        log_event(f"P2P error connecting to {peer['username']}: {e}")

def send_message_to_all_peers(message):
    for addr, conn in peer_connections.items():
        try:
            conn.sendall(message.encode('utf-8'))
            print(f"[P2P] Sent message to {addr}")
            log_event(f"P2P sent message to {addr}")
        except Exception as e:
            print(f"[P2P ERROR] Error sending message to {addr}: {e}")
            log_event(f"P2P error sending message to {addr}: {e}")

def send_message_to_peer(peer, message):
    try:
        conn = peer_connections.get((peer['ip'], peer['port']))
        if conn:
            conn.sendall(message.encode('utf-8'))
            print(f"[P2P] Sent message to {peer['username']}")
            log_event(f"P2P sent message to {peer['username']}")
        else:
            print(f"[P2P] Peer {peer['username']} is not connected.")
            log_event(f"P2P peer {peer['username']} not connected")
    except Exception as e:
        print(f"[P2P ERROR] Error sending message to peer: {e}")
        log_event(f"P2P error sending message to {peer['username']}: {e}")