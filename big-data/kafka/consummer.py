"""
Consumer de test : lit le topic Kafka, verifie chaque message contre le contrat
(kafka_message.schema.json), verifie que la cle = transaction_id et mesure la
latence de transit (maintenant - produced_at).

Ce n'est PAS le consumer de production (c'est Spark). C'est un outil de controle.

Installation :  pip install confluent-kafka jsonschema
Exemples :
    python consumer.py --schema contracts/kafka_message.schema.json --max 100
    python consumer.py --schema contracts/kafka_message.schema.json --max 0   # jusqu'a Ctrl+C
"""
import argparse
import json
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaError
from jsonschema import Draft7Validator


def parse_iso(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--schema", required=True, help="chemin de kafka_message.schema.json")
    p.add_argument("--bootstrap", default="localhost:29092")
    p.add_argument("--topic", default="transactions_stream")
    p.add_argument("--group", default=None, help="group.id (par defaut : nouveau groupe, relit tout depuis le debut)")
    p.add_argument("--max", type=int, default=100, help="nb de messages a lire (0 = jusqu'a Ctrl+C)")
    p.add_argument("--idle", type=float, default=15, help="arret apres N secondes sans message")
    p.add_argument("--show", type=int, default=3, help="nb de messages affiches en entier")
    args = p.parse_args()

    with open(args.schema, encoding="utf-8") as f:
        validator = Draft7Validator(json.load(f))

    consumer = Consumer({
        "bootstrap.servers": args.bootstrap,
        "group.id": args.group or ("debug-" + uuid.uuid4().hex[:8]),
        "auto.offset.reset": "earliest",   # un nouveau groupe lit depuis le debut du topic
        "enable.auto.commit": True,
    })
    consumer.subscribe([args.topic])

    total = valid = invalid = key_mismatch = 0
    latencies = []
    last_msg_time = time.time()
    print(f"Ecoute de {args.topic} sur {args.bootstrap} ...")

    try:
        while args.max == 0 or total < args.max:
            msg = consumer.poll(1.0)
            if msg is None:
                if time.time() - last_msg_time > args.idle:
                    print(f"Aucun message depuis {args.idle:.0f}s, arret.")
                    break
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    print("Erreur Kafka :", msg.error())
                continue

            last_msg_time = time.time()
            total += 1
            key = msg.key().decode("utf-8") if msg.key() else None

            try:
                body = json.loads(msg.value().decode("utf-8"))
            except Exception as e:
                invalid += 1
                print(f"[INVALIDE] JSON illisible (partition {msg.partition()}, offset {msg.offset()}): {e}")
                continue

            errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
            if errors:
                invalid += 1
                print(f"[INVALIDE] offset {msg.offset()} : {errors[0].message}")
            else:
                valid += 1
                latencies.append((datetime.now(timezone.utc) - parse_iso(body["produced_at"])).total_seconds() * 1000)

            if key != body.get("transaction_id"):
                key_mismatch += 1

            if total <= args.show:
                print(f"--- partition {msg.partition()} offset {msg.offset()} cle={key}")
                print(json.dumps(body, indent=2))
    except KeyboardInterrupt:
        print("Arret demande")
    finally:
        consumer.close()

    print("\n===== BILAN =====")
    print(f"Messages lus          : {total}")
    print(f"Conformes au contrat  : {valid}")
    print(f"Non conformes         : {invalid}")
    print(f"Cle != transaction_id : {key_mismatch}")
    if latencies:
        latencies.sort()
        print(f"Latence transit (ms)  : moy {sum(latencies)/len(latencies):.1f} | "
              f"p95 {latencies[int(len(latencies)*0.95)-1]:.1f} | max {latencies[-1]:.1f}")
        print("(la latence inclut le temps ecoulé depuis l'envoi : relance juste apres le producer pour une mesure realiste)")


if __name__ == "__main__":
    main()