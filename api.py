from flask import Flask, jsonify, request
from utils import log_event
from message_log import log_message
from database import save_message, get_messages, get_channels, create_channel
from datetime import datetime

app = Flask(__name__)

@app.route('/api/channels', methods=['GET'])
def get_channels_api():
    channels = get_channels()
    log_event(f"API: Lấy danh sách kênh: {channels}")
    return jsonify(channels)

@app.route('/api/channels/<channel>/messages', methods=['GET'])
def get_messages_api(channel):
    if channel not in get_channels():
        log_event(f"API: Kênh {channel} không tìm thấy")
        return jsonify({"error": "Kênh không tìm thấy"}), 404
    messages = get_messages(channel)
    formatted_messages = [f"{msg['sender']}: {msg['message']} [{msg['timestamp']}]" for msg in messages]
    log_event(f"API: Lấy {len(messages)} tin nhắn cho kênh {channel}")
    return jsonify(formatted_messages)

@app.route('/api/channels/<channel>/messages', methods=['POST'])
def post_message(channel):
    if channel not in get_channels():
        log_event(f"API: Kênh {channel} không tìm thấy")
        return jsonify({"error": "Kênh không tìm thấy"}), 404
    data = request.get_json()
    if not data or 'message' not in data:
        log_event(f"API: Dữ liệu tin nhắn không hợp lệ cho kênh {channel}")
        return jsonify({"error": "Dữ liệu tin nhắn không hợp lệ"}), 400
    message = data['message']
    sender = data.get('sender', 'API')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"{sender}: {message} [{timestamp}]"
    save_message(channel, sender, message, timestamp)
    log_event(f"API: Gửi tin nhắn đến kênh {channel}: {message}")
    log_message(channel, message, sender, deleted=False)
    return jsonify({"status": "Tin nhắn đã được gửi"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)