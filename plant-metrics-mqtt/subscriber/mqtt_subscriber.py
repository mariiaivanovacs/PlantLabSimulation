"""
MQTT Subscriber — Plant Lab Simulation

Subscribes to companyA/+/environment, validates each message,
stores it to Firebase Firestore, and optionally publishes an ACK.

Usage:
    python subscriber/mqtt_subscriber.py

Environment (plant-metrics-mqtt/config/.env):
    MQTT_BROKER_URL        broker hostname (default: test.mosquitto.org)
    MQTT_PORT              broker port (default: 1883)
    MQTT_SUBSCRIBE_TOPIC   subscribe pattern (default: companyA/+/environment)
    MQTT_ACK_TOPIC         ack template (default: companyA/{gh_id}/ack)
    MQTT_QOS               QoS level (default: 1)
    MQTT_KEEPALIVE         keepalive seconds (default: 60)
"""

import sys
import os
import json
import logging
from pathlib import Path

# ── Load env ──────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / 'config' / '.env')
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
BROKER_URL = os.getenv('MQTT_BROKER_URL', 'test.mosquitto.org')
PORT = int(os.getenv('MQTT_PORT', '1883'))
SUBSCRIBE_TOPIC = os.getenv('MQTT_SUBSCRIBE_TOPIC', 'companyA/+/environment')
ACK_TOPIC_TEMPLATE = os.getenv('MQTT_ACK_TOPIC', 'companyA/{gh_id}/ack')
QOS = int(os.getenv('MQTT_QOS', '1'))
KEEPALIVE = int(os.getenv('MQTT_KEEPALIVE', '60'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SUBSCRIBER] %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f'Connected to {BROKER_URL}:{PORT}')
        client.subscribe(SUBSCRIBE_TOPIC, qos=QOS)
        logger.info(f'Subscribed to {SUBSCRIBE_TOPIC} (QoS={QOS})')
    else:
        logger.error(f'Broker connection failed (rc={rc})')


def on_message(client, userdata, msg):
    topic = msg.topic
    logger.info(f'Received on [{topic}] — {len(msg.payload)} bytes')

    try:
        payload = json.loads(msg.payload.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error(f'Invalid payload: {exc}')
        return

    from handlers import handle_message
    result = handle_message(topic, payload)

    # Send ACK if processing succeeded
    if result.get('success') and ACK_TOPIC_TEMPLATE:
        parts = topic.split('/')
        gh_id = parts[1] if len(parts) >= 2 else 'unknown'
        ack_topic = ACK_TOPIC_TEMPLATE.replace('{gh_id}', gh_id)
        ack = json.dumps({
            'status': 'received',
            'hour': payload.get('hour'),
            'doc_id': result.get('doc_id'),
        })
        client.publish(ack_topic, ack, qos=1)
        logger.debug(f'ACK → {ack_topic}')


def on_disconnect(client, userdata, rc):
    if rc != 0:
        logger.warning(f'Unexpected disconnect (rc={rc}) — paho will reconnect')


def run_subscriber():
    import paho.mqtt.client as mqtt

    client = mqtt.Client(client_id='plant-subscriber')
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    logger.info(f'Connecting to {BROKER_URL}:{PORT} …')
    client.connect(BROKER_URL, PORT, KEEPALIVE)

    logger.info('Entering subscriber loop (Ctrl-C to stop)')
    client.loop_forever()


if __name__ == '__main__':
    run_subscriber()
