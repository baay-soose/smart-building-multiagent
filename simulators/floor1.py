import random
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simulators.base_sensor import BaseSensor


# ------------------------------------------------------------------
# Seuils normaux pour l'étage 1
# ------------------------------------------------------------------
THRESHOLDS = {
    "temperature": {"min": 18.0, "max": 26.0},
    "humidity":    {"min": 30.0, "max": 60.0},
    "co2_ppm":     {"min": 400,  "max": 1000},
}


class Floor1Sensor(BaseSensor):
    """
    Capteur ESP32 simulé — Étage 1 (bureaux).
    Publie : température, humidité, CO₂.
    Topic  : building/floor1
    """

    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883, publish_interval: int = 5):
        super().__init__(
            sensor_id="esp32-floor1",
            location="floor1",
            broker_host=broker_host,
            broker_port=broker_port,
            publish_interval=publish_interval,
        )
        # État interne : dérive progressive pour simuler un comportement réaliste
        self._temp = random.uniform(20.0, 23.0)
        self._humidity = random.uniform(40.0, 50.0)
        self._co2 = random.uniform(500, 700)

    # ------------------------------------------------------------------
    # Lecture normale avec légère dérive
    # ------------------------------------------------------------------

    def read_sensors(self) -> dict:
        # Dérive gaussienne faible — simule un vrai capteur
        self._temp    += random.gauss(0, 0.3)
        self._humidity += random.gauss(0, 0.5)
        self._co2     += random.gauss(0, 10)

        # Clamp dans des limites physiques raisonnables
        self._temp     = max(10.0, min(40.0, self._temp))
        self._humidity = max(10.0, min(90.0, self._humidity))
        self._co2      = max(350, min(5000, self._co2))

        return {
            "temperature": round(self._temp, 2),
            "humidity":    round(self._humidity, 2),
            "co2_ppm":     int(self._co2),
        }

    # ------------------------------------------------------------------
    # Anomalie injectée
    # ------------------------------------------------------------------

    def inject_anomaly(self) -> dict:
        """
        Choisit aléatoirement un type d'anomalie :
        - surchauffe (température élevée)
        - mauvaise qualité d'air (CO₂ élevé)
        - humidité excessive
        """
        anomaly_type = random.choice(["overheating", "poor_air", "high_humidity"])

        values = self.read_sensors()  # base réaliste

        if anomaly_type == "overheating":
            values["temperature"] = round(random.uniform(30.0, 38.0), 2)

        elif anomaly_type == "poor_air":
            values["co2_ppm"] = int(random.uniform(1200, 2500))

        elif anomaly_type == "high_humidity":
            values["humidity"] = round(random.uniform(75.0, 90.0), 2)

        values["anomaly"] = anomaly_type
        return values


# ------------------------------------------------------------------
# Point d'entrée standalone (test direct)
# ------------------------------------------------------------------

if __name__ == "__main__":
    import time

    sensor = Floor1Sensor(publish_interval=3)
    sensor.start(anomaly_probability=0.15)  # 15% pour faciliter les tests

    print("Capteur floor1 démarré. Ctrl+C pour arrêter.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sensor.stop()
        print("Arrêté.")
