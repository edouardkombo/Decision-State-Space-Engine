from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from dsse.models import CaseState, case_state_from_payload, case_state_to_payload

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS singular_entity (
        entity_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        entity_key TEXT,
        state TEXT,
        payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS singular_event (
        event_id TEXT PRIMARY KEY,
        case_id TEXT,
        event_type TEXT NOT NULL,
        actor_type TEXT,
        actor_id TEXT,
        source_artifact_id TEXT,
        payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS singular_relation (
        relation_id TEXT PRIMARY KEY,
        from_entity_id TEXT NOT NULL,
        to_entity_id TEXT NOT NULL,
        relation_type TEXT NOT NULL,
        weight DOUBLE PRECISION,
        payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS singular_snapshot (
        snapshot_id TEXT PRIMARY KEY,
        case_id TEXT,
        snapshot_type TEXT NOT NULL,
        payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS singular_artifact (
        artifact_id TEXT PRIMARY KEY,
        artifact_type TEXT NOT NULL,
        storage_uri TEXT NOT NULL,
        checksum TEXT,
        mime_type TEXT,
        payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS singular_run (
        run_id TEXT PRIMARY KEY,
        run_type TEXT NOT NULL,
        model_entity_id TEXT,
        status TEXT NOT NULL,
        payload_jsonb JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ
    );
    """,
]


@dataclass(slots=True)
class DatabaseCheck:
    ok: bool
    message: str


class DatabaseManager:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def validate_dsn(self) -> DatabaseCheck:
        parsed = urlparse(self.dsn)
        if parsed.scheme not in {"postgresql", "postgres"}:
            return DatabaseCheck(False, "Only PostgreSQL DSNs are supported.")
        if not parsed.hostname or not parsed.path.strip("/"):
            return DatabaseCheck(False, "PostgreSQL DSN must include host and database name.")
        return DatabaseCheck(True, "DSN format looks valid.")

    def connect(self):
        import psycopg

        return psycopg.connect(self.dsn)

    def _parsed_dsn(self):
        return urlparse(self.dsn)

    def _database_name(self) -> str:
        return self._parsed_dsn().path.strip("/")

    def _maintenance_dsns(self) -> list[str]:
        parsed = self._parsed_dsn()
        candidates: list[str] = []
        for db_name in ("postgres", "template1"):
            admin_dsn = urlunparse(parsed._replace(path=f"/{db_name}"))
            if admin_dsn not in candidates:
                candidates.append(admin_dsn)
        return candidates

    def _is_missing_database_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "does not exist" in text and "database" in text

    def _entity_id(self, case_key: str) -> str:
        return f"case:{case_key}"

    def ensure_database_exists(self) -> DatabaseCheck:
        import psycopg
        from psycopg import sql

        db_name = self._database_name()
        if not db_name:
            return DatabaseCheck(False, "Database name is missing from the PostgreSQL DSN.")

        last_error: Exception | None = None
        for admin_dsn in self._maintenance_dsns():
            try:
                with psycopg.connect(admin_dsn, autocommit=True) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
                        exists = cur.fetchone() is not None
                        if exists:
                            return DatabaseCheck(True, f"Database '{db_name}' already exists.")
                        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
                        return DatabaseCheck(True, f"Database '{db_name}' created.")
            except Exception as exc:  # pragma: no cover
                last_error = exc

        if last_error is None:  # pragma: no cover
            return DatabaseCheck(False, f"Could not create database '{db_name}'.")
        return DatabaseCheck(False, f"Could not create database '{db_name}': {last_error}")

    def test_connection(self) -> DatabaseCheck:
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            return DatabaseCheck(True, "Connection OK")
        except Exception as exc:  # pragma: no cover
            if self._is_missing_database_error(exc):
                creation = self.ensure_database_exists()
                if not creation.ok:
                    return DatabaseCheck(False, creation.message)
                try:
                    with self.connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT 1")
                            cur.fetchone()
                    return DatabaseCheck(True, f"{creation.message} Connection OK")
                except Exception as retry_exc:
                    return DatabaseCheck(False, f"Database was created but connection still failed: {retry_exc}")
            return DatabaseCheck(False, f"Connection failed: {exc}")

    def ensure_schema(self) -> DatabaseCheck:
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    for stmt in SCHEMA_SQL:
                        cur.execute(stmt)
                conn.commit()
            return DatabaseCheck(True, "Schema ready")
        except Exception as exc:  # pragma: no cover
            return DatabaseCheck(False, f"Schema creation failed: {exc}")

    def ensure_pgvector(self) -> DatabaseCheck:
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                conn.commit()
            return DatabaseCheck(True, "pgvector ready")
        except Exception as exc:  # pragma: no cover
            return DatabaseCheck(False, f"pgvector setup failed: {exc}")

    def save_case_runtime(self, case: CaseState, event_type: str, payload: dict | None = None) -> DatabaseCheck:
        from psycopg.types.json import Jsonb

        case_payload = case_state_to_payload(case)
        event_payload = {
            "case_key": case.case_key,
            "lifecycle": case.lifecycle,
            "status_reason": case.status_reason,
            "history": list(case.history),
        }
        if payload:
            event_payload.update(payload)
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO singular_entity (entity_id, entity_type, entity_key, state, payload_jsonb)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (entity_id) DO UPDATE SET
                            entity_type = EXCLUDED.entity_type,
                            entity_key = EXCLUDED.entity_key,
                            state = EXCLUDED.state,
                            payload_jsonb = EXCLUDED.payload_jsonb,
                            updated_at = NOW()
                        """,
                        (
                            self._entity_id(case.case_key),
                            "case_runtime",
                            case.case_key,
                            case.lifecycle,
                            Jsonb(case_payload),
                        ),
                    )
                    cur.execute(
                        "INSERT INTO singular_snapshot (snapshot_id, case_id, snapshot_type, payload_jsonb) VALUES (%s, %s, %s, %s)",
                        (
                            f"snap:{case.case_key}:{uuid4().hex}",
                            case.case_key,
                            "case_runtime",
                            Jsonb(case_payload),
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO singular_event (event_id, case_id, event_type, actor_type, actor_id, payload_jsonb)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            f"event:{case.case_key}:{uuid4().hex}",
                            case.case_key,
                            event_type,
                            case.current_owner,
                            case.current_owner,
                            Jsonb(event_payload),
                        ),
                    )
                conn.commit()
            return DatabaseCheck(True, f"Runtime state persisted for case '{case.case_key}'.")
        except Exception as exc:  # pragma: no cover
            return DatabaseCheck(False, f"Runtime persistence failed: {exc}")

    def load_case_runtime(self, case_key: str) -> CaseState | None:
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT payload_jsonb FROM singular_entity WHERE entity_id = %s AND entity_type = %s",
                        (self._entity_id(case_key), "case_runtime"),
                    )
                    row = cur.fetchone()
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(f"Could not load runtime state for case '{case_key}': {exc}") from exc
        if not row:
            return None
        payload = row[0]
        if not isinstance(payload, dict):
            raise RuntimeError(f"Runtime payload for case '{case_key}' is not a JSON object.")
        return case_state_from_payload(payload)

    def reset_database(self) -> DatabaseCheck:
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    for table in ["singular_run", "singular_artifact", "singular_snapshot", "singular_relation", "singular_event", "singular_entity"]:
                        cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                conn.commit()
            return DatabaseCheck(True, "Database cleared")
        except Exception as exc:  # pragma: no cover
            return DatabaseCheck(False, f"Reset failed: {exc}")
