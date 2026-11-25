import os
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests


DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/kitap.db")
COVER_DIR = Path(os.environ.get("COVER_DIR", "static/kapaklar"))


def get_connection():
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                publisher TEXT,
                cover_path TEXT,
                source_url TEXT,
                page_count INTEGER NOT NULL DEFAULT 0,
                isbn TEXT,
                publication_year TEXT,
                status TEXT NOT NULL DEFAULT 'Okunacak',
                current_page INTEGER NOT NULL DEFAULT 0,
                rating INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                finished_at TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reading_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                pages_read INTEGER NOT NULL,
                logged_at TEXT NOT NULL,
                FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def _dict(row):
    return dict(row) if row else None


def book_exists(title, isbn=""):
    with get_connection() as connection:
        if isbn:
            row = connection.execute(
                "SELECT id FROM books WHERE isbn = ? OR lower(title) = lower(?)",
                (isbn, title),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT id FROM books WHERE lower(title) = lower(?)", (title,)
            ).fetchone()
        return row is not None


def add_book(title, author, publisher, cover_path, source_url, page_count, isbn, publication_year, status):
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO books
            (title, author, publisher, cover_path, source_url, page_count, isbn, publication_year,
             status, current_page, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)""",
            (
                title,
                author,
                publisher,
                cover_path,
                source_url,
                page_count,
                isbn,
                publication_year,
                status,
                datetime.now().isoformat(),
            ),
        )
        return cursor.lastrowid


def get_books(status=None):
    with get_connection() as connection:
        if status:
            rows = connection.execute(
                "SELECT * FROM books WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM books ORDER BY created_at DESC").fetchall()
        return [_dict(row) for row in rows]


def get_book(book_id):
    with get_connection() as connection:
        return _dict(connection.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone())


def update_book_status(book_id, status):
    if status not in ("Okunacak", "Okunuyor", "Okundu"):
        raise ValueError("Geçersiz raf.")
    with get_connection() as connection:
        finished_at = datetime.now().isoformat() if status == "Okundu" else None
        connection.execute(
            "UPDATE books SET status = ?, finished_at = COALESCE(?, finished_at) WHERE id = ?",
            (status, finished_at, book_id),
        )
        if status == "Okunacak":
            connection.execute("UPDATE books SET finished_at = NULL WHERE id = ?", (book_id,))


def add_reading_log(book_id, pages_read):
    now = datetime.now()
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO reading_logs(book_id, pages_read, logged_at) VALUES (?, ?, ?)",
            (book_id, pages_read, now.isoformat()),
        )
        connection.execute(
            "UPDATE books SET current_page = ? WHERE id = ?", (pages_read, book_id)
        )
        book = connection.execute(
            "SELECT page_count FROM books WHERE id = ?", (book_id,)
        ).fetchone()
        if book and pages_read == book["page_count"]:
            connection.execute(
                "UPDATE books SET status = 'Okundu', finished_at = ? WHERE id = ?",
                (now.isoformat(), book_id),
            )


def get_reading_logs(book_id):
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM reading_logs WHERE book_id = ? ORDER BY logged_at ASC, id ASC",
            (book_id,),
        ).fetchall()
        logs = []
        for row in rows:
            item = _dict(row)
            item["logged_at"] = datetime.fromisoformat(item["logged_at"])
            logs.append(item)
        return logs


def get_reading_log(log_id):
    with get_connection() as connection:
        return _dict(connection.execute("SELECT * FROM reading_logs WHERE id = ?", (log_id,)).fetchone())


def delete_reading_log(log_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM reading_logs WHERE id = ?", (log_id,))


def recalculate_current_page(book_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT pages_read FROM reading_logs WHERE book_id = ? ORDER BY logged_at DESC, id DESC LIMIT 1",
            (book_id,),
        ).fetchone()
        current = row["pages_read"] if row else 0
        connection.execute(
            "UPDATE books SET current_page = ?, status = CASE WHEN status = 'Okundu' THEN 'Okunuyor' ELSE status END WHERE id = ?",
            (current, book_id),
        )


def update_review(book_id, rating, note):
    with get_connection() as connection:
        connection.execute(
            "UPDATE books SET rating = ?, note = ? WHERE id = ?", (rating, note, book_id)
        )


def delete_book(book_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM reading_logs WHERE book_id = ?", (book_id,))
        connection.execute("DELETE FROM books WHERE id = ?", (book_id,))


def count_finished_in_year(year):
    prefix = f"{year}-"
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM books WHERE status = 'Okundu' AND finished_at LIKE ?",
            (prefix + "%",),
        ).fetchone()
        return row["count"]


def monthly_pages(year):
    months = [0] * 12
    prefix = f"{year}-"
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT logged_at, pages_read FROM reading_logs WHERE logged_at LIKE ?",
            (prefix + "%",),
        ).fetchall()
    for row in rows:
        month = int(row["logged_at"][5:7]) - 1
        months[month] += row["pages_read"]
    return months


def reading_streak():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT DISTINCT substr(logged_at, 1, 10) AS day FROM reading_logs ORDER BY day DESC"
        ).fetchall()
    days = [datetime.strptime(row["day"], "%Y-%m-%d").date() for row in rows]
    if not days:
        return 0
    streak = 0
    expected = datetime.now().date()
    for day in days:
        if day == expected or day == expected - __import__("datetime").timedelta(days=1):
            streak += 1
            expected = day - __import__("datetime").timedelta(days=1)
        else:
            break
    return streak


def get_setting_int(key, default):
    with get_connection() as connection:
        row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return default


def set_setting(key, value):
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def download_cover(url):
    if not url:
        return "/static/kapaklar/default.svg"
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        extension = ".jpg"
        if "png" in content_type:
            extension = ".png"
        elif "webp" in content_type:
            extension = ".webp"
        name = f"{abs(hash(url))}{extension}"
        (COVER_DIR / name).write_bytes(response.content)
        return f"/static/kapaklar/{name}"
    except Exception:
        return "/static/kapaklar/default.svg"


def save_cover_file(upload):
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    extension = Path(upload.filename).suffix.lower() or ".jpg"
    if extension not in (".jpg", ".jpeg", ".png", ".webp"):
        extension = ".jpg"
    name = f"{abs(hash(upload.filename + datetime.now().isoformat()))}{extension}"
    upload.save(COVER_DIR / name)
    return f"/static/kapaklar/{name}"
