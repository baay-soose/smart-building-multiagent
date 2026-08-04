import json
import logging
import requests
from datetime import datetime, timezone
from typing import Optional
import paho.mqtt.client as mqtt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

N8N_WEBHOOKS = {
    "alert": "http://localhost:5678/webhook/alert",
    "hvac":  "http://localhost:5678/webhook/hvac",
    "fire":  "http://localhost:5678/webhook/fire",
    "power": "http://localhost:5678/webhook/power",
}

DECISION_RULES = [
    {
        "condition": lambda d, loc: loc == "floor3" and d.get("_smoke_detected"),
        "actions":   ["fire"],
        "label":     "Incendie — fumée détectée (direct)",
    },
    {
        "condition": lambda d, loc: loc == "floor3" and d.get("risque") in ("critical", "high") and d.get("urgence"),
        "actions":   ["fire"],
        "label":     "Alerte incendie",
    },
    {
        "condition": lambda d, loc: loc == "server_room" and d.get("risque") in ("critical", "high") and d.get("urgence"),
        "actions":   ["power", "hvac"],
        "label":     "Coupure alimentation serveur",
    },
    {
        "condition": lambda d, loc: d.get("risque") in ("critical", "high") and d.get("urgence"),
        "actions":   ["hvac"],
        "label":     "Activation HVAC",
    },
    {
        "condition": lambda d, loc: d.get("risque") == "medium",
        "actions":   ["alert"],
        "label":     "Alerte standard",
    },
]

class DecisionAgent:

    def __init__(self, n8n_webhooks: dict = N8N_WEBHOOKS, dry_run: bool = False):
        self.webhooks = n8n_webhooks
        self.dry_run  = dry_run
        self.logger   = logging.getLogger("DecisionAgent")
        self._mqtt    = None
        self._init_mqtt()

    # ------------------------------------------------------------------
    # MQTT — publication vers le dashboard
    # ------------------------------------------------------------------

    def _init_mqtt(self):
        try:
            client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="decision-agent-publisher"
            )
            client.connect("localhost", 1883, keepalive=60)
            client.loop_start()
            self._mqtt = client
        except Exception as e:
            self.logger.warning(f"Dashboard MQTT non disponible : {e}")

    def _publish_decision(self, location: str, diagnostic: dict, actions: list, event: dict):
        if not self._mqtt:
            self.logger.warning("MQTT dashboard non connecté — décision non publiée")
            return
        try:
            payload = json.dumps({
                "location":           location,
                "diagnostic":         diagnostic.get("diagnostic", ""),
                "risque":             diagnostic.get("risque", ""),
                "urgence":            diagnostic.get("urgence", False),
                "action_recommandee": diagnostic.get("action_recommandee", ""),
                "actions_declenchees": actions,
                "timestamp":          datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False)
            result = self._mqtt.publish(f"decisions/{location}", payload, qos=1)
            self.logger.info(f"Décision publiée sur decisions/{location} (rc={result.rc})")
        except Exception as e:
            self.logger.warning(f"Erreur publication dashboard : {e}")

    # ------------------------------------------------------------------
    # Point d'entrée — appelé par AnalysisAgent
    # ------------------------------------------------------------------

    def decide(self, result: dict):
        anomaly_event = result.get("anomaly_event", {})
        diagnostic    = result.get("diagnostic", {})
        location      = anomaly_event.get("location", "unknown")

        # Normaliser le risque
        if "risque" in diagnostic:
            risque = diagnostic["risque"].lower()
            risque = risque.replace("critique", "critical")
            risque = risque.replace("élevé", "high")
            risque = risque.replace("eleve", "high")
            risque = risque.replace("moyen", "medium")
            risque = risque.replace("faible", "low")
            diagnostic["risque"] = risque

        # Forcer le risque selon les valeurs capteurs — indépendamment d'Ollama
        values = anomaly_event.get("values", {})
        if values.get("smoke") == 1:
            diagnostic["risque"] = "critical"
            diagnostic["urgence"] = True
        elif location == "server_room" and values.get("temperature", 0) > 35:
            if diagnostic.get("risque") not in ("critical", "high"):
                diagnostic["risque"] = "critical"
                diagnostic["urgence"] = True

        self.logger.info(
            f"Décision en cours — {location} | "
            f"risque : {diagnostic.get('risque')} | "
            f"urgence : {diagnostic.get('urgence')}"
        )

        actions = self._select_actions(diagnostic, location)

        if not actions:
            self.logger.info("Aucune action requise.")
            # Publier quand même pour que le dashboard voie les décisions "sans action"
            self._publish_decision(location, diagnostic, [], anomaly_event)
            return

        for action in actions:
            self._trigger_action(action, anomaly_event, diagnostic)

        # Publier la décision complète vers le dashboard
        self._publish_decision(location, diagnostic, actions, anomaly_event)

    # ------------------------------------------------------------------
    # Sélection des actions
    # ------------------------------------------------------------------

    def _select_actions(self, diagnostic: dict, location: str) -> list:
        for rule in DECISION_RULES:
            try:
                if rule["condition"](diagnostic, location):
                    self.logger.info(f"Règle déclenchée : {rule['label']}")
                    return rule["actions"]
            except Exception:
                continue
        return []

    # ------------------------------------------------------------------
    # Déclenchement via n8n webhook
    # ------------------------------------------------------------------

    def _trigger_action(self, action: str, event: dict, diagnostic: dict):
        webhook_url = self.webhooks.get(action)
        if not webhook_url:
            self.logger.error(f"Webhook inconnu : {action}")
            return

        payload = {
            "action":             action,
            "location":           event.get("location"),
            "sensor_id":          event.get("sensor_id"),
            "timestamp":          event.get("timestamp"),
            "values":             event.get("values"),
            "diagnostic":         diagnostic.get("diagnostic"),
            "risque":             diagnostic.get("risque"),
            "urgence":            diagnostic.get("urgence"),
            "action_recommandee": diagnostic.get("action_recommandee"),
        }

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Action '{action}' → {webhook_url}")
            return

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                self.logger.info(f"Action '{action}' déclenchée avec succès.")
            else:
                self.logger.warning(f"Action '{action}' — réponse inattendue : {response.status_code}")
        except requests.exceptions.ConnectionError:
            self.logger.warning(f"n8n non disponible pour l'action '{action}'.")
        except Exception as e:
            self.logger.error(f"Erreur déclenchement action '{action}' : {e}")


# ------------------------------------------------------------------
# Test standalone
# ------------------------------------------------------------------

if __name__ == "__main__":
    agent = DecisionAgent(dry_run=True)

    print("=== Scénario 1 : surchauffe salle serveur ===")
    agent.decide({
        "anomaly_event": {
            "location": "server_room", "sensor_id": "esp32-server-room",
            "timestamp": "2026-04-09T18:00:00",
            "values": {"temperature": 42.5, "cpu_load_pct": 95.0},
        },
        "diagnostic": {
            "diagnostic": "Surchauffe critique de la salle serveur",
            "cause_probable": "Défaillance du système de refroidissement",
            "risque": "critical", "action_recommandee": "Couper les serveurs non essentiels",
            "urgence": True,
        },
    })

    print("\n=== Scénario 2 : fumée étage 3 ===")
    agent.decide({
        "anomaly_event": {
            "location": "floor3", "sensor_id": "esp32-floor3",
            "timestamp": "2026-04-09T18:05:00",
            "values": {"temperature": 55.0, "smoke": 1},
        },
        "diagnostic": {
            "diagnostic": "Incendie probable à l'étage 3",
            "cause_probable": "Source de chaleur ou feu déclaré",
            "risque": "critical", "action_recommandee": "Évacuation immédiate",
            "urgence": True,
        },
    })

    print("\n=== Scénario 3 : CO2 élevé étage 1 ===")
    agent.decide({
        "anomaly_event": {
            "location": "floor1", "sensor_id": "esp32-floor1",
            "timestamp": "2026-04-09T18:10:00",
            "values": {"co2_ppm": 1400},
        },
        "diagnostic": {
            "diagnostic": "Taux de CO2 élevé dans les bureaux",
            "cause_probable": "Ventilation insuffisante",
            "risque": "medium", "action_recommandee": "Augmenter la ventilation",
            "urgence": False,
        },
    })
