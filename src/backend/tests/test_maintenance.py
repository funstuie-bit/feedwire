"""Exercise scheduled maintenance against a disposable database."""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from models import Base, Feed, Item, Note, UserAction
from tasks import auto_read_old_items, cleanup_old_items


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine)
        self.now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        self.session_patch = patch("tasks.SyncSession", self.sessions)
        self.session_patch.start()
        self.clock_patch = patch("tasks.datetime")
        self.clock = self.clock_patch.start()
        self.clock.now.return_value = self.now
        with self.sessions() as db:
            db.add(Feed(id=1, url="https://example.com/rss"))
            db.commit()

    def tearDown(self):
        self.clock_patch.stop()
        self.session_patch.stop()
        self.engine.dispose()

    def test_auto_read_matches_previous_cron_and_is_idempotent(self):
        old = self.now - timedelta(days=8)
        with self.sessions() as db:
            for id, values in enumerate([
                {"published_at": old},
                {"created_at": old},
                {"published_at": old, "is_saved": True},
                {"published_at": old, "is_hidden": True},
                {"published_at": old, "is_read": True},
                {"published_at": self.now - timedelta(days=7)},
                {"published_at": self.now, "created_at": old},
            ], 1):
                db.add(Item(id=id, feed_id=1, guid=str(id), **{"created_at": self.now, **values}))
            db.commit()
        self.assertEqual(auto_read_old_items(), {"marked_read": 2, "days": 7})
        self.assertEqual(auto_read_old_items()["marked_read"], 0)
        with self.sessions() as db:
            self.assertEqual(list(db.scalars(select(Item.id).where(Item.is_read).order_by(Item.id))), [1, 2, 5])
            self.assertEqual(len(list(db.scalars(select(Item)))), 7)

    def test_retention_keeps_saved_notes_and_learning(self):
        with self.sessions() as db:
            for id in range(1, 5):
                db.add(Item(id=id, feed_id=1, guid=str(id), created_at=self.now - timedelta(days=91), is_saved=id == 2))
            db.flush()
            db.add(Note(item_id=3, content="Keep me"))
            db.add(UserAction(item_id=4, action="read"))
            db.commit()
        cleanup_old_items()
        with self.sessions() as db:
            self.assertEqual(list(db.scalars(select(Item.id).order_by(Item.id))), [2, 3, 4])
