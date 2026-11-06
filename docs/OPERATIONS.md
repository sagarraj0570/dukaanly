# Dukaanly — Operational Runbook & Production Operations

## 1. Health Checks & Probes

Dukaanly implements a three-tier observability and health check architecture:

### A. Liveness Probe (`GET /api/v1/health/live`)
- **Target**: Kubernetes, Docker healthchecks, AWS ALB target groups.
- **Contract**: Fast, dependency-free check returning `200 OK` as long as the Python/FastAPI process is responsive.
- **Response**: `{"status": "ok"}`
- **Logging**: Supressed in `RequestCorrelationMiddleware` to prevent log saturation.

### B. Readiness Probe (`GET /api/v1/health/ready`)
- **Target**: Ingress traffic routing, container orchestrator traffic admission.
- **Contract**: Validates connectivity to PostgreSQL, Redis, and core configuration with strict bounded timeouts (`2.5s`). Never hangs indefinitely.
- **Status Codes**:
  - `200 OK`: All mandatory dependencies are reachable and healthy.
  - `503 Service Unavailable`: Database or Redis is unreachable. Traffic should not be routed to this instance.
- **Response**:
  ```json
  {
    "status": "ready",
    "database": true,
    "redis": true,
    "configuration": true
  }
  ```

### C. Operational Diagnostics Endpoint (`GET /api/v1/health/diagnostics`)
- **Target**: Internal operations dashboards, on-call engineers, monitoring daemons.
- **Authorization**: Strictly restricted to users with `admin` role (`require_role(UserRole.admin)`). Unauthenticated requests receive `401 Unauthorized`; customers and shop owners receive `403 Forbidden`.
- **Security Invariant**: Never exposes passwords, JWT secrets, or PII.
- **Response Schema**:
  ```json
  {
    "status": "healthy",
    "app_name": "Dukaanly",
    "app_version": "1.0.0",
    "environment": "production",
    "uptime_seconds": 14285.42,
    "database": {
      "status": "connected",
      "pool": {
        "size": 10,
        "pool_size": 10,
        "checked_in": 8,
        "checked_out": 2,
        "overflow": 0,
        "total_connections": 10,
        "pre_ping": true,
        "recycle_seconds": 1800
      }
    },
    "redis": {
      "connected": true,
      "latency_ms": 1.45,
      "max_connections": 50,
      "url_masked": "redis://***@redis:6379/0",
      "socket_timeout": 3.0,
      "connect_timeout": 3.0
    },
    "celery": {
      "broker_url_masked": "redis://***@redis:6379/0",
      "broker_url_configured": true,
      "task_acks_late": true,
      "reject_on_worker_lost": true,
      "worker_prefetch_multiplier": 1,
      "soft_time_limit": 240,
      "time_limit": 300,
      "scheduled_tasks_count": 5,
      "registered_tasks_count": 5
    },
    "websockets": {
      "active_connections": 14,
      "active_deliveries_tracked": 7
    }
  }
  ```

---

## 2. Troubleshooting & Incident Response

### Incident 1: High Database Latency or Connection Pool Starvation
- **Symptoms**:
  - `/ready` latency increases or returns `503`.
  - Diagnostics reports `checked_out == pool_size + max_overflow` and `checked_in == 0`.
- **Investigation**:
  1. Inspect PostgreSQL active queries:
     ```sql
     SELECT pid, now() - query_start AS duration, state, query 
     FROM pg_stat_activity 
     WHERE state != 'idle' 
     ORDER BY duration DESC;
     ```
  2. Check for deadlocks or lock contention on `orders` or `inventory`:
     ```sql
     SELECT blocked_locks.pid AS blocked_pid, blocking_locks.pid AS blocking_pid,
            blocked_activity.query AS blocked_statement
     FROM pg_catalog.pg_locks blocked_locks
     JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
     JOIN pg_catalog.pg_locks blocking_locks 
         ON blocking_locks.locktype = blocked_locks.locktype
         AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
         AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
         AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
         AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
         AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
         AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
         AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
         AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
         AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
         AND blocking_locks.pid != blocked_locks.pid;
     ```
- **Remediation**:
  - Cancel slow query: `SELECT pg_cancel_backend(<pid>);`
  - Terminate blocking connection: `SELECT pg_terminate_backend(<pid>);`
  - Ensure `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` are sized according to total Uvicorn worker count:
    $$\text{Total Connections} = \text{Workers} \times (\text{DB\_POOL\_SIZE} + \text{DB\_MAX\_OVERFLOW}) \le \text{PostgreSQL max\_connections} - 20$$

---

### Incident 2: Redis Unavailable or Intermittent Connection Drops
- **Behavior**:
  - Rate limiting automatically fails open with structured warning logs to protect core checkout and browsing traffic.
  - Live tracking PubSub reconnection loops back off and reconnect.
- **Verification**:
  - Check Redis container status: `docker exec -it dukaanly_redis redis-cli ping`
  - Verify memory usage: `docker exec -it dukaanly_redis redis-cli info memory`
- **Mitigation**:
  - Restart Redis container: `docker restart dukaanly_redis`.
  - Backend automatically re-establishes pool connections within `REDIS_SOCKET_CONNECT_TIMEOUT` (3s).

---

### Incident 3: Celery Task Failure or Worker Crash
- **Behavior**:
  - Because `task_acks_late=True` and `task_reject_on_worker_lost=True`, uncompleted tasks are automatically re-queued when a worker crashes or is restarted.
  - `worker_prefetch_multiplier=1` guarantees fair task distribution among workers.
  - Tasks encountering `OperationalError` or `DBAPIError` retry up to 3 times with exponential backoff.
- **Inspection**:
  - Check Celery logs: `docker logs dukaanly_celery_worker --tail 200`
  - Verify task queue depth:
    ```bash
    celery -A app.core.celery_app inspect active
    ```

---

## 3. Log Correlation & Request Tracing

All HTTP requests and background processes emit structured JSON logs.

### Querying Logs with Correlation ID
1. Every client response includes an `X-Request-ID` header.
2. In log aggregators (Elasticsearch, CloudWatch, Loki), trace an entire request lifecycle by filtering on `request_id`:
   ```json
   { "request_id": "8a3f9e2b1c4d..." }
   ```
3. When tracking upstream requests from webhooks or external partners, use `correlation_id`:
   ```json
   { "correlation_id": "upstream_event_9981" }
   ```
