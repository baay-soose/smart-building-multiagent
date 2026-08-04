import json
import logging
import requests
from typing import Callable, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral:7b-instruct-q4_0"

PROMPT_TEMPLATE = """[INST] Tu es un expert en gestion de bâtiment intelligent. IMPORTANT : tu dois répondre UNIQUEMENT en français. Ne réponds jamais en anglais.

Voici une anomalie détectée par un capteur IoT :
Zone : {location}
Capteur : {sensor_id}
Valeurs mesurées : {values}
Anomalies détectées : {anomalies}

Réponds avec UNIQUEMENT ce JSON en français, rien d'autre :
{{
  "diagnostic": "une phrase en français décrivant la situation",
  "cause_probable": "la cause la plus probable en français",
  "risque": "low",
  "action_recommandee": "action concrète à effectuer en français",
  "urgence": false
}}

RÈGLES STRICTES :
- Toutes les valeurs textuelles doivent être en français
- risque doit être exactement l'un de : low, medium, high, critical
- urgence doit être exactement true ou false
- Aucun texte en dehors du JSON [/INST]"""


class AnalysisAgent:
    def __init__(
        self,
        ollama_url: str = OLLAMA_URL,
        model: str = OLLAMA_MODEL,
        on_decision: Optional[Callable] = None,
    ):
        self.ollama_url  = ollama_url
        self.model       = model
        self.on_decision = on_decision
        self.logger      = logging.getLogger("AnalysisAgent")

    def analyze(self, anomaly_event: dict):
        location  = anomaly_event.get("location", "unknown")
        sensor_id = anomaly_event.get("sensor_id", "unknown")
        values    = anomaly_event.get("values", {})
        anomalies = anomaly_event.get("anomalies", [])

        self.logger.info(f"Analyse en cours — {location} | {len(anomalies)} anomalie(s)")

        prompt = PROMPT_TEMPLATE.format(
            location=location,
            sensor_id=sensor_id,
            values=json.dumps(values, ensure_ascii=False),
            anomalies=", ".join(a["reason"] for a in anomalies),
        )

        try:
            raw_response = self._call_ollama(prompt)
            diagnostic   = self._parse_response(raw_response)

            # Injecter les flags directs depuis les valeurs capteurs
            values = anomaly_event.get("values", {})
            diagnostic["_smoke_detected"] = values.get("smoke", 0) == 1

            if diagnostic:
                result = {"anomaly_event": anomaly_event, "diagnostic": diagnostic}
                self.logger.info(
                    f"Diagnostic : {diagnostic.get('diagnostic', '?')} "
                    f"| risque : {diagnostic.get('risque', '?')} "
                    f"| urgence : {diagnostic.get('urgence', False)}"
                )
                if self.on_decision:
                    self.on_decision(result)
            else:
                self.logger.error("Impossible de parser la réponse du LLM.")

        except Exception as e:
            self.logger.error(f"Erreur lors de l'analyse : {e}")

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "system": "Tu es un expert en gestion de bâtiment intelligent. Tu réponds TOUJOURS en français, jamais en anglais.",
        }
        response = requests.post(self.ollama_url, json=payload, timeout=150)
        response.raise_for_status()
        return response.json().get("response", "")

    def _parse_response(self, raw: str) -> Optional[dict]:
        try:
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start == -1 or end == 0:
                raise ValueError("Aucun JSON trouvé")
            return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Erreur parsing JSON : {e}\nRéponse : {raw[:200]}")
            return None


if __name__ == "__main__":
    def print_decision(result):
        print("\n--- RÉSULTAT ANALYSE ---")
        d = result["diagnostic"]
        print(f"  Diagnostic        : {d.get('diagnostic')}")
        print(f"  Cause probable    : {d.get('cause_probable')}")
        print(f"  Risque            : {d.get('risque')}")
        print(f"  Action recommandée: {d.get('action_recommandee')}")
        print(f"  Urgence           : {d.get('urgence')}")
        print("------------------------\n")

    agent = AnalysisAgent(on_decision=print_decision)

    test_event = {
        "sensor_id": "esp32-server-room",
        "location":  "server_room",
        "timestamp": "2026-04-10T11:00:00",
        "values":    {"temperature": 42.5, "cpu_load_pct": 95.0, "power_w": 2400},
        "anomalies": [
            {"metric": "temperature",  "value": 42.5, "reason": "temperature trop élevé (42.5 > 30.0)", "severity": "critical"},
            {"metric": "cpu_load_pct", "value": 95.0, "reason": "cpu_load_pct trop élevé (95.0 > 90)",  "severity": "high"},
        ],
    }

    print("Envoi de l'événement test à Ollama...\n")
    agent.analyze(test_event)
