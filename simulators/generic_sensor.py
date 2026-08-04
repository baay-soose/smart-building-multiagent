import random
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from simulators.base_sensor import BaseSensor

# Types de capteurs disponibles avec leurs paramètres
SENSOR_TYPES = {
    "temperature": {
        "init":   lambda: random.uniform(19.0, 23.0),
        "drift":  lambda v: max(10.0, min(50.0, v + random.gauss(0, 0.3))),
        "unit":   "°C",
        "anomaly": lambda: round(random.uniform(30.0, 45.0), 2),
        "threshold": {"min": 16.0, "max": 28.0},
    },
    "humidity": {
        "init":   lambda: random.uniform(40.0, 55.0),
        "drift":  lambda v: max(10.0, min(90.0, v + random.gauss(0, 0.5))),
        "unit":   "%",
        "anomaly": lambda: round(random.uniform(75.0, 90.0), 2),
        "threshold": {"min": 25.0, "max": 65.0},
    },
    "co2_ppm": {
        "init":   lambda: random.uniform(450, 700),
        "drift":  lambda v: max(350, min(5000, v + random.gauss(0, 10))),
        "unit":   "ppm",
        "anomaly": lambda: int(random.uniform(1200, 2500)),
        "threshold": {"min": 350, "max": 1000},
    },
    "luminosity": {
        "init":   lambda: random.uniform(300, 600),
        "drift":  lambda v: max(0, min(1200, v + random.gauss(0, 15))),
        "unit":   "lux",
        "anomaly": lambda: 0,
        "threshold": {"min": 100, "max": 900},
    },
    "motion": {
        "init":   lambda: 0,
        "drift":  lambda v: 1 if random.random() < 0.3 else 0,
        "unit":   "",
        "anomaly": lambda: 1,
        "threshold": {"values": [0, 1]},
    },
    "smoke": {
        "init":   lambda: 0,
        "drift":  lambda v: 1 if random.random() < 0.01 else 0,
        "unit":   "",
        "anomaly": lambda: 1,
        "threshold": {"critical_if": 1},
    },
    "cpu_load_pct": {
        "init":   lambda: random.uniform(30.0, 60.0),
        "drift":  lambda v: max(0.0, min(100.0, v + random.gauss(0, 2.0))),
        "unit":   "%",
        "anomaly": lambda: round(random.uniform(90.0, 100.0), 1),
        "threshold": {"min": 0, "max": 90},
    },
    "power_w": {
        "init":   lambda: random.uniform(400, 900),
        "drift":  lambda v: max(100, min(3000, v + random.gauss(0, 20))),
        "unit":   "W",
        "anomaly": lambda: int(random.uniform(2100, 3000)),
        "threshold": {"min": 0, "max": 2000},
    },
}


class GenericSensor(BaseSensor):
    """
    Capteur générique créé dynamiquement depuis le dashboard.
    Supporte n'importe quelle combinaison de types de capteurs.
    """

    def __init__(
        self,
        zone_id: str,
        zone_label: str,
        sensor_types: list,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        publish_interval: int = 5,
    ):
        super().__init__(
            sensor_id=f"esp32-{zone_id}",
            location=zone_id,
            broker_host=broker_host,
            broker_port=broker_port,
            publish_interval=publish_interval,
        )
        self.zone_label   = zone_label
        self.sensor_types = [s for s in sensor_types if s in SENSOR_TYPES]

        # Initialiser les valeurs internes
        self._values = {
            stype: SENSOR_TYPES[stype]["init"]()
            for stype in self.sensor_types
        }

    def read_sensors(self) -> dict:
        result = {}
        for stype in self.sensor_types:
            cfg = SENSOR_TYPES[stype]
            self._values[stype] = cfg["drift"](self._values[stype])
            v = self._values[stype]
            # Arrondir selon le type
            if stype in ("motion", "smoke", "co2_ppm", "power_w"):
                result[stype] = int(v)
            else:
                result[stype] = round(v, 2)
        return result

    def inject_anomaly(self) -> dict:
        values = self.read_sensors()
        # Choisir un capteur aléatoire pour l'anomalie
        anom_type = random.choice(self.sensor_types)
        cfg = SENSOR_TYPES[anom_type]
        values[anom_type] = cfg["anomaly"]()
        values["anomaly"] = f"{anom_type}_spike"
        return values
