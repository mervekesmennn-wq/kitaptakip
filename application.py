import os
from datetime import date, datetime, timedelta
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for

import db
import scraper


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "gelistirilebilir-gelistirme-anahtari")

with app.app_context():
    db.init_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def validate_page_update(total_pages, previous_page, new_page):
    if not isinstance(total_pages, int) or total_pages <= 0:
        raise ValueError("Sayfa sayısı 0'dan büyük olmalıdır.")
    if not isinstance(new_page, int) or new_page < 0:
        raise ValueError("Okunan sayfa 0 veya daha büyük olmalıdır.")
    if new_page > total_pages:
        raise ValueError("Okunan sayfa toplam sayfadan büyük olamaz.")
    if new_page < previous_page:
        raise ValueError("Okunan sayfa önceki kayıttan küçük olamaz.")
    return True


def estimate_finish_days(logs, total_pages, current_page):
    if not logs or total_pages <= current_page:
        return 0
    cutoff = datetime.now() - timedelta(days=7)
    recent = [log for log in logs if log["logged_at"] >= cutoff]
    if not recent:
        recent = list(logs[-7:])
    if len(recent) == 1:
        return max(1, (total_pages - current_page) // max(recent[0]["pages_read"], 1))
    previous = 0
    if logs.index(recent[0]) > 0:
        previous = logs[logs.index(recent[0]) - 1]["pages_read"]
    total = (recent[-1]["pages_read"] - previous)
    days = max(1, (recent[-1]["logged_at"] - recent[0]["logged_at"]).days)
    daily_speed = max(1, total // days)
    return max(1, (total_pages - current_page + daily_speed - 1) // daily_speed)


def goal_status(books_read, annual_goal):
    remaining = max(0, annual_goal - books_read)
    if remaining == 0:
        message = f"Bu yıl {books_read}/{annual_goal}, hedefini tamamladın"
    elif books_read < annual_goal:
        message = f"Bu yıl {books_read}/{annual_goal}, hedefinin {remaining} kitabı gerisindesin"
    else:
        message = f"Bu yıl {books_read}/{annual_goal}, hedefini geçtin"
    return {"read": books_read, "goal": annual_goal, "remaining": remaining, "message": message}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == "test" and request.form.get("password") == "123":
            session["logged_in"] = True
            return redirect(url_for("library"))
        flash("Kullanıcı adı veya şifre hatalı.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def library():
    selected_status = request.args.get("raf", "Okunuyor")
    if selected_status not in ("Okunacak", "Okunuyor", "Okundu"):
        selected_status = "Okunuyor"
    books = db.get_books(selected_status)
    return render_template("library.html", books=books, selected_status=selected_status)


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    query = request.args.get("q", "").strip()
    results = []
    source_error = False
    manual_form = False

    if query:
        if request.method == "POST":
            query = request.form.get("q", query).strip()
        try:
            results = scraper.search_books(query)
            if not results:
                manual_form = True
        except Exception:
            source_error = True
            manual_form = True

    if request.method == "POST" and "manual" in request.form:
        return redirect(url_for("add_manual"))
    return render_template(
        "search.html",
        query=query,
        results=results,
        source_error=source_error,
        manual_form=manual_form,
    )


@app.route("/add/manual", methods=["GET", "POST"])
@login_required
def add_manual():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        publisher = request.form.get("publisher", "").strip()
        isbn = request.form.get("isbn", "").strip()
        status = request.form.get("status", "Okunacak")
        try:
            page_count = int(request.form.get("page_count", 0))
        except (TypeError, ValueError):
            page_count = 0
        if not title or page_count <= 0:
            flash("Kitap adı ve 0'dan büyük sayfa sayısı gereklidir.", "danger")
            return render_template("manual.html")
        if db.book_exists(title, isbn):
            flash("Bu kitap zaten ekli.", "warning")
            return redirect(url_for("library"))
        cover_path = "/static/kapaklar/default.svg"
        cover_url = request.files.get("cover")
        if cover_url and cover_url.filename:
            cover_path = db.save_cover_file(cover_url)
        publication_year = request.form.get("publication_year", "").strip()
        db.add_book(
            title=title,
            author=author,
            publisher=publisher,
            cover_path=cover_path,
            source_url="",
            page_count=page_count,
            isbn=isbn,
            publication_year=publication_year,
            status=status,
        )
        flash("Kitap rafına ekledi.", "success")
        return redirect(url_for("library"))
    return render_template("manual.html")


@app.route("/add/search", methods=["POST"])
@login_required
def add_search():
    title = request.form["title"]
    if db.book_exists(title, request.form.get("isbn", "")):
        flash("Bu kitap zaten ekli.", "warning")
        return redirect(url_for("library"))
    status = request.form["status"]
    try:
        details = scraper.get_book_details(request.form["source_url"])
    except Exception:
        details = {}
    page_count = details.get("page_count") or 0
    try:
        page_count = int(page_count)
    except (TypeError, ValueError):
        page_count = 0
    if page_count <= 0:
        page_count = 0
    cover_path = db.download_cover(details.get("cover_url") or request.form.get("cover_url"))
    db.add_book(
        title=title,
        author=request.form.get("author", ""),
        publisher=request.form.get("publisher", ""),
        cover_path=cover_path,
        source_url=request.form["source_url"],
        page_count=page_count,
        isbn=details.get("isbn") or request.form.get("isbn", ""),
        publication_year=details.get("publication_year") or "",
        status=status,
    )
    flash("Kitap rafına ekledi.", "success")
    return redirect(url_for("library"))


@app.route("/book/<int:book_id>", methods=["GET", "POST"])
@login_required
def book_detail(book_id):
    book = db.get_book(book_id)
    if not book:
        return redirect(url_for("library"))
    if request.method == "POST":
        action = request.form.get("action")
        if action == "status":
            db.update_book_status(book_id, request.form["status"])
            flash("Raf güncellendi.", "success")
        elif action == "progress":
            try:
                new_page = int(request.form["pages"])
                validate_page_update(book["page_count"], book["current_page"], new_page)
                db.add_reading_log(book_id, new_page)
                if new_page == book["page_count"]:
                    db.update_book_status(book_id, "Okundu")
                elif book["status"] == "Okunacak":
                    db.update_book_status(book_id, "Okunuyor")
                flash("Bugünkü okuma kaydı eklendi.", "success")
            except ValueError as exc:
                flash(str(exc), "danger")
        elif action == "review":
            try:
                rating = int(request.form.get("rating", 0))
                if rating not in range(0, 6):
                    raise ValueError
            except (TypeError, ValueError):
                rating = 0
            db.update_review(book_id, rating, request.form.get("note", "").strip())
            flash("Puan ve not güncellendi.", "success")
        elif action == "delete":
            db.delete_book(book_id)
            flash("Kitap silindi.", "success")
            return redirect(url_for("library"))
        return redirect(url_for("book_detail", book_id=book_id))
    logs = db.get_reading_logs(book_id)
    finish_days = estimate_finish_days(logs, book["page_count"], book["current_page"])
    return render_template("book.html", book=book, logs=logs, finish_days=finish_days)


@app.route("/log/<int:log_id>/delete", methods=["POST"])
@login_required
def delete_log(log_id):
    log = db.get_reading_log(log_id)
    if log:
        db.delete_reading_log(log_id)
        db.recalculate_current_page(log["book_id"])
    return redirect(request.referrer or url_for("library"))


@app.route("/stats")
@login_required
def stats():
    goal = db.get_setting_int("annual_goal", 24)
    year = datetime.now().year
    read_count = db.count_finished_in_year(year)
    status = goal_status(read_count, goal)
    monthly = db.monthly_pages(year)
    streak = db.reading_streak()
    return render_template("stats.html", goal_status=status, monthly=monthly, streak=streak, year=year)


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        try:
            goal = int(request.form["annual_goal"])
            if goal <= 0:
                raise ValueError
            db.set_setting("annual_goal", str(goal))
            flash("Yıllık hedef güncellendi.", "success")
        except (KeyError, ValueError):
            flash("Yıllık hedef pozitif bir sayı olmalıdır.", "danger")
        return redirect(url_for("settings"))
    goal = db.get_setting_int("annual_goal", 24)
    return render_template("settings.html", goal=goal)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010, debug=True)
