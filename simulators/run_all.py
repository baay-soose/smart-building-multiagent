"""
Lance tous les capteurs ESP32 simulés en parallèle.
Usage : python simulators/run_all.py
"""
import time
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulators.floor1      import Floor1Sensor
from simulators.floor2      import Floor2Sensor
from simulators.floor3      import Floor3Sensor
from simulators.server_room import ServerRoomSensor

BROKER_HOST        = "localhost"
BROKER_PORT        = 1883
PUBLISH_INTERVAL   = 5      # secondes
ANOMALY_PROB       = 0.05   # 10% de chance d'anomalie par publication

SENSORS = [
    Floor1Sensor(BROKER_HOST, BROKER_PORT, PUBLISH_INTERVAL),
    Floor2Sensor(BROKER_HOST, BROKER_PORT, PUBLISH_INTERVAL),
    Floor3Sensor(BROKER_HOST, BROKER_PORT, PUBLISH_INTERVAL),
    ServerRoomSensor(BROKER_HOST, BROKER_PORT, PUBLISH_INTERVAL),
]

if __name__ == "__main__":
    print(f"Démarrage de {len(SENSORS)} capteurs...\n")

    for sensor in SENSORS:
        sensor.start(anomaly_probability=ANOMALY_PROB)

    print("Tous les capteurs sont actifs. Ctrl+C pour tout arrêter.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nArrêt en cours...")
        for sensor in SENSORS:
            sensor.stop()
        print("Tous les capteurs arrêtés.")
