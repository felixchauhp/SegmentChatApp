# tracker.py
import threading
from utils import log_event

lock = threading.Lock()

class Tracker:
    def __init__(self):
        self.peers = []

    def add_peer(self, ip, port, username, session_id, visitor=False, invisible=False, online=True):
        peer_info = {
            'ip': ip,
            'port': port,
            'username': username,
            'session_id': session_id,
            'visitor': visitor,
            'invisible': invisible,
            'online': online
        }
        if not self.peer_exists(ip, port):
            self.peers.append(peer_info)
            log_event(f"Added peer: {peer_info}")

    def remove_peer(self, ip, port):
        self.peers = [peer for peer in self.peers if peer['ip'] != ip or peer['port'] != port]
        log_event(f"Removed peer: IP={ip}, Port={port}")

    def peer_exists(self, ip, port):
        return any(peer['ip'] == ip and peer['port'] == port for peer in self.peers)

    def update_peer_status(self, ip, port, online=True, invisible=False):
        for peer in self.peers:
            if peer['ip'] == ip and peer['port'] == port:
                peer['online'] = online
                peer['invisible'] = invisible
                log_event(f"Updated peer status: IP={ip}, Port={port}, online={online}, invisible={invisible}")
                break

    def get_peers(self):
        with lock:
            return [peer for peer in self.peers if not peer['invisible']]