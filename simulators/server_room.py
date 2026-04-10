import random
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simulators.base_sensor import BaseSensor


THRESHOLDS = {
    "temperature":  {"min": 18.0, "max": 27.0},
    "cpu_load_pct": {"min": 0,    "max": 85},
    "power_w":      {"min": 200,  "max": 1500},
}


class ServerRoomSensor(BaseSensor):
    """
    Capteur ESP32 simulé — Salle serveur.
    Publie : température, charge CPU, consommation électrique.
    Topic  : building/server_room
    C'est la zone la plus critique — seuils plus stricts.
    """

    def __init__(self, broker_host: str = "localhost", broker_port: int = 1883, publish_interval: int = 5):
        super().__init__(
            sensor_id="esp32-server-room",
            location="server_room",
            broker_host=broker_host,
            broker_port=broker_port,
            publish_interval=publish_interval,
        )
        self._temp     = random.uniform(20.0, 24.0)
        self._cpu_load = random.uniform(30.0, 60.0)
        self._power    = random.uniform(400, 900)

    def read_sensors(self) -> dict:
        self._temp     += random.gauss(0, 0.2)
        self._cpu_load += random.gauss(0, 2.0)
        self._power    += random.gauss(0, 20)

        self._temp     = max(15.0, min(60.0, self._temp))
        self._cpu_load = max(0.0,  min(100.0, self._cpu_load))
        self._power    = max(100,  min(3000, self._power))

        return {
            "temperature":  round(self._temp, 2),
            "cpu_load_pct": round(self._cpu_load, 1),
            "power_w":      int(self._power),
        }

    def inject_anomaly(self) -> dict:
        anomaly_type = random.choice(["overheat", "cpu_spike", "power_surge"])
        values = self.read_sensors()

        if anomaly_type == "overheat":
            # Surchauffe critique — danger pour le matériel
            values["temperature"] = round(random.uniform(35.0, 55.0), 2)

        elif anomaly_type == "cpu_spike":
            values["cpu_load_pct"] = round(random.uniform(90.0, 100.0), 1)
            values["power_w"]      = int(random.uniform(1600, 2500))

        elif anomaly_type == "power_surge":
            # Pic de consommation électrique
            values["power_w"] = int(random.uniform(2000, 3000))

        values["anomaly"] = anomaly_type
        return values


if __name__ == "__main__":
    import time

    sensor = ServerRoomSensor(publish_interval=3)
    sensor.start(anomaly_probability=0.15)
    print("Capteur server_room démarré. Ctrl+C pour arrêter.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sensor.stop()
