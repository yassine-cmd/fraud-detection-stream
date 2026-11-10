"""Simulateur de trafic PaySim et producteur Kafka.

Lit le fichier CSV de transactions et publie en continu les messages JSON
dans le topic Kafka 'transactions_stream' conformement au contrat
contracts/kafka_message.schema.json.
Expose un serveur HTTP de controle sur le port 8001 (start/stop/rate/fraud_ratio).
"""

import argparse
import csv
import json
import os
import random
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from confluent_kafka import Producer

NUMERIC_FIELDS = ["amount", "oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest"]
ALLOWED_TYPES = {"PAYMENT", "TRANSFER", "CASH_OUT", "DEBIT", "CASH_IN"}


def now_iso():
    """ISO 8601 UTC avec millisecondes et suffixe Z obligatoire."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class StreamSimulator:
    def __init__(
        self,
        data_file: str,
        bootstrap: str,
        topic: str,
        rate: float = 500.0,
        fraud_ratio: float = 0.0013,
        auto_start: bool = True,
    ):
        self.data_file = data_file
        self.bootstrap = bootstrap
        self.topic = topic
        self.rate = max(1.0, float(rate))
        self.fraud_ratio = min(1.0, max(0.0, float(fraud_ratio)))
        self.is_running = auto_start
        self.total_sent = 0
        self.total_delivered = 0
        self.errors_count = 0
        self.last_error = None
        self.lock = threading.Lock()

        self.rows_all = []
        self.rows_fraud = []
        self.rows_normal = []
        self.fraud_idx = 0
        self.normal_idx = 0
        self.load_dataset()

        # Initialisation Kafka Producer avec retries
        self.producer = Producer(
            {
                "bootstrap.servers": self.bootstrap,
                "linger.ms": 10,
                "acks": "all",
                "enable.idempotence": True,
                "retries": 5,
                "queue.buffering.max.messages": 100000,
            }
        )

    def load_dataset(self):
        """Charge le CSV PaySim en memoire et separe fraudes / transactions normales."""
        if not os.path.exists(self.data_file):
            print(f"[WARN] Fichier introuvable: {self.data_file}", flush=True)
            return

        with open(self.data_file, mode="r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                op_type = str(row.get("type", "")).strip().upper()
                if op_type not in ALLOWED_TYPES:
                    continue
                self.rows_all.append(row)
                if str(row.get("isFraud", "0")).strip() == "1":
                    self.rows_fraud.append(row)
                else:
                    self.rows_normal.append(row)

        print(
            f"[Simulator] Charge {len(self.rows_all)} transactions "
            f"({len(self.rows_fraud)} fraudes, {len(self.rows_normal)} normales) "
            f"depuis {self.data_file}",
            flush=True,
        )

    def _pick_row(self) -> dict:
        """Selectionne une ligne en respectant le ratio de fraudes demande."""
        with self.lock:
            fraud_ratio = self.fraud_ratio

        if fraud_ratio > 0.0 and self.rows_fraud and random.random() < fraud_ratio:
            row = self.rows_fraud[self.fraud_idx % len(self.rows_fraud)]
            self.fraud_idx += 1
            return row

        if self.rows_normal:
            row = self.rows_normal[self.normal_idx % len(self.rows_normal)]
            self.normal_idx += 1
            return row

        if self.rows_fraud:
            row = self.rows_fraud[self.fraud_idx % len(self.rows_fraud)]
            self.fraud_idx += 1
            return row

        return None

    def build_message(self, raw_row: dict) -> dict:
        """Construit un message strictement conforme au contrat JSON Kafka."""
        msg = {
            "transaction_id": "tx_" + str(uuid.uuid4()),
            "step": max(1, int(float(raw_row.get("step", 1) or 1))),
            "type": str(raw_row.get("type", "TRANSFER")).strip().upper(),
            "produced_at": now_iso(),
        }

        for field in NUMERIC_FIELDS:
            try:
                value = float(raw_row.get(field, 0.0) or 0.0)
            except (TypeError, ValueError):
                value = 0.0
            msg[field] = max(0.0, value)

        name_orig = raw_row.get("nameOrig")
        if name_orig:
            msg["nameOrig"] = str(name_orig)
        name_dest = raw_row.get("nameDest")
        if name_dest:
            msg["nameDest"] = str(name_dest)

        return msg

    def start(self, rate: float = None, fraud_ratio: float = None):
        with self.lock:
            if rate is not None:
                new_rate = float(rate)
                if new_rate <= 0:
                    raise ValueError("rate_tx_per_sec doit etre strictement positif")
                self.rate = min(5000.0, max(1.0, new_rate))
            if fraud_ratio is not None:
                new_ratio = float(fraud_ratio)
                if not 0.0 <= new_ratio <= 1.0:
                    raise ValueError("fraud_ratio doit etre compris entre 0.0 et 1.0")
                self.fraud_ratio = new_ratio
            self.is_running = True
            print(
                f"[Simulator] Demarrage flux : {self.rate} tx/s, ratio={self.fraud_ratio}",
                flush=True,
            )

    def stop(self):
        with self.lock:
            self.is_running = False
        print("[Simulator] Flux mis en pause", flush=True)

    def status(self) -> dict:
        with self.lock:
            return {
                "is_running": self.is_running,
                "rate_tx_per_sec": int(self.rate),
                "fraud_ratio": self.fraud_ratio,
                "total_sent": self.total_sent,
                "total_delivered": self.total_delivered,
                "errors_count": self.errors_count,
                "dataset_rows": len(self.rows_all),
                "last_error": self.last_error,
            }

    def run_loop(self):
        """Boucle principale d'emission vers Kafka a debit constant."""
        print(
            f"[Simulator] Producteur Kafka vers {self.bootstrap} topic={self.topic}",
            flush=True,
        )
        last_report = 0

        def on_delivery(err, _msg):
            if err is not None:
                with self.lock:
                    self.errors_count += 1
                    self.last_error = str(err)
                    current_errors = self.errors_count
                if current_errors % 100 == 1:
                    print(f"[Kafka Error] Echec livraison : {err}", flush=True)
            else:
                with self.lock:
                    self.total_delivered += 1

        while True:
            with self.lock:
                running = self.is_running
                rate = max(1.0, self.rate)

            if not running or not (self.rows_normal or self.rows_fraud):
                # Continuer a servir les callbacks de livraison des messages deja en file.
                self.producer.poll(0)
                time.sleep(0.2)
                continue

            target = max(1, int(round(rate)))
            sent_this_second = 0
            loop_start = time.perf_counter()

            while sent_this_second < target:
                with self.lock:
                    if not self.is_running:
                        break

                raw_row = self._pick_row()
                if raw_row is None:
                    break

                msg = self.build_message(raw_row)
                try:
                    self.producer.produce(
                        self.topic,
                        key=msg["transaction_id"],
                        value=json.dumps(msg, separators=(",", ":")).encode("utf-8"),
                        on_delivery=on_delivery,
                    )
                except BufferError:
                    # File locale pleine : laisser librdkafka vider le buffer.
                    self.producer.poll(0.1)
                    continue
                except Exception as e:
                    print(f"[Simulator Exception] produce error : {e}", flush=True)
                    time.sleep(0.5)
                    continue

                sent_this_second += 1
                with self.lock:
                    self.total_sent += 1
                    total_sent = self.total_sent

                if sent_this_second % 100 == 0:
                    self.producer.poll(0)

                if total_sent - last_report >= 5000:
                    self.producer.flush(1.0)
                    print(
                        f"[Simulator] {total_sent} messages publies dans {self.topic}",
                        flush=True,
                    )
                    last_report = total_sent

            self.producer.poll(0)

            elapsed = time.perf_counter() - loop_start
            if elapsed < 1.0:
                time.sleep(1.0 - elapsed)


class ControlHttpHandler(BaseHTTPRequestHandler):
    simulator: StreamSimulator = None

    def _set_headers(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _write_json(self, code: int, payload: dict):
        self._set_headers(code)
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        if self.path in ["/status", "/api/v1/stream/status"]:
            self._write_json(200, self.simulator.status())
        elif self.path in ["/health", "/api/v1/health"]:
            status = self.simulator.status()
            healthy = status["dataset_rows"] > 0
            status["status"] = "healthy" if healthy else "unhealthy"
            self._write_json(200 if healthy else 503, status)
        else:
            self._write_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path not in ["/control", "/api/v1/stream/control"]:
            self._write_json(404, {"error": "not found"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        try:
            payload = json.loads(body) if body else {}
            action = str(payload.get("action", "start")).lower()
            if action not in ("start", "stop"):
                raise ValueError("action doit valoir 'start' ou 'stop'")

            rate = payload.get("rate_tx_per_sec")
            fraud_ratio = payload.get("fraud_ratio")

            if action == "stop":
                self.simulator.stop()
            else:
                self.simulator.start(rate=rate, fraud_ratio=fraud_ratio)

            self._write_json(200, self.simulator.status())
        except ValueError as e:
            self._write_json(422, {"error": str(e)})
        except Exception as e:
            self._write_json(400, {"error": str(e)})

    def log_message(self, format, *args):
        # Silence HTTP logs
        return


def main():
    parser = argparse.ArgumentParser(description="Simulateur de trafic PaySim -> Kafka")
    parser.add_argument("--file", default=os.getenv("DATA_FILE", "/data/test_stream.csv"))
    parser.add_argument("--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP", "localhost:29092"))
    parser.add_argument("--topic", default=os.getenv("KAFKA_TOPIC", "transactions_stream"))
    parser.add_argument("--rate", type=float, default=float(os.getenv("RATE", "500")))
    parser.add_argument(
        "--fraud-ratio", type=float, default=float(os.getenv("FRAUD_RATIO", "0.0013"))
    )
    parser.add_argument("--control-port", type=int, default=int(os.getenv("CONTROL_PORT", "8001")))
    parser.add_argument(
        "--auto-start", action="store_true", default=os.getenv("AUTO_START", "true").lower() == "true"
    )
    args = parser.parse_args()

    # Fallback : si test_stream.csv est absent, utiliser test.csv
    if not os.path.exists(args.file):
        alt = os.path.join(os.path.dirname(args.file), "test.csv")
        if os.path.exists(alt):
            args.file = alt

    sim = StreamSimulator(
        data_file=args.file,
        bootstrap=args.bootstrap,
        topic=args.topic,
        rate=args.rate,
        fraud_ratio=args.fraud_ratio,
        auto_start=args.auto_start,
    )

    # Thread du simulateur de streaming
    sim_thread = threading.Thread(target=sim.run_loop, daemon=True)
    sim_thread.start()

    # Serveur HTTP de controle
    ControlHttpHandler.simulator = sim
    server = HTTPServer(("0.0.0.0", args.control_port), ControlHttpHandler)
    print(f"[Simulator] Serveur HTTP de controle pret sur le port {args.control_port}", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[Simulator] Arret...", flush=True)
    finally:
        sim.stop()
        sim.producer.flush(5.0)
        server.server_close()


if __name__ == "__main__":
    main()
