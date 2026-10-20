"""Durable, transactional Footprint state, versioned task claims and approval records."""
from __future__ import annotations
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from .config import ensure_home, HOME

DDL = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, root TEXT NOT NULL UNIQUE, name TEXT NOT NULL, spec_json TEXT NOT NULL,
  spec_state TEXT NOT NULL DEFAULT 'DRAFT', status TEXT NOT NULL DEFAULT 'IDEA', created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
  created_at REAL NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), role TEXT NOT NULL,
  title TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'BACKLOG', version INTEGER NOT NULL DEFAULT 0,
  lease_owner TEXT, lease_expiry REAL, attempt INTEGER NOT NULL DEFAULT 0, evidence_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS task_edges (
  predecessor TEXT NOT NULL REFERENCES tasks(id), successor TEXT NOT NULL REFERENCES tasks(id),
  PRIMARY KEY(predecessor, successor)
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), kind TEXT NOT NULL,
  digest TEXT NOT NULL, description TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
  created_at REAL NOT NULL, expires_at REAL NOT NULL, used_at REAL
);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id),
  level TEXT NOT NULL, actor TEXT NOT NULL, created_at REAL NOT NULL, note TEXT NOT NULL DEFAULT '',
  artifact_sha256 TEXT, manifest_sha256 TEXT, payload_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence(project_id, id);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_events_project ON events(project_id, id);
"""

class StateError(RuntimeError):
    pass

class Store:
    def __init__(self, path: Path | None = None):
        if path is None:
            ensure_home()
            path = HOME / "state.sqlite"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=15000")
        try:
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _initialize(self) -> None:
        con = sqlite3.connect(self.path, timeout=15)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA foreign_keys=ON")
            con.executescript(DDL)
            con.execute("PRAGMA user_version=1")
            con.commit()
        finally:
            con.close()

    @staticmethod
    def event(con: sqlite3.Connection, pid: str, actor: str, kind: str, payload: dict) -> None:
        con.execute("INSERT INTO events(project_id,created_at,actor,kind,payload_json) VALUES(?,?,?,?,?)",
                    (pid, time.time(), actor, kind, json.dumps(payload, sort_keys=True)))

    def create_project(self, pid: str, root: str, name: str, spec: dict) -> dict:
        with self.tx() as con:
            con.execute("INSERT INTO projects(id,root,name,spec_json,created_at) VALUES(?,?,?,?,?)",
                        (pid, root, name, json.dumps(spec, sort_keys=True), time.time()))
            self.event(con, pid, "system", "PROJECT_CREATED", {"root": root})
        return self.project(pid)

    def project(self, pid: str) -> dict:
        with self.tx() as con:
            row = con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
            if row is None:
                raise StateError(f"Project not found: {pid}")
            return {**dict(row), "spec": json.loads(row["spec_json"])}

    def projects(self) -> list[dict]:
        with self.tx() as con:
            return [dict(row) for row in con.execute("SELECT id,name,root,status,spec_state,created_at FROM projects ORDER BY created_at DESC")]

    def update_project(self, pid: str, *, status: str | None = None, spec_state: str | None = None) -> None:
        with self.tx() as con:
            if not con.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
                raise StateError("Unknown project")
            if status is not None:
                con.execute("UPDATE projects SET status=? WHERE id=?", (status, pid))
                self.event(con, pid, "controller", "PROJECT_STATUS", {"status": status})
            if spec_state is not None:
                con.execute("UPDATE projects SET spec_state=? WHERE id=?", (spec_state, pid))
                self.event(con, pid, "user", "SPEC_STATUS", {"status": spec_state})

    def set_tasks(self, pid: str, tasks: list[dict], edges: list[tuple[str, str]]) -> None:
        with self.tx() as con:
            if con.execute("SELECT 1 FROM tasks WHERE project_id=? LIMIT 1", (pid,)).fetchone():
                raise StateError("Tasks already planned; spec revision/replanning is not implemented")
            for t in tasks:
                con.execute("INSERT INTO tasks(id,project_id,role,title,state) VALUES(?,?,?,?,?)",
                            (t["id"], pid, t["role"], t["title"], "READY" if t.get("ready") else "BACKLOG"))
            for a, b in edges:
                con.execute("INSERT INTO task_edges(predecessor,successor) VALUES(?,?)", (a, b))
            self.event(con, pid, "scrum-master", "TASK_GRAPH_CREATED", {"tasks": len(tasks), "edges": len(edges)})

    def tasks(self, pid: str) -> list[dict]:
        with self.tx() as con:
            return [dict(r) for r in con.execute("SELECT * FROM tasks WHERE project_id=? ORDER BY id", (pid,))]

    def refresh_ready(self, pid: str) -> None:
        with self.tx() as con:
            con.execute("""UPDATE tasks SET state='READY',version=version+1 WHERE project_id=? AND state='BACKLOG'
                AND NOT EXISTS (SELECT 1 FROM task_edges e JOIN tasks p ON p.id=e.predecessor
                                WHERE e.successor=tasks.id AND p.state!='DONE')""", (pid,))

    def claim(self, task_id: str, worker: str, *, ttl: int = 300) -> dict | None:
        if not (1 <= ttl <= 3600):
            raise StateError("Invalid lease TTL")
        with self.tx() as con:
            row = con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or (row["state"] != "READY" and not (
                    row["state"] in ("LEASED", "RUNNING") and (row["lease_expiry"] or 0) < time.time())):
                return None
            con.execute("UPDATE tasks SET state='LEASED',lease_owner=?,lease_expiry=?,version=version+1,attempt=attempt+1 WHERE id=?",
                        (worker, time.time() + ttl, task_id))
            self.event(con, row["project_id"], worker, "TASK_LEASED", {"task": task_id})
            return dict(con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())

    def lease_info(self, task_id: str) -> dict | None:
        with self.tx() as con:
            row = con.execute("SELECT id,state,lease_owner,lease_expiry,version FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            return None
        remaining = max(0, int((row["lease_expiry"] or 0) - time.time())) if row["lease_owner"] else 0
        return {"task": row["id"], "state": row["state"], "holder": row["lease_owner"], "seconds_left": remaining, "version": row["version"]}

    def force_release(self, task_id: str, reason: str) -> dict:
        """USER-ONLY: break any lease on a task and return it to READY."""
        with self.tx() as con:
            row = con.execute("SELECT project_id,state,lease_owner FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise StateError(f"Task not found: {task_id}")
            if row["state"] not in ("LEASED", "RUNNING"):
                raise StateError(f"Task {task_id} is {row['state']}, nothing to release")
            con.execute("UPDATE tasks SET state='READY',lease_owner=NULL,lease_expiry=NULL,version=version+1 WHERE id=?", (task_id,))
            self.event(con, row["project_id"], "user", "TASK_FORCE_RELEASED", {"task": task_id, "previous_holder": row["lease_owner"], "reason": reason[:300]})
        return {"task": task_id, "state": "READY", "previous_holder": row["lease_owner"]}

    def delete_project(self, pid: str) -> dict:
        """USER-ONLY: remove every row for a project. The workspace directory is handled by the caller."""
        with self.tx() as con:
            if con.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone() is None:
                raise StateError(f"Project not found: {pid}")
            counts = {}
            for table in ("evidence", "approvals", "events"):
                counts[table] = con.execute(f"DELETE FROM {table} WHERE project_id=?", (pid,)).rowcount
            counts["task_edges"] = con.execute(
                "DELETE FROM task_edges WHERE predecessor IN (SELECT id FROM tasks WHERE project_id=?) "
                "OR successor IN (SELECT id FROM tasks WHERE project_id=?)", (pid, pid)).rowcount
            counts["tasks"] = con.execute("DELETE FROM tasks WHERE project_id=?", (pid,)).rowcount
            con.execute("DELETE FROM projects WHERE id=?", (pid,))
        return {"deleted": pid, "rows": counts}

    def release(self, task_id: str, worker: str, version: int, reason: str) -> bool:
        """Give a lease back (task returns to READY) when the worker failed before producing evidence."""
        with self.tx() as con:
            cur = con.execute("UPDATE tasks SET state='READY',lease_owner=NULL,lease_expiry=NULL,version=version+1 "
                              "WHERE id=? AND lease_owner=? AND version=? AND state IN ('LEASED','RUNNING')",
                              (task_id, worker, version))
            if cur.rowcount == 1:
                pid = con.execute("SELECT project_id FROM tasks WHERE id=?", (task_id,)).fetchone()["project_id"]
                self.event(con, pid, worker, "TASK_RELEASED", {"task": task_id, "reason": reason[:300]})
            return cur.rowcount == 1

    def heartbeat(self, task_id: str, worker: str, version: int, ttl: int = 300) -> bool:
        with self.tx() as con:
            cur = con.execute("UPDATE tasks SET lease_expiry=? WHERE id=? AND lease_owner=? AND version=? AND state IN ('LEASED','RUNNING')",
                              (time.time() + ttl, task_id, worker, version))
            return cur.rowcount == 1

    def finish(self, task_id: str, worker: str, version: int, evidence: list[dict]) -> bool:
        if not evidence or any(not isinstance(e, dict) or not e.get("kind") or not e.get("value") for e in evidence):
            raise StateError("Completion requires explicit evidence entries")
        with self.tx() as con:
            row = con.execute("SELECT project_id FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise StateError("Unknown task")
            cur = con.execute("""UPDATE tasks SET state='DONE',version=version+1,lease_owner=NULL,lease_expiry=NULL,
               evidence_json=? WHERE id=? AND state IN ('LEASED','RUNNING','VERIFYING')
               AND version=? AND lease_owner=? AND lease_expiry>?""",
               (json.dumps(evidence), task_id, version, worker, time.time()))
            if cur.rowcount:
                self.event(con, row["project_id"], worker, "TASK_COMPLETED", {"task": task_id, "evidence": evidence})
            return bool(cur.rowcount)

    @staticmethod
    def digest(kind: str, args: dict) -> str:
        return hashlib.sha256(json.dumps({"kind": kind, "args": args}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def request_approval(self, pid: str, kind: str, args: dict, description: str, *, ttl: int = 3600) -> dict:
        if not (60 <= ttl <= 86400):
            raise StateError("Approval must expire within 1 minute to 24 hours")
        approval = secrets.token_urlsafe(18)
        with self.tx() as con:
            con.execute("INSERT INTO approvals(id,project_id,kind,digest,description,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",
                        (approval, pid, kind, self.digest(kind, args), description, time.time(), time.time() + ttl))
            self.event(con, pid, "controller", "APPROVAL_REQUESTED", {"id": approval, "kind": kind, "description": description})
        return {"id": approval, "kind": kind, "description": description}

    def approvals(self, pid: str) -> list[dict]:
        with self.tx() as con:
            return [dict(x) for x in con.execute("SELECT * FROM approvals WHERE project_id=? ORDER BY created_at DESC", (pid,))]

    def decide_approval(self, approval: str, granted: bool) -> None:
        with self.tx() as con:
            row = con.execute("SELECT * FROM approvals WHERE id=?", (approval,)).fetchone()
            if not row or row["state"] != "PENDING" or row["expires_at"] <= time.time():
                raise StateError("Approval not pending or expired")
            con.execute("UPDATE approvals SET state=? WHERE id=?", ("GRANTED" if granted else "DENIED", approval))
            self.event(con, row["project_id"], "user", "APPROVAL_DECIDED", {"id": approval, "granted": granted})

    def consume_approval(self, approval: str, pid: str, kind: str, args: dict) -> bool:
        with self.tx() as con:
            cur = con.execute("""UPDATE approvals SET state='CONSUMED',used_at=? WHERE id=? AND project_id=? AND kind=?
                AND digest=? AND state='GRANTED' AND expires_at>?""",
                (time.time(), approval, pid, kind, self.digest(kind, args), time.time()))
            if cur.rowcount:
                self.event(con, pid, "controller", "APPROVAL_CONSUMED", {"id": approval, "kind": kind})
            return bool(cur.rowcount)

    def add_evidence(self, pid: str, level: str, actor: str, note: str, *, artifact_sha256: str | None,
                     manifest_sha256: str | None, payload: dict) -> dict:
        row = {"project_id": pid, "level": level, "actor": actor, "created_at": time.time(), "note": note,
               "artifact_sha256": artifact_sha256, "manifest_sha256": manifest_sha256}
        with self.tx() as con:
            cur = con.execute(
                "INSERT INTO evidence(project_id,level,actor,created_at,note,artifact_sha256,manifest_sha256,payload_json) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (pid, level, actor, row["created_at"], note, artifact_sha256, manifest_sha256, json.dumps(payload, sort_keys=True)))
            row["id"] = cur.lastrowid
            self.event(con, pid, actor, "EVIDENCE", {"level": level, "artifact_sha256": artifact_sha256})
        return row

    def evidence(self, pid: str) -> list[dict]:
        with self.tx() as con:
            rows = con.execute("SELECT id,level,actor,created_at,note,artifact_sha256,manifest_sha256,payload_json "
                               "FROM evidence WHERE project_id=? ORDER BY id", (pid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r); d["payload"] = json.loads(d.pop("payload_json")); out.append(d)
        return out

    def add_event(self, pid: str, actor: str, kind: str, payload: dict) -> None:
        with self.tx() as con:
            self.event(con, pid, actor, kind, payload)

    def events(self, pid: str, limit: int = 50) -> list[dict]:
        with self.tx() as con:
            rows = con.execute("SELECT * FROM events WHERE project_id=? ORDER BY id DESC LIMIT ?", (pid, min(500, max(1, limit))))
            return [dict(r) | {"payload": json.loads(r["payload_json"])} for r in rows]
