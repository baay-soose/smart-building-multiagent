import random
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simulators.base_sensor import BaseSensor


THRESHOLDS = {
    "temperature": {"min": 18.0, "max": 26.0},
    "humidity":    {"min": 30.0, "max": 60.0},
    "smoke":       {"values": [0, 1]},
}


class Floor3Sensor(BaseSensor):
    """
    Capteur ESP32 simulé — Étage 3 (open space).
    Publie : température, humidité, détection fumée.
    Topic  : building/floor3
    """

    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883, publish_interval: int = 5):
        super().__init__(
            sensor_id="esp32-floor3",
            location="floor3",
            broker_host=broker_host,
            broker_port=broker_port,
            publish_interval=publish_interval,
        )
        self._temp = random.uniform(20.0, 23.0)
        self._humidity = random.uniform(40.0, 50.0)

    def read_sensors(self) -> dict:
        self._temp     += random.gauss(0, 0.3)
        self._humidity += random.gauss(0, 0.5)

        self._temp     = max(10.0, min(40.0, self._temp))
        self._humidity = max(10.0, min(90.0, self._humidity))

        # Fumée — très rare en conditions normales (1%)
        smoke = 1 if random.random() < 0.01 else 0

        return {
            "temperature": round(self._temp, 2),
            "humidity":    round(self._humidity, 2),
            "smoke":       smoke,
        }

    def inject_anomaly(self) -> dict:
        anomaly_type = random.choice(["fire", "overheating", "high_humidity"])
        values = self.read_sensors()

        if anomaly_type == "fire":
            # Fumée + température très élevée
            values["smoke"] = 1
            values["temperature"] = round(random.uniform(45.0, 70.0), 2)

        elif anomaly_type == "overheating":
            values["temperature"] = round(random.uniform(30.0, 38.0), 2)

        elif anomaly_type == "high_humidity":
            values["humidity"] = round(random.uniform(75.0, 90.0), 2)

        values["anomaly"] = anomaly_type
        return values


if __name__ == "__main__":
    import time

    sensor = Floor3Sensor(publish_interval=3)
    sensor.start(anomaly_probability=0.15)
    print("Capteur floor3 démarré. Ctrl+C pour arrêter.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sensor.stop()
