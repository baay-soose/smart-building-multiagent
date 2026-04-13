import json
import time
import random
import threading
import logging
from datetime import datetime
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


class BaseSensor:
    """
    Classe parente pour tous les capteurs ESP32 simulés.
    Gère la connexion MQTT et la publication des données.
    Chaque sous-classe définit ses capteurs et ses anomalies.
    """

    def __init__(self, sensor_id: str, location: str, broker_host: str = "localhost", broker_port: int = 1883, publish_interval: int = 5):
        self.sensor_id = sensor_id
        self.location = location
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.publish_interval = publish_interval
        self.logger = logging.getLogger(sensor_id)
        self._running = False

        self.client = mqtt.Client(client_id=sensor_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    # ------------------------------------------------------------------
    # Callbacks MQTT
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info(f"Connecté au broker MQTT ({self.broker_host}:{self.broker_port})")
        else:
            self.logger.error(f"Échec connexion MQTT, code : {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.logger.warning("Déconnecté du broker MQTT")

    # ------------------------------------------------------------------
    # Méthodes à surcharger dans les sous-classes
    # ------------------------------------------------------------------

    def read_sensors(self) -> dict:
        """
        Retourne un dict avec les valeurs des capteurs.
        À implémenter dans chaque sous-classe.
        Exemple : {"temperature": 22.5, "humidity": 45.0}
        """
        raise NotImplementedError("read_sensors() doit être implémenté dans la sous-classe.")

    def inject_anomaly(self) -> dict:
        """
        Retourne des valeurs anormales pour les tests.
        Optionnel — retourne read_sensors() par défaut.
        """
        return self.read_sensors()

    # ------------------------------------------------------------------
    # Publication MQTT
    # ------------------------------------------------------------------

    def _build_payload(self, values: dict) -> dict:
        return {
            "sensor_id": self.sensor_id,
            "location": self.location,
            "timestamp": datetime.utcnow().isoformat(),
            "values": values,
        }

    def publish(self, topic: str, values: dict):
        payload = json.dumps(self._build_payload(values))
        result = self.client.publish(topic, payload, qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            self.logger.info(f"→ {topic} | {values}")
        else:
            self.logger.error(f"Erreur publication sur {topic}")

    # ------------------------------------------------------------------
    # Boucle principale
    # ------------------------------------------------------------------

    def _loop(self, anomaly_probability: float = 0.05):
        """
        Boucle de publication. Toutes les `publish_interval` secondes,
        lit les capteurs et publie. Avec une faible probabilité,
        injecte une anomalie à la place.
        """
        base_topic = f"building/{self.location}"

        while self._running:
            try:
                if random.random() < anomaly_probability:
                    values = self.inject_anomaly()
                    self.logger.warning(f"Anomalie injectée : {values}")
                else:
                    values = self.read_sensors()

                self.publish(base_topic, values)

            except Exception as e:
                self.logger.error(f"Erreur dans la boucle : {e}")

            time.sleep(self.publish_interval)

    def start(self, anomaly_probability: float = 0.05):
        """Démarre la connexion MQTT et la boucle de publication dans un thread."""
        self.client.connect(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            args=(anomaly_probability,),
            daemon=True,
            name=self.sensor_id,
        )
        self._thread.start()
        self.logger.info(f"Capteur démarré — intervalle : {self.publish_interval}s")

    def stop(self):
        """Arrête proprement le capteur."""
        self._running = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
        self.logger.info("Capteur arrêté.")
