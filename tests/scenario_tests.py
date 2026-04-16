"""
Script de tests par scénarios — injecte des anomalies directement
sur le broker MQTT et vérifie la réaction de la plateforme.

Usage : python tests/scenario_tests.py
"""
import json
import time
import logging
from datetime import datetime
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ScenarioTest] %(message)s")
logger = logging.getLogger("ScenarioTest")

BROKER_HOST = "localhost"
BROKER_PORT  = 1883
WAIT_AFTER   = 30  # secondes d'attente après chaque injection (Ollama ~20s)

# ------------------------------------------------------------------
# Scénarios de test
# ------------------------------------------------------------------
SCENARIOS = [
    {
        "id":          1,
        "nom":         "Incendie étage 3",
        "description": "Fumée détectée + température critique sur floor3",
        "topic":       "building/floor3",
        "sensor_id":   "esp32-floor3",
        "location":    "floor3",
        "values": {
            "temperature": 62.5,
            "humidity":    45.0,
            "smoke":       1,
            "anomaly":     "fire",
        },
        "actions_attendues": ["fire", "alert"],
    },
    {
        "id":          2,
        "nom":         "Surchauffe salle serveur",
        "description": "Température critique + pic CPU dans server_room",
        "topic":       "building/server_room",
        "sensor_id":   "esp32-server-room",
        "location":    "server_room",
        "values": {
            "temperature":  48.0,
            "cpu_load_pct": 97.5,
            "power_w":      2800,
            "anomaly":      "overheat",
        },
        "actions_attendues": ["power", "hvac", "alert"],
    },
    {
        "id":          3,
        "nom":         "Mauvaise qualité d'air étage 1",
        "description": "Taux de CO2 très élevé sur floor1",
        "topic":       "building/floor1",
        "sensor_id":   "esp32-floor1",
        "location":    "floor1",
        "values": {
            "temperature": 22.0,
            "humidity":    48.0,
            "co2_ppm":     2200,
            "anomaly":     "poor_air",
        },
        "actions_attendues": ["alert"],
    },
    {
        "id":          4,
        "nom":         "Luminosité nulle avec présence détectée",
        "description": "Panne d'éclairage malgré mouvement détecté sur floor2",
        "topic":       "building/floor2",
        "sensor_id":   "esp32-floor2",
        "location":    "floor2",
        "values": {
            "temperature": 21.5,
            "motion":      1,
            "luminosity":  0,
            "anomaly":     "no_light",
        },
        "actions_attendues": ["alert"],
    },
]


def build_payload(scenario: dict) -> dict:
    return {
        "sensor_id": scenario["sensor_id"],
        "location":  scenario["location"],
        "timestamp": datetime.utcnow().isoformat(),
        "values":    scenario["values"],
    }


def run_scenario(client: mqtt.Client, scenario: dict):
    logger.info("=" * 55)
    logger.info(f"SCÉNARIO {scenario['id']} : {scenario['nom']}")
    logger.info(f"Description : {scenario['description']}")
    logger.info(f"Actions attendues : {scenario['actions_attendues']}")
    logger.info("-" * 55)

    payload = json.dumps(build_payload(scenario))
    result  = client.publish(scenario["topic"], payload, qos=1)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        logger.info(f"Anomalie injectée sur {scenario['topic']}")
        logger.info(f"Valeurs : {scenario['values']}")
    else:
        logger.error(f"Erreur publication MQTT : {result.rc}")
        return

    logger.info(f"Attente de {WAIT_AFTER}s pour la réponse de la plateforme...")
    time.sleep(WAIT_AFTER)
    logger.info(f"Scénario {scenario['id']} terminé — vérifie les logs de l'orchestrateur et n8n.\n")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info(f"Connecté au broker MQTT ({BROKER_HOST}:{BROKER_PORT})")
    else:
        logger.error(f"Erreur connexion MQTT : {rc}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tests par scénarios — Smart Building")
    parser.add_argument("--scenario", type=int, default=0,
                        help="Numéro du scénario à exécuter (0 = tous)")
    parser.add_argument("--wait", type=int, default=WAIT_AFTER,
                        help=f"Secondes d'attente entre scénarios (défaut: {WAIT_AFTER})")
    args = parser.parse_args()

    client = mqtt.Client(client_id="scenario-tester")
    client.on_connect = on_connect
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()
    time.sleep(1)

    scenarios_to_run = SCENARIOS if args.scenario == 0 else [
        s for s in SCENARIOS if s["id"] == args.scenario
    ]

    if not scenarios_to_run:
        logger.error(f"Scénario {args.scenario} introuvable.")
    else:
        logger.info(f"{len(scenarios_to_run)} scénario(s) à exécuter.\n")
        for scenario in scenarios_to_run:
            run_scenario(client, scenario)
            if len(scenarios_to_run) > 1:
                time.sleep(5)  # pause entre scénarios

    client.loop_stop()
    client.disconnect()
    logger.info("Tests terminés.")
