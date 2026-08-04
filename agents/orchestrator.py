import argparse
import logging
import queue
import threading
import time
from typing import Optional

from agents.monitor_agent  import MonitorAgent
from agents.analysis_agent import AnalysisAgent
from agents.decision_agent import DecisionAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


class Orchestrator:
    """
    Coordonne les 3 agents : MonitorAgent → AnalysisAgent (via PicoClaw) → DecisionAgent
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        picoclaw_container: str = "picoclaw",
        dry_run: bool = False,
    ):
        self.logger = logging.getLogger("Orchestrator")

        # Instanciation des agents dans l'ordre inverse pour le chainage des callbacks
        self.decision_agent = DecisionAgent(dry_run=dry_run)

        self.analysis_agent = AnalysisAgent(
            container_name=picoclaw_container,
            on_decision=self.decision_agent.decide,
        )

        self.monitor_agent = MonitorAgent(
            broker_host=broker_host,
            broker_port=broker_port,
            on_anomaly=self._on_anomaly_received,
        )

        # File d'attente entre MonitorAgent et AnalysisAgent
        # (PicoClaw ne peut traiter qu'une requête à la fois)
        self._queue = queue.Queue(maxsize=10)
        self._worker_thread = None
        self._running = False

    # ------------------------------------------------------------------
    # Callback appelé par le MonitorAgent
    # ------------------------------------------------------------------

    def _on_anomaly_received(self, event: dict):
        """Filtre les anomalies medium et met en file les critical/high."""
        anomalies = event.get("anomalies", [])
        if not anomalies:
            return

        severities = [a.get("severity", "medium") for a in anomalies]

        if "critical" not in severities and "high" not in severities:
            self.logger.debug(f"Anomalie medium ignorée : {event.get('location')}")
            return

        try:
            self._queue.put_nowait(event)
            self.logger.info(
                f"Anomalie ajoutée en file (taille={self._queue.qsize()}) — "
                f"{event.get('location')}"
            )
        except queue.Full:
            self.logger.warning("File pleine — anomalie ignorée.")

    # ------------------------------------------------------------------
    # Worker thread — consomme la file séquentiellement
    # ------------------------------------------------------------------

    def _analysis_worker(self):
        while self._running:
            try:
                event = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                self.analysis_agent.analyze(event)
            except Exception as e:
                self.logger.error(f"Erreur lors de l'analyse : {e}")

            self._queue.task_done()

    # ------------------------------------------------------------------
    # Démarrage / arrêt
    # ------------------------------------------------------------------

    def start(self):
        self.logger.info("Démarrage de l'orchestrateur...")
        self._running = True

        self._worker_thread = threading.Thread(target=self._analysis_worker, daemon=True)
        self._worker_thread.start()

        self.monitor_agent.start()
        self.logger.info("Orchestrateur prêt. En attente d'anomalies...")

    def stop(self):
        self.logger.info("Arrêt de l'orchestrateur...")
        self._running = False
        self.monitor_agent.stop()
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)


# ------------------------------------------------------------------
# Point d'entrée CLI
# ------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orchestrator smart building multi-agents")
    parser.add_argument("--broker", default="localhost", help="Adresse du broker MQTT")
    parser.add_argument("--port", type=int, default=1883, help="Port MQTT")
    parser.add_argument("--picoclaw", default="picoclaw", help="Nom du conteneur PicoClaw")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas appeler n8n")
    args = parser.parse_args()

    orchestrator = Orchestrator(
        broker_host=args.broker,
        broker_port=args.port,
        picoclaw_container=args.picoclaw,
        dry_run=args.dry_run,
    )

    try:
        orchestrator.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        orchestrator.stop()
