import time
import logging
import threading
import queue

from agents.monitor_agent   import MonitorAgent
from agents.analysis_agent  import AnalysisAgent
from agents.decision_agent  import DecisionAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


class Orchestrator:
    """
    Orchestre les 3 agents en les branchant via callbacks :
    MonitorAgent -> AnalysisAgent -> DecisionAgent

    Les anomalies sont mises dans une file d'attente et
    traitées une par une par un worker dédié — Ollama ne
    peut traiter qu'une requête à la fois.
    """

    def __init__(
        self,
        broker_host:   str  = "localhost",
        broker_port:   int  = 1883,
        ollama_url:    str  = "http://localhost:11434/api/generate",
        dry_run:       bool = False,
        queue_maxsize: int  = 20,
    ):
        self.logger = logging.getLogger("Orchestrator")

        self.decision_agent = DecisionAgent(dry_run=dry_run)
        self.analysis_agent = AnalysisAgent(
            ollama_url=ollama_url,
            on_decision=self.decision_agent.decide,
        )
        self.monitor_agent  = MonitorAgent(
            broker_host=broker_host,
            broker_port=broker_port,
            on_anomaly=self._on_anomaly_received,
        )

        self._queue  = queue.Queue(maxsize=queue_maxsize)
        self._worker = threading.Thread(
            target=self._analysis_worker,
            daemon=True,
            name="analysis-worker",
        )

    def _on_anomaly_received(self, event: dict):
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.logger.warning(f"File pleine — événement ignoré ({event.get('location')})")

    def _analysis_worker(self):
        self.logger.info("Worker d'analyse démarré.")
        while True:
            event = self._queue.get()
            if event is None:
                break
            try:
                self.analysis_agent.analyze(event)
            except Exception as e:
                self.logger.error(f"Erreur worker : {e}")
            finally:
                self._queue.task_done()

    def start(self):
        self.logger.info("Démarrage de la plateforme multi-agents...")
        self._worker.start()
        self.monitor_agent.start()
        self.logger.info("Plateforme active — en attente de données capteurs.")

    def stop(self):
        self.logger.info("Arrêt en cours...")
        self.monitor_agent.stop()
        self._queue.put(None)
        self._worker.join(timeout=15)
        self.logger.info("Plateforme arrêtée.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Smart Building Multi-Agent Platform")
    parser.add_argument("--dry-run", action="store_true", help="Simule les actions n8n sans les déclencher")
    parser.add_argument("--broker",  default="localhost",                           help="Hôte MQTT (défaut: localhost)")
    parser.add_argument("--ollama",  default="http://localhost:11434/api/generate", help="URL Ollama")
    args = parser.parse_args()

    orchestrator = Orchestrator(
        broker_host=args.broker,
        ollama_url=args.ollama,
        dry_run=args.dry_run,
    )

    orchestrator.start()

    print("\n" + "="*55)
    print("  Plateforme smart building multi-agents démarrée")
    print("  Lance simulators/run_all.py dans un autre terminal")
    print("  Ctrl+C pour arrêter")
    print("="*55 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        orchestrator.stop()
