"""SNF2 : charge sur POST /predict.  locust -f tests/locustfile.py --host http://localhost:8000 \
        --headless -u 20 -r 10 -t 1m   (>= 1000 requêtes, lire le P95 dans le rapport)"""
import random
from locust import HttpUser, constant_pacing, task


class PredictUser(HttpUser):
    wait_time = constant_pacing(0.05)

    @task
    def predict(self):
        amt = random.uniform(10, 500000)
        self.client.post("/api/v1/predict", json={
            "step": random.randint(600, 743), "type": random.choice(["TRANSFER", "CASH_OUT", "PAYMENT", "CASH_IN", "DEBIT"]),
            "amount": amt, "oldbalanceOrg": amt, "newbalanceOrig": 0.0,
            "oldbalanceDest": 0.0, "newbalanceDest": amt}, name="/predict")
