// Initialisation MongoDB 'fraud' - conforme a contracts/mongodb_schemas.md
// Idempotent : peut etre rejoue a chaque demarrage (service mongo-config).
// Retention configurable via MONGO_TTL_SECONDS (0 = pas de purge).

const DEFAULT_TTL_SECONDS = 86400;

function readTtlSeconds() {
    let raw = null;
    try {
        if (typeof process !== "undefined" && process.env) {
            raw = process.env.MONGO_TTL_SECONDS;
        }
    } catch (e) {
        raw = null;
    }
    if (raw === null || raw === undefined || String(raw).trim() === "") {
        return DEFAULT_TTL_SECONDS;
    }
    const parsed = parseInt(String(raw).trim(), 10);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        return 0;
    }
    return parsed;
}

const TTL_SECONDS = readTtlSeconds();

db = db.getSiblingDB("fraud");

function ensureCollection(name) {
    if (!db.getCollectionNames().includes(name)) {
        db.createCollection(name);
        print("[mongo-init] collection '" + name + "' creee");
    }
}

function findSingleFieldIndex(coll, field) {
    return coll.getIndexes().find(function (idx) {
        if (!idx.key) {
            return false;
        }
        const keys = Object.keys(idx.key);
        return keys.length === 1 && keys[0] === field;
    });
}

function applyRetention(coll, field, ttlSeconds) {
    const collName = coll.getName();
    const existing = findSingleFieldIndex(coll, field);

    if (ttlSeconds > 0) {
        if (existing) {
            if (existing.expireAfterSeconds === ttlSeconds) {
                print("[mongo-init] " + collName + "." + field + " TTL deja a " + ttlSeconds + "s");
                return;
            }
            if (existing.expireAfterSeconds !== undefined) {
                db.runCommand({
                    collMod: collName,
                    index: {
                        keyPattern: existing.key,
                        expireAfterSeconds: ttlSeconds,
                    },
                });
                print("[mongo-init] " + collName + "." + field + " TTL mis a jour -> " + ttlSeconds + "s");
                return;
            }
            coll.dropIndex(existing.name);
        }
        coll.createIndex(
            { [field]: -1 },
            { name: field + "_ttl", expireAfterSeconds: ttlSeconds, background: true }
        );
        print("[mongo-init] " + collName + "." + field + " index TTL cree (" + ttlSeconds + "s)");
        return;
    }

    if (existing && existing.expireAfterSeconds !== undefined) {
        coll.dropIndex(existing.name);
        coll.createIndex({ [field]: -1 }, { background: true });
        print("[mongo-init] " + collName + "." + field + " TTL supprime (retention infinie)");
        return;
    }
    if (!existing) {
        coll.createIndex({ [field]: -1 }, { background: true });
        print("[mongo-init] " + collName + "." + field + " index de tri cree");
    }
}

ensureCollection("transactions");
ensureCollection("fraud_alerts");
ensureCollection("stats_buckets");
ensureCollection("processed_batches");

db.transactions.createIndex({ is_fraud: 1, scored_at: -1 }, { background: true });
db.transactions.createIndex({ scored_at: -1, type: 1, is_fraud: 1 }, { background: true });
db.stats_buckets.createIndex({ bucket_start: 1 }, { background: true });

applyRetention(db.transactions, "scored_at", TTL_SECONDS);
applyRetention(db.fraud_alerts, "scored_at", TTL_SECONDS);
applyRetention(db.stats_buckets, "bucket_start", TTL_SECONDS);

print(
    "[mongo-init] Base 'fraud' prete. Retention=" +
    (TTL_SECONDS > 0 ? TTL_SECONDS + "s" : "infinie")
);
