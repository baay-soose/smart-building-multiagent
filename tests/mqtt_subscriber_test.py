"""
Script de test — souscrit à tous les topics building/#
et affiche les messages reçus en temps réel.
Usage : python tests/mqtt_subscriber_test.py
"""
import json
import paho.mqtt.client as mqtt


BROKER_HOST = "localhost"
BROKER_PORT = 1883


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[OK] Connecté au broker {BROKER_HOST}:{BROKER_PORT}")
        client.subscribe("building/#")
        print("[OK] Souscrit à building/#\n")
    else:
        print(f"[ERREUR] Connexion échouée, code : {rc}")


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        sensor_id = payload.get("sensor_id", "?")
        location  = payload.get("location", "?")
        timestamp = payload.get("timestamp", "?")
        values    = payload.get("values", {})
        anomaly   = values.get("anomaly", None)

        flag = " ⚠ ANOMALIE" if anomaly else ""
        print(f"[{timestamp}] {sensor_id} ({location}){flag}")
        for k, v in values.items():
            if k != "anomaly":
                print(f"    {k}: {v}")
        print()

    except Exception as e:
        print(f"[ERREUR] Parsing message : {e}")


if __name__ == "__main__":
    client = mqtt.Client(client_id="test-subscriber")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    print("En attente de messages... Ctrl+C pour arrêter.\n")

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        client.disconnect()
        print("Arrêté.")
