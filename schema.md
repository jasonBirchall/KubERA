```bash
```
CREATE TABLE pod_alerts (
    id           SERIAL PRIMARY KEY,          -- or INTEGER if SQLite
    namespace    TEXT NOT NULL,
    pod_name     TEXT NOT NULL,
    issue_type   TEXT NOT NULL,
    severity     TEXT NOT NULL,
    first_seen   TIMESTAMPTZ NOT NULL,
    last_seen    TIMESTAMPTZ,                 -- NULL ⇒ still ongoing
    UNIQUE (namespace, pod_name, issue_type, first_seen)
);

CREATE INDEX ON pod_alerts (issue_type);
CREATE INDEX ON pod_alerts (first_seen);
```
```

Why this shape?

    One row per episode (continuous failure window).

    When the pod recovers you simply UPDATE … SET last_seen = now().

    Later you can aggregate: “Total CrashLoopBackOff minutes per day”, “MTTR by service”, etc.
