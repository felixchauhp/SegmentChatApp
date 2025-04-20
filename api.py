# api.py
from flask import Flask, jsonify, request
from sync import channel_storage
from utils import log_event
from message_log import log_message

app = Flask(__name__)

@app.route('/api/channels', methods=['GET'])
def get_channels():
    channels = list(channel_storage.keys())
    log_event(f"API: Fetched channel list: {channels}")
    return jsonify(channels)

@app.route('/api/channels/<channel>/messages', methods=['GET'])
def get_messages(channel):
    if channel not in channel_storage:
        log_event(f"API: Channel {channel} not found")
        return jsonify({"error": "Channel not found"}), 404
    messages = channel_storage[channel]
    log_event(f"API: Fetched {len(messages)} messages for channel {channel}")
    return jsonify(messages)

@app.route('/api/channels/<channel>/messages', methods=['POST'])
def post_message(channel):
    if channel not in channel_storage:
        log_event(f"API: Channel {channel} not found")
        return jsonify({"error": "Channel not found"}), 404
    data = request.get_json()
    if not data or 'message' not in data:
        log_event(f"API: Invalid message data for channel {channel}")
        return jsonify({"error": "Invalid message data"}), 400
    message = data['message']
    channel_storage[channel].append(message)
    log_event(f"API: Posted message to channel {channel}: {message}")
    log_message(channel, message, "API", deleted=False)
    return jsonify({"status": "Message posted"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001)