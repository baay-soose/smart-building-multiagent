import json
import logging
import requests
from typing import Callable, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"

# ------------------------------------------------------------------
# Templates de prompts par zone
# ------------------------------------------------------------------
PROMPT_TEMPLATES = {
    "default": """Tu es un système expert en gestion de bâtiment intelligent (smart building).
Tu reçois des données d'un capteur IoT qui a détecté une anomalie.

Informations :
- Zone      : {location}
- Capteur   : {sensor_id}
- Timestamp : {timestamp}
- Valeurs   : {values}
- Anomalies : {anomalies}

Fournis un diagnostic structuré en JSON avec exactement ces champs :
{{
  "diagnostic": "explication courte de la situation",
  "cause_probable": "cause la plus probable",
  "risque": "low | medium | high | critical",
  "action_recommandee": "action concrète à effectuer",
  "urgence": true | false
}}

Réponds UNIQUEMENT avec le JSON, sans texte supplémentaire.""",

    "server_room": """Tu es un système expert en infrastructure informatique et datacenter.
Tu reçois des données critiques de la salle serveur.

Informations :
- Zone      : {location}
- Capteur   : {sensor_id}
- Timestamp : {timestamp}
- Valeurs   : {values}
- Anomalies : {anomalies}

Fournis un diagnostic structuré en JSON avec exactement ces champs :
{{
  "diagnostic": "explication courte de la situation",
  "cause_probable": "cause la plus probable",
  "risque": "low | medium | high | critical",
  "action_recommandee": "action concrète à effectuer",
  "urgence": true | false
}}

Réponds UNIQUEMENT avec le JSON, sans texte supplémentaire.""",

    "floor3": """Tu es un système expert en sécurité incendie et gestion de bâtiment.
Une anomalie a été détectée à l'étage 3. La fumée est un signal critique.

Informations :
- Zone      : {location}
- Capteur   : {sensor_id}
- Timestamp : {timestamp}
- Valeurs   : {values}
- Anomalies : {anomalies}

Fournis un diagnostic structuré en JSON avec exactement ces champs :
{{
  "diagnostic": "explication courte de la situation",
  "cause_probable": "cause la plus probable",
  "risque": "low | medium | high | critical",
  "action_recommandee": "action concrète à effectuer",
  "urgence": true | false
}}

Réponds UNIQUEMENT avec le JSON, sans texte supplémentaire.""",
}


class AnalysisAgent:
    """
    Agent d'analyse — reçoit un event d'anomalie du MonitorAgent,
    construit un prompt contextuel et appelle Ollama/Mistral
    pour générer un diagnostic structuré.

    Transmet le résultat au DecisionAgent via callback on_decision.
    """

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

    # ------------------------------------------------------------------
    # Point d'entrée — appelé par MonitorAgent
    # ------------------------------------------------------------------

    def analyze(self, anomaly_event: dict):
        location  = anomaly_event.get("location", "unknown")
        sensor_id = anomaly_event.get("sensor_id", "unknown")
        timestamp = anomaly_event.get("timestamp", "")
        values    = anomaly_event.get("values", {})
        anomalies = anomaly_event.get("anomalies", [])

        self.logger.info(f"Analyse en cours — {location} | {len(anomalies)} anomalie(s)")

        prompt = self._build_prompt(location, sensor_id, timestamp, values, anomalies)

        try:
            raw_response = self._call_ollama(prompt)
            diagnostic   = self._parse_response(raw_response)

            if diagnostic:
                result = {
                    "anomaly_event": anomaly_event,
                    "diagnostic":    diagnostic,
                }
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

    # ------------------------------------------------------------------
    # Construction du prompt
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        location: str,
        sensor_id: str,
        timestamp: str,
        values: dict,
        anomalies: list,
    ) -> str:
        template = PROMPT_TEMPLATES.get(location, PROMPT_TEMPLATES["default"])

        anomalies_str = "\n".join(
            f"  - [{a['severity'].upper()}] {a['reason']}" for a in anomalies
        )
        values_str = json.dumps(values, ensure_ascii=False)

        return template.format(
            location=location,
            sensor_id=sensor_id,
            timestamp=timestamp,
            values=values_str,
            anomalies=anomalies_str,
        )

    # ------------------------------------------------------------------
    # Appel Ollama
    # ------------------------------------------------------------------

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
        }
        response = requests.post(self.ollama_url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json().get("response", "")

    # ------------------------------------------------------------------
    # Parsing de la réponse JSON
    # ------------------------------------------------------------------

    def _parse_response(self, raw: str) -> Optional[dict]:
        try:
            # Nettoyer les backticks markdown si présents
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            return json.loads(cleaned.strip())
        except json.JSONDecodeError as e:
            self.logger.error(f"Erreur parsing JSON LLM : {e}\nRéponse brute : {raw}")
            return None


# ------------------------------------------------------------------
# Test standalone
# ------------------------------------------------------------------

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

    # Événement de test simulé
    test_event = {
        "sensor_id": "esp32-server-room",
        "location":  "server_room",
        "timestamp": "2026-04-09T18:00:00",
        "values":    {"temperature": 42.5, "cpu_load_pct": 95.0, "power_w": 2400},
        "anomalies": [
            {"metric": "temperature",  "value": 42.5, "reason": "temperature trop élevé (42.5 > 27.0)", "severity": "critical"},
            {"metric": "cpu_load_pct", "value": 95.0, "reason": "cpu_load_pct trop élevé (95.0 > 85)",  "severity": "high"},
        ],
    }

    print("Envoi de l'événement test à Ollama...\n")
    agent.analyze(test_event)
