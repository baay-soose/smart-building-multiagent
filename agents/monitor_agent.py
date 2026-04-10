import json
import logging
import threading
from datetime import datetime
from typing import Callable, Optional
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


# ------------------------------------------------------------------
# Seuils d'alerte par zone et par capteur
# ------------------------------------------------------------------
ALERT_THRESHOLDS = {
    "floor1": {
        "temperature": {"min": 16.0, "max": 28.0},
        "humidity":    {"min": 25.0, "max": 65.0},
        "co2_ppm":     {"min": 350,  "max": 1000},
    },
    "floor2": {
        "temperature": {"min": 16.0, "max": 28.0},
        "luminosity":  {"min": 100,  "max": 900},
    },
    "floor3": {
        "temperature": {"min": 16.0, "max": 28.0},
        "humidity":    {"min": 25.0, "max": 65.0},
        "smoke":       {"critical_if": 1},
    },
    "server_room": {
        "temperature":  {"min": 18.0, "max": 30.0},
        "cpu_load_pct": {"min": 0,    "max": 90},
        "power_w":      {"min": 0,    "max": 2000},
    },
}

# Niveaux de sévérité
SEVERITY_RULES = {
    "floor3":      {"smoke": "critical"},
    "server_room": {"temperature": "critical", "cpu_load_pct": "high"},
}


class MonitorAgent:
    """
    Agent de surveillance — souscrit à tous les topics MQTT
    et détecte les anomalies en comparant aux seuils définis.

    Lorsqu'une anomalie est détectée, il appelle le callback
    `on_anomaly` (branché sur l'agent d'analyse).
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        on_anomaly: Optional[Callable] = None,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.on_anomaly  = on_anomaly  # callable(anomaly_event: dict)
        self.logger      = logging.getLogger("MonitorAgent")

        self.client = mqtt.Client(client_id="monitor-agent")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Callbacks MQTT
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe("building/#", qos=1)
            self.logger.info("Connecté — souscrit à building/#")
        else:
            self.logger.error(f"Échec connexion MQTT, code : {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload  = json.loads(msg.payload.decode())
            location = payload.get("location", "unknown")
            values   = payload.get("values", {})
            sensor_id = payload.get("sensor_id", "unknown")

            anomalies = self._check_thresholds(location, values)

            if anomalies:
                event = {
                    "sensor_id":  sensor_id,
                    "location":   location,
                    "timestamp":  payload.get("timestamp", datetime.utcnow().isoformat()),
                    "values":     values,
                    "anomalies":  anomalies,
                }
                self._handle_anomaly(event)

        except Exception as e:
            self.logger.error(f"Erreur traitement message : {e}")

    # ------------------------------------------------------------------
    # Détection des anomalies
    # ------------------------------------------------------------------

    def _check_thresholds(self, location: str, values: dict) -> list:
        """
        Compare les valeurs reçues aux seuils de la zone.
        Retourne une liste d'anomalies détectées.
        """
        thresholds = ALERT_THRESHOLDS.get(location, {})
        anomalies  = []

        for metric, value in values.items():
            if metric == "anomaly":
                continue

            rules = thresholds.get(metric)
            if not rules:
                continue

            severity = self._get_severity(location, metric)

            # Seuil critique binaire (ex: smoke == 1)
            if "critical_if" in rules:
                if value == rules["critical_if"]:
                    anomalies.append({
                        "metric":   metric,
                        "value":    value,
                        "reason":   f"{metric} déclenché",
                        "severity": "critical",
                    })

            # Seuil min/max
            else:
                if "min" in rules and value < rules["min"]:
                    anomalies.append({
                        "metric":   metric,
                        "value":    value,
                        "threshold": rules["min"],
                        "reason":   f"{metric} trop bas ({value} < {rules['min']})",
                        "severity": severity,
                    })
                if "max" in rules and value > rules["max"]:
                    anomalies.append({
                        "metric":   metric,
                        "value":    value,
                        "threshold": rules["max"],
                        "reason":   f"{metric} trop élevé ({value} > {rules['max']})",
                        "severity": severity,
                    })

        return anomalies

    def _get_severity(self, location: str, metric: str) -> str:
        return SEVERITY_RULES.get(location, {}).get(metric, "medium")

    # ------------------------------------------------------------------
    # Gestion des anomalies
    # ------------------------------------------------------------------

    def _handle_anomaly(self, event: dict):
        severities = [a["severity"] for a in event["anomalies"]]
        max_sev    = "critical" if "critical" in severities else \
                     "high"     if "high"     in severities else "medium"

        self.logger.warning(
            f"[{max_sev.upper()}] Anomalie détectée — "
            f"{event['location']} | "
            + ", ".join(a["reason"] for a in event["anomalies"])
        )

        if self.on_anomaly:
            with self._lock:
                self.on_anomaly(event)

    # ------------------------------------------------------------------
    # Démarrage / arrêt
    # ------------------------------------------------------------------

    def start(self):
        self.client.connect(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()
        self.logger.info("MonitorAgent démarré.")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()
        self.logger.info("MonitorAgent arrêté.")


# ------------------------------------------------------------------
# Test standalone
# ------------------------------------------------------------------

if __name__ == "__main__":
    import time

    def print_anomaly(event):
        print("\n--- ANOMALIE REÇUE PAR CALLBACK ---")
        print(f"  Lieu      : {event['location']}")
        print(f"  Capteur   : {event['sensor_id']}")
        print(f"  Timestamp : {event['timestamp']}")
        for a in event["anomalies"]:
            print(f"  [{a['severity'].upper()}] {a['reason']}")
        print("------------------------------------\n")

    agent = MonitorAgent(on_anomaly=print_anomaly)
    agent.start()

    print("MonitorAgent actif — lance run_all.py dans un autre terminal.\nCtrl+C pour arrêter.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        agent.stop()
