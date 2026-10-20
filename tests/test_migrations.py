"""STA-001: versioned schema migrations with backup, atomic steps, and newer-DB refusal."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_orchestra import state as state_mod
from mod_orchestra.state import Store, MIGRATIONS, SCHEMA_VERSION, StateError


def apply(db: Path, upto: int, extra_sql: str = ""):
    con = sqlite3.connect(db)
    for version, _title, sql in MIGRATIONS:
        if version > upto:
            break
        for st in sql.split(";"):
            if st.strip():
                con.execute(st)
    if extra_sql:
        con.execute(extra_sql)
    con.execute(f"PRAGMA user_version={upto}")
    con.commit(); con.close()


class Migrations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_fresh_db_lands_on_current_version(self):
        self.assertEqual(Store(self.dir / "a.sqlite").schema_version(), SCHEMA_VERSION)

    def test_reopen_is_a_noop_without_backup(self):
        db = self.dir / "b.sqlite"; Store(db); Store(db)
        self.assertEqual(list(self.dir.glob("b.sqlite.bak-*")), [])

    def test_v1_db_is_upgraded_in_place_with_backup_and_data_kept(self):
        db = self.dir / "old.sqlite"
        apply(db, 1, "INSERT INTO projects VALUES('p1','/x','P','{}','DRAFT','IDEA',1)")
        store = Store(db)
        self.assertEqual(store.schema_version(), SCHEMA_VERSION)
        self.assertEqual(store.project("p1")["id"], "p1")
        self.assertEqual(store.evidence("p1"), [])
        backup = self.dir / "old.sqlite.bak-v1"
        self.assertTrue(backup.is_file())
        con = sqlite3.connect(backup)
        try:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT count(*) FROM projects").fetchone()[0], 1)
        finally:
            con.close()  # Windows cannot remove an open DB file during TemporaryDirectory cleanup

    def test_db_from_newer_craftctl_is_refused(self):
        db = self.dir / "future.sqlite"
        con = sqlite3.connect(db); con.execute(f"PRAGMA user_version={SCHEMA_VERSION + 50}"); con.commit(); con.close()
        with self.assertRaisesRegex(StateError, "newer than this craftctl"):
            Store(db)

    def test_failed_step_rolls_back_and_keeps_previous_version(self):
        db = self.dir / "broken.sqlite"
        apply(db, SCHEMA_VERSION)
        broken = MIGRATIONS + [(SCHEMA_VERSION + 1, "broken", "CREATE TABLE half(a); CREATE TABLE half(a);")]
        with patch.object(state_mod, "MIGRATIONS", broken), patch.object(state_mod, "SCHEMA_VERSION", SCHEMA_VERSION + 1):
            with self.assertRaisesRegex(StateError, "migration v%d .*failed" % (SCHEMA_VERSION + 1)):
                Store(db)
        con = sqlite3.connect(db)
        try:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
            self.assertEqual(con.execute("SELECT name FROM sqlite_master WHERE name='half'").fetchall(), [])
        finally:
            con.close()

    def test_migration_list_is_contiguous_and_append_only(self):
        self.assertEqual([m[0] for m in MIGRATIONS], list(range(1, len(MIGRATIONS) + 1)))


if __name__ == "__main__":
    unittest.main()
