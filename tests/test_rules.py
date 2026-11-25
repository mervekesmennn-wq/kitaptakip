import os
import pytest
from datetime import datetime, timedelta

import application
import db


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "kitap.db"
    cover_dir = tmp_path / "kapaklar"
    monkeypatch.setattr(db, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(db, "COVER_DIR", cover_dir)
    db.init_db()
    return db_path


def test_page_validation(temp_db):
    application.validate_page_update(300, 20, 20)
    with pytest.raises(ValueError):
        application.validate_page_update(300, 20, 301)
    with pytest.raises(ValueError):
        application.validate_page_update(300, 20, 19)
    with pytest.raises(ValueError):
        application.validate_page_update(0, 0, 1)


def test_finish_estimate(temp_db):
    now = datetime.now()
    logs = [
        {"pages_read": 20, "logged_at": now - timedelta(days=6)},
        {"pages_read": 50, "logged_at": now - timedelta(days=3)},
        {"pages_read": 80, "logged_at": now},
    ]
    assert application.estimate_finish_days(logs, 200, 80) == 10


def test_annual_goal_status():
    status = application.goal_status(9, 24)
    assert status["remaining"] == 15
    assert "2 kitap" not in status["message"]
    assert "15" in status["message"]
    assert application.goal_status(24, 24)["remaining"] == 0
