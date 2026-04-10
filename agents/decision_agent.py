import json
import logging
import requests
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

# ------------------------------------------------------------------
# URL du webhook n8n (à remplacer une fois n8n configuré)
# ------------------------------------------------------------------
N8N_WEBHOOKS = {
    "alert":      "http://localhost:5678/webhook/alert",
    "hvac":       "http://localhost:5678/webhook/hvac",
    "fire":       "http://localhost:5678/webhook/fire",
    "power":      "http://localhost:5678/webhook/power",
}

# ------------------------------------------------------------------
# Règles de décision
# Risque + urgence → action(s) à déclencher
# ------------------------------------------------------------------
DECISION_RULES = [
    {
        "condition": lambda d, loc: d.get("risque") == "critical" and loc == "floor3",
        "actions":   ["fire", "alert"],
        "label":     "Alerte incendie",
    },
    {
        "condition": lambda d, loc: d.get("risque") == "critical" and loc == "server_room",
        "actions":   ["power", "alert"],
        "label":     "Coupure alimentation serveur",
    },
    {
        "condition": lambda d, loc: d.get("risque") in ("critical", "high") and d.get("urgence"),
        "actions":   ["hvac", "alert"],
        "label":     "Activation HVAC + alerte",
    },
    {
        "condition": lambda d, loc: d.get("risque") == "medium",
        "actions":   ["alert"],
        "label":     "Alerte standard",
    },
]


class DecisionAgent:
    """
    Agent de décision — reçoit le diagnostic de l'AnalysisAgent,
    applique les règles de décision et déclenche les actions
    via les webhooks n8n.
    """

    def __init__(self, n8n_webhooks: dict = N8N_WEBHOOKS, dry_run: bool = False):
        self.webhooks = n8n_webhooks
        self.dry_run  = dry_run   # Si True, simule sans appeler n8n
        self.logger   = logging.getLogger("DecisionAgent")

    # ------------------------------------------------------------------
    # Point d'entrée — appelé par AnalysisAgent
    # ------------------------------------------------------------------

    def decide(self, result: dict):
        anomaly_event = result.get("anomaly_event", {})
        diagnostic    = result.get("diagnostic", {})
        location      = anomaly_event.get("location", "unknown")

        # Normaliser le risque en minuscules (Mistral peut retourner "Medium", "High"...)
        if "risque" in diagnostic:
            diagnostic["risque"] = diagnostic["risque"].lower()

        self.logger.info(
            f"Décision en cours — {location} | "
            f"risque : {diagnostic.get('risque')} | "
            f"urgence : {diagnostic.get('urgence')}"
        )

        actions = self._select_actions(diagnostic, location)

        if not actions:
            self.logger.info("Aucune action requise.")
            return

        for action in actions:
            self._trigger_action(action, anomaly_event, diagnostic)

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
    # Déclenchement d'une action via n8n webhook
    # ------------------------------------------------------------------

    def _trigger_action(self, action: str, event: dict, diagnostic: dict):
        webhook_url = self.webhooks.get(action)
        if not webhook_url:
            self.logger.error(f"Webhook inconnu : {action}")
            return

        payload = {
            "action":     action,
            "location":   event.get("location"),
            "sensor_id":  event.get("sensor_id"),
            "timestamp":  event.get("timestamp"),
            "values":     event.get("values"),
            "diagnostic": diagnostic.get("diagnostic"),
            "risque":     diagnostic.get("risque"),
            "urgence":    diagnostic.get("urgence"),
            "action_recommandee": diagnostic.get("action_recommandee"),
        }

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Action '{action}' → {webhook_url}")
            self.logger.info(f"[DRY RUN] Payload : {json.dumps(payload, ensure_ascii=False, indent=2)}")
            return

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200:
                self.logger.info(f"Action '{action}' déclenchée avec succès.")
            else:
                self.logger.warning(f"Action '{action}' — réponse inattendue : {response.status_code}")
        except requests.exceptions.ConnectionError:
            self.logger.warning(
                f"n8n non disponible pour l'action '{action}' — "
                "le webhook sera déclenché une fois n8n configuré."
            )
        except Exception as e:
            self.logger.error(f"Erreur déclenchement action '{action}' : {e}")


# ------------------------------------------------------------------
# Test standalone
# ------------------------------------------------------------------

if __name__ == "__main__":
    agent = DecisionAgent(dry_run=True)

    # Scénario 1 — surchauffe critique salle serveur
    print("=== Scénario 1 : surchauffe salle serveur ===")
    agent.decide({
        "anomaly_event": {
            "location":  "server_room",
            "sensor_id": "esp32-server-room",
            "timestamp": "2026-04-09T18:00:00",
            "values":    {"temperature": 42.5, "cpu_load_pct": 95.0},
        },
        "diagnostic": {
            "diagnostic":          "Surchauffe critique de la salle serveur",
            "cause_probable":      "Défaillance du système de refroidissement",
            "risque":              "critical",
            "action_recommandee":  "Couper les serveurs non essentiels",
            "urgence":             True,
        },
    })

    print()

    # Scénario 2 — détection fumée floor3
    print("=== Scénario 2 : fumée détectée étage 3 ===")
    agent.decide({
        "anomaly_event": {
            "location":  "floor3",
            "sensor_id": "esp32-floor3",
            "timestamp": "2026-04-09T18:05:00",
            "values":    {"temperature": 55.0, "smoke": 1},
        },
        "diagnostic": {
            "diagnostic":         "Incendie probable détecté à l'étage 3",
            "cause_probable":     "Source de chaleur ou feu déclaré",
            "risque":             "critical",
            "action_recommandee": "Déclencher alarme incendie et évacuation",
            "urgence":            True,
        },
    })

    print()

    # Scénario 3 — alerte medium
    print("=== Scénario 3 : CO2 élevé étage 1 ===")
    agent.decide({
        "anomaly_event": {
            "location":  "floor1",
            "sensor_id": "esp32-floor1",
            "timestamp": "2026-04-09T18:10:00",
            "values":    {"co2_ppm": 1400},
        },
        "diagnostic": {
            "diagnostic":         "Taux de CO2 élevé dans les bureaux",
            "cause_probable":     "Ventilation insuffisante",
            "risque":             "medium",
            "action_recommandee": "Augmenter la ventilation",
            "urgence":            False,
        },
    })
