import json
import logging
import subprocess
import re
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


class AnalysisAgent:
    """
    Agent d'analyse — utilise PicoClaw (Claude Sonnet 4.6 via Anthropic)
    au lieu d'Ollama pour analyser les anomalies IoT.
    """

    def __init__(
        self,
        container_name: str = "picoclaw",
        on_decision=None,
        timeout: int = 60,
    ):
        self.container_name = container_name
        self.on_decision    = on_decision
        self.timeout        = timeout
        self.logger         = logging.getLogger("AnalysisAgent")

    # ------------------------------------------------------------------
    # Point d'entrée — appelé par l'Orchestrator
    # ------------------------------------------------------------------

    def analyze(self, anomaly_event: dict):
        location    = anomaly_event.get("location", "unknown")
        sensor_id   = anomaly_event.get("sensor_id", "unknown")
        values      = anomaly_event.get("values", {})
        anomalies   = anomaly_event.get("anomalies", [])

        self.logger.info(f"Analyse de l'anomalie sur {location} via PicoClaw...")

        prompt = self._build_prompt(location, sensor_id, values, anomalies)
        diagnostic = self._query_picoclaw(prompt)

        if not diagnostic:
            self.logger.warning("Aucun diagnostic obtenu de PicoClaw.")
            return

        result = {
            "anomaly_event": anomaly_event,
            "diagnostic":    diagnostic,
        }

        self.logger.info(
            f"Diagnostic généré : risque={diagnostic.get('risque')} | "
            f"urgence={diagnostic.get('urgence')}"
        )

        if self.on_decision:
            self.on_decision(result)

    # ------------------------------------------------------------------
    # Construction du prompt
    # ------------------------------------------------------------------

    def _build_prompt(self, location: str, sensor_id: str, values: dict, anomalies: list) -> str:
        vals_str = ", ".join(f"{k}={v}" for k, v in values.items() if k != "anomaly")
        anom_str = ", ".join(a.get("type", "") for a in anomalies) if anomalies else values.get("anomaly", "inconnue")

        prompt = f"""Tu es un expert en supervision de bâtiment intelligent (smart building).

Une anomalie a été détectée sur le capteur IoT '{sensor_id}' dans la zone '{location}'.

Type d'anomalie : {anom_str}
Valeurs mesurées : {vals_str}

Analyse cette situation et réponds UNIQUEMENT en JSON valide avec cette structure exacte :
{{
  "diagnostic": "description claire de la situation en français (2 phrases max)",
  "cause_probable": "cause la plus probable en français",
  "risque": "low|medium|high|critical",
  "action_recommandee": "action concrète à entreprendre en français",
  "urgence": true|false
}}

Réponds UNIQUEMENT avec le JSON, sans texte avant ni après, sans balise de code."""
        return prompt

    # ------------------------------------------------------------------
    # Appel à PicoClaw via docker exec
    # ------------------------------------------------------------------

    def _query_picoclaw(self, prompt: str) -> Optional[dict]:
        try:
            result = subprocess.run(
                [
                    "docker", "exec", self.container_name,
                    "picoclaw", "agent", "-m", prompt
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                self.logger.error(f"PicoClaw a retourné code {result.returncode}: {result.stderr[:200]}")
                return None

            output = result.stdout.strip()
            return self._parse_response(output)

        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout ({self.timeout}s) pour la requête PicoClaw.")
            return None
        except Exception as e:
            self.logger.error(f"Erreur appel PicoClaw : {e}")
            return None

    # ------------------------------------------------------------------
    # Parsing de la réponse JSON (nettoie l'ASCII art + texte parasite)
    # ------------------------------------------------------------------

    def _parse_response(self, output: str) -> Optional[dict]:
        # Retirer l'ASCII art PicoClaw et emojis
        # Chercher le premier { et le dernier } pour extraire le JSON
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", output, re.DOTALL)
        if not match:
            self.logger.warning(f"Aucun JSON trouvé dans la réponse : {output[:200]}")
            return None

        json_str = match.group(0)

        try:
            data = json.loads(json_str)
            return data
        except json.JSONDecodeError as e:
            self.logger.warning(f"JSON invalide : {e} | contenu : {json_str[:200]}")
            return None


# ------------------------------------------------------------------
# Test standalone
# ------------------------------------------------------------------

if __name__ == "__main__":
    def print_decision(result):
        print("=== DÉCISION REÇUE ===")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    agent = AnalysisAgent(on_decision=print_decision)

    test_event = {
        "location":  "server_room",
        "sensor_id": "esp32-server-room",
        "values":    {"temperature": 42.5, "cpu_load_pct": 95.0, "power_w": 2100},
        "anomalies": [
            {"type": "overheat", "severity": "critical"},
            {"type": "cpu_spike", "severity": "high"},
        ],
    }

    agent.analyze(test_event)
