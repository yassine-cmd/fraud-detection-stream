# Variante Java 17 / Ubuntu 22.04 : Python 3.10 (compatible numpy 1.26 / pandas 2.2)
# La variante "3.5.1-python3" par defaut est basee sur Python 3.8 (numpy 1.26 incompatible).
FROM apache/spark:3.5.1-java17-python3

USER root

# libgomp1 est requis par XGBoost / scikit-learn (OpenMP) sur l'image Ubuntu.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Versions ML figees : identiques a celles utilisees pour entrainer model.joblib
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt \
    && mkdir -p /checkpoint /models /app /tmp/.ivy \
    && chown -R spark:spark /checkpoint /models /app /tmp/.ivy

COPY streaming_job.py /app/streaming_job.py

USER spark
