import random
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simulators.base_sensor import BaseSensor


THRESHOLDS = {
    "temperature": {"min": 18.0, "max": 26.0},
    "motion":      {"values": [0, 1]},
    "luminosity":  {"min": 200,  "max": 800},
}


class Floor2Sensor(BaseSensor):
    """
    Capteur ESP32 simulé — Étage 2 (salles de réunion).
    Publie : température, mouvement, luminosité.
    Topic  : building/floor2
    """

    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883, publish_interval: int = 5):
        super().__init__(
            sensor_id="esp32-floor2",
            location="floor2",
            broker_host=broker_host,
            broker_port=broker_port,
            publish_interval=publish_interval,
        )
        self._temp = random.uniform(20.0, 23.0)
        self._luminosity = random.uniform(300, 600)

    def read_sensors(self) -> dict:
        self._temp       += random.gauss(0, 0.3)
        self._luminosity += random.gauss(0, 15)

        self._temp       = max(10.0, min(40.0, self._temp))
        self._luminosity = max(0, min(1200, self._luminosity))

        # Mouvement aléatoire — 30% de chance de détection
        motion = 1 if random.random() < 0.3 else 0

        return {
            "temperature": round(self._temp, 2),
            "motion":      motion,
            "luminosity":  int(self._luminosity),
        }

    def inject_anomaly(self) -> dict:
        anomaly_type = random.choice(["overheating", "no_light", "motion_stuck"])
        values = self.read_sensors()

        if anomaly_type == "overheating":
            values["temperature"] = round(random.uniform(30.0, 38.0), 2)

        elif anomaly_type == "no_light":
            # Luminosité nulle malgré présence de mouvement
            values["luminosity"] = 0
            values["motion"] = 1

        elif anomaly_type == "motion_stuck":
            # Capteur de mouvement bloqué à 1 en permanence
            values["motion"] = 1

        values["anomaly"] = anomaly_type
        return values


if __name__ == "__main__":
    import time

    sensor = Floor2Sensor(publish_interval=3)
    sensor.start(anomaly_probability=0.15)
    print("Capteur floor2 démarré. Ctrl+C pour arrêter.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sensor.stop()
