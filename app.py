import os
import tempfile
import uuid
from decimal import Decimal
from datetime import datetime, timedelta

import mysql.connector
import streamlit as st
from mysql.connector import Error, IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

st.set_page_config(page_title="CineBook", page_icon="🎬", layout="wide")

def setting(name, default=""):
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "DB_SSL_CA"]
missing = [key for key in required if not setting(key)]
if missing:
    st.error("Missing Streamlit Secrets: " + ", ".join(missing))
    st.stop()

ca_value = str(setting("DB_SSL_CA")).strip()
if "-----BEGIN CERTIFICATE-----" not in ca_value:
    st.error("DB_SSL_CA must contain the complete PEM certificate, not a file path.")
    st.stop()

_ca_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False, encoding="utf-8")
_ca_file.write(ca_value + "\\n")
_ca_file.flush()
_ca_file.close()

DB = {
    "host": str(setting("DB_HOST")).strip(),
    "port": int(setting("DB_PORT")),
    "user": str(setting("DB_USER")).strip(),
    "password": str(setting("DB_PASSWORD")),
    "database": str(setting("DB_NAME")).strip(),
    "connection_timeout": 20,
    "ssl_ca": _ca_file.name,
    "ssl_verify_cert": True,
    "ssl_verify_identity": True,
}

def connect():
    return mysql.connector.connect(**DB)

def fetch_all(sql, params=()):
    conn = connect()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()

def fetch_one(sql, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None

def execute(sql, params=()):
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def logged_in():
    return bool(st.session_state.get("user"))

def is_admin():
    return logged_in() and st.session_state.user.get("role") == "admin"

def login_panel():
    st.subheader("Welcome to CineBook")
    login_tab, register_tab = st.tabs(["Login", "Create account"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email").strip().lower()
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            try:
                user = fetch_one("SELECT user_id,name,email,password_hash,role,status FROM users WHERE email=%s", (email,))
                if user and user["status"] == "Active" and check_password_hash(user["password_hash"], password):
                    st.session_state.user = {k: user[k] for k in ("user_id","name","email","role")}
                    st.success("Login successful.")
                    st.rerun()
                else:
                    st.error("Incorrect email/password or inactive account.")
            except Error as e:
                st.error(f"Database error: {e}")
    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Full name")
            email = st.text_input("Email address").strip().lower()
            password = st.text_input("Password (minimum 8 characters)", type="password")
            confirm = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create account", use_container_width=True)
        if submitted:
            if not name.strip() or "@" not in email or len(password) < 8:
                st.error("Enter a name, valid email and password of at least 8 characters.")
            elif password != confirm:
                st.error("Passwords do not match.")
            else:
                try:
                    execute("INSERT INTO users (name,email,password_hash,role) VALUES (%s,%s,%s,'user')",
                            (name.strip(), email, generate_password_hash(password)))
                    st.success("Account created. Please log in.")
                except IntegrityError:
                    st.error("An account with this email already exists.")
                except Error as e:
                    st.error(f"Could not create account: {e}")

def movie_catalogue():
    st.header("Now showing")
    movies = fetch_all("SELECT * FROM movies WHERE status='Active' ORDER BY movie_id DESC")
    if not movies:
        st.info("No active movies are available yet.")
        return
    cols = st.columns(3)
    for i, movie in enumerate(movies):
        with cols[i % 3]:
            if movie.get("poster_url"):
                st.image(movie["poster_url"], use_container_width=True)
            st.subheader(movie["title"])
            st.caption(f'{movie.get("genre") or "Movie"} • {movie.get("language") or "Language not listed"} • {movie.get("duration_minutes") or "?"} min')
            if movie.get("description"):
                st.write(movie["description"])
            if st.button("View shows", key=f'movie_{movie["movie_id"]}', use_container_width=True):
                st.session_state.selected_movie = movie["movie_id"]
                st.session_state.page = "Shows"
                st.rerun()

def show_list():
    movie_id = st.session_state.get("selected_movie")
    if movie_id:
        movie = fetch_one("SELECT * FROM movies WHERE movie_id=%s AND status='Active'", (movie_id,))
        if not movie:
            st.error("Movie not found.")
            return
        st.header(f'Showtimes: {movie["title"]}')
        shows = fetch_all("""
            SELECT sh.show_id,sh.start_time,sh.end_time,sh.base_price,
                   sc.screen_name,th.name AS theatre_name,th.location,
                   (SELECT COUNT(*) FROM seats s WHERE s.screen_id=sc.screen_id) AS total_seats,
                   (SELECT COUNT(*) FROM booking_seats bs WHERE bs.show_id=sh.show_id
                    AND bs.allocation_status IN ('Held','Booked')) AS booked_seats
            FROM shows sh JOIN screens sc ON sc.screen_id=sh.screen_id
            JOIN theatres th ON th.theatre_id=sc.theatre_id
            WHERE sh.movie_id=%s AND sh.status='Scheduled' AND sh.start_time>NOW()
            ORDER BY sh.start_time
        """, (movie_id,))
        if not shows:
            st.info("No upcoming shows.")
        for show in shows:
            available = int(show["total_seats"] or 0) - int(show["booked_seats"] or 0)
            with st.container(border=True):
                st.write(f'**{show["theatre_name"]} — {show["screen_name"]}**')
                st.write(f'{show["location"] or ""}  •  {show["start_time"]}')
                st.write(f'₹{show["base_price"]} per seat  •  {available} seats available')
                if st.button("Choose seats", key=f'show_{show["show_id"]}'):
                    st.session_state.selected_show = show["show_id"]
                    st.session_state.page = "Seats"
                    st.rerun()
        if st.button("Back to movies"):
            st.session_state.page = "Movies"
            st.rerun()
    else:
        st.info("Choose a movie from the Movies page.")

def seat_booking():
    show_id = st.session_state.get("selected_show")
    show = fetch_one("""
        SELECT sh.*,m.title,sc.screen_id,sc.screen_name,th.name AS theatre_name,th.location
        FROM shows sh JOIN movies m ON m.movie_id=sh.movie_id
        JOIN screens sc ON sc.screen_id=sh.screen_id
        JOIN theatres th ON th.theatre_id=sc.theatre_id
        WHERE sh.show_id=%s AND sh.status='Scheduled'
    """, (show_id,))
    if not show:
        st.error("Show not found or no longer scheduled.")
        return
    st.header("Select your seats")
    st.write(f'**{show["title"]}** — {show["theatre_name"]}, {show["screen_name"]}')
    st.caption(f'{show["start_time"]} • ₹{show["base_price"]} per seat')
    seats = fetch_all("""
        SELECT s.seat_id,s.row_label,s.seat_number,s.seat_type,
               IF(bs.seat_id IS NULL,0,1) AS is_booked
        FROM seats s LEFT JOIN booking_seats bs
          ON bs.seat_id=s.seat_id AND bs.show_id=%s
          AND bs.allocation_status IN ('Held','Booked')
        WHERE s.screen_id=%s ORDER BY s.row_label,s.seat_number
    """, (show_id, show["screen_id"]))
    if not seats:
        st.warning("No seats configured for this screen.")
        return
    options = {f'{s["row_label"]}{s["seat_number"]} ({s["seat_type"]})': s["seat_id"] for s in seats if not s["is_booked"]}
    occupied = sum(int(s["is_booked"]) for s in seats)
    st.caption(f'{len(options)} available • {occupied} booked')
    if not options:
        st.warning("This show is sold out.")
        return
    selected_labels = st.multiselect("Available seats", list(options.keys()))
    total = Decimal(str(show["base_price"])) * len(selected_labels)
    st.write(f"**Total: ₹{total:.2f}**")
    if st.button("Confirm booking", type="primary", disabled=not selected_labels):
        if not logged_in():
            st.warning("Please log in first.")
            return
        seat_ids = sorted(options[x] for x in selected_labels)
        conn = connect()
        try:
            conn.start_transaction()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT show_id,screen_id,base_price FROM shows WHERE show_id=%s AND status='Scheduled' FOR UPDATE", (show_id,))
            locked_show = cur.fetchone()
            if not locked_show:
                raise ValueError("This show is no longer available.")
            marks = ",".join(["%s"] * len(seat_ids))
            cur.execute(f"SELECT seat_id FROM seats WHERE screen_id=%s AND seat_id IN ({marks}) ORDER BY seat_id FOR UPDATE",
                        tuple([locked_show["screen_id"]] + seat_ids))
            valid = cur.fetchall()
            if len(valid) != len(seat_ids):
                raise ValueError("One or more seats do not belong to this screen.")
            cur.execute(f"SELECT seat_id FROM booking_seats WHERE show_id=%s AND seat_id IN ({marks}) AND allocation_status IN ('Held','Booked') FOR UPDATE",
                        tuple([show_id] + seat_ids))
            if cur.fetchall():
                raise ValueError("A selected seat was just booked. Refresh and choose again.")
            price = Decimal(str(locked_show["base_price"]))
            ref = "CB" + uuid.uuid4().hex[:12].upper()
            cur.execute("INSERT INTO bookings (booking_reference,user_id,show_id,total_amount,status) VALUES (%s,%s,%s,%s,'Confirmed')",
                        (ref, st.session_state.user["user_id"], show_id, price * len(seat_ids)))
            booking_id = cur.lastrowid
            for sid in seat_ids:
                cur.execute("INSERT INTO booking_seats (booking_id,show_id,seat_id,price,allocation_status) VALUES (%s,%s,%s,%s,'Booked')",
                            (booking_id, show_id, sid, price))
            conn.commit()
            st.success(f"Booking confirmed! Reference: {ref}")
            st.session_state.page = "My bookings"
            st.rerun()
        except (ValueError, IntegrityError) as e:
            conn.rollback()
            st.error(str(e) or "Those seats are no longer available.")
        except Error as e:
            conn.rollback()
            st.error(f"Booking failed: {e}")
        finally:
            conn.close()

def my_bookings():
    st.header("My bookings")
    rows = fetch_all("""
        SELECT b.booking_id,b.booking_reference,b.total_amount,b.status,b.booked_at,
               m.title,sh.start_time,th.name AS theatre_name,sc.screen_name,
               GROUP_CONCAT(CONCAT(s.row_label,s.seat_number) ORDER BY s.row_label,s.seat_number SEPARATOR ', ') AS seat_names
        FROM bookings b JOIN shows sh ON sh.show_id=b.show_id
        JOIN movies m ON m.movie_id=sh.movie_id
        JOIN screens sc ON sc.screen_id=sh.screen_id
        JOIN theatres th ON th.theatre_id=sc.theatre_id
        LEFT JOIN booking_seats bs ON bs.booking_id=b.booking_id
        LEFT JOIN seats s ON s.seat_id=bs.seat_id
        WHERE b.user_id=%s
        GROUP BY b.booking_id,b.booking_reference,b.total_amount,b.status,b.booked_at,
                 m.title,sh.start_time,th.name,sc.screen_name
        ORDER BY b.booked_at DESC
    """, (st.session_state.user["user_id"],))
    if not rows:
        st.info("You haven't booked any tickets yet.")
    for b in rows:
        with st.container(border=True):
            st.subheader(b["title"])
            st.write(f'Reference: **{b["booking_reference"]}**')
            st.write(f'{b["theatre_name"]} • {b["screen_name"]} • {b["start_time"]}')
            st.write(f'Seats: {b["seat_names"] or "—"}')
            st.write(f'Total: ₹{b["total_amount"]} • Status: **{b["status"]}**')
            if b["status"] == "Confirmed" and st.button("Cancel booking", key=f'cancel_{b["booking_id"]}'):
                cancel_booking(b["booking_id"])

def cancel_booking(booking_id):
    conn = connect()
    try:
        conn.start_transaction()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM bookings WHERE booking_id=%s AND user_id=%s FOR UPDATE",
                    (booking_id, st.session_state.user["user_id"]))
        booking = cur.fetchone()
        if not booking or booking["status"] != "Confirmed":
            raise ValueError("This booking cannot be cancelled.")
        cur.execute("UPDATE bookings SET status='Cancelled',cancelled_at=NOW() WHERE booking_id=%s", (booking_id,))
        cur.execute("UPDATE booking_seats SET allocation_status='Released' WHERE booking_id=%s AND allocation_status IN ('Held','Booked')", (booking_id,))
        conn.commit()
        st.success("Booking cancelled. Seats are available again.")
        st.rerun()
    except (ValueError, Error) as e:
        conn.rollback()
        st.error(str(e))
    finally:
        conn.close()

def admin_panel():
    if not is_admin():
        st.error("Administrator access required.")
        return
    st.header("Admin dashboard")
    movies_tab, shows_tab, overview_tab = st.tabs(["Add movie", "Schedule show", "Current data"])
    with movies_tab:
        with st.form("add_movie"):
            title = st.text_input("Movie title")
            genre = st.text_input("Genre")
            language = st.text_input("Language")
            duration = st.number_input("Duration (minutes)", min_value=1, step=1)
            description = st.text_area("Description")
            poster = st.text_input("Poster image URL")
            submit = st.form_submit_button("Add movie")
        if submit:
            try:
                execute("INSERT INTO movies (title,genre,language,duration_minutes,description,poster_url,status) VALUES (%s,%s,%s,%s,%s,%s,'Active')",
                        (title.strip(),genre.strip(),language.strip(),int(duration),description.strip(),poster.strip()))
                st.success("Movie added.")
                st.rerun()
            except Error as e:
                st.error(f"Could not add movie: {e}")
    with shows_tab:
        movies = fetch_all("SELECT movie_id,title,duration_minutes FROM movies WHERE status='Active' ORDER BY title")
        screens = fetch_all("SELECT sc.screen_id,sc.screen_name,th.name FROM screens sc JOIN theatres th ON th.theatre_id=sc.theatre_id ORDER BY th.name,sc.screen_name")
        if not movies or not screens:
            st.info("Add an active movie and configure a screen before scheduling.")
        else:
            with st.form("add_show"):
                movie_map = {f'{m["title"]} (ID {m["movie_id"]})':m for m in movies}
                screen_map = {f'{s["name"]} — {s["screen_name"]} (ID {s["screen_id"]})':s for s in screens}
                movie_label = st.selectbox("Movie", list(movie_map))
                screen_label = st.selectbox("Screen", list(screen_map))
                start = st.datetime_input("Start time", value=datetime.now()+timedelta(days=1))
                price = st.number_input("Ticket price (₹)", min_value=0.0, value=200.0, step=10.0)
                submit = st.form_submit_button("Schedule show")
            if submit:
                m = movie_map[movie_label]
                s = screen_map[screen_label]
                end = start + timedelta(minutes=int(m["duration_minutes"])+20)
                try:
                    execute("INSERT INTO shows (movie_id,screen_id,start_time,end_time,status,base_price) VALUES (%s,%s,%s,%s,'Scheduled',%s)",
                            (m["movie_id"],s["screen_id"],start,end,Decimal(str(price))))
                    st.success("Show scheduled.")
                    st.rerun()
                except Error as e:
                    st.error(f"Could not schedule show: {e}")
    with overview_tab:
        st.subheader("Movies")
        st.dataframe(fetch_all("SELECT movie_id,title,genre,language,duration_minutes,status FROM movies ORDER BY movie_id DESC"), use_container_width=True)
        st.subheader("Upcoming and recent shows")
        st.dataframe(fetch_all("""SELECT sh.show_id,m.title,th.name AS theatre,sc.screen_name,sh.start_time,sh.status,sh.base_price
                                  FROM shows sh JOIN movies m ON m.movie_id=sh.movie_id
                                  JOIN screens sc ON sc.screen_id=sh.screen_id
                                  JOIN theatres th ON th.theatre_id=sc.theatre_id
                                  ORDER BY sh.start_time DESC LIMIT 100"""), use_container_width=True)

def main():
    st.title("🎬 CineBook")
    st.caption("Your movie. Your seats. Your show.")
    if logged_in():
        st.sidebar.success(f'Logged in: {st.session_state.user["name"]}')
        pages = ["Movies", "Shows", "Seats", "My bookings"]
        if is_admin():
            pages.append("Admin")
        page = st.sidebar.radio("Navigation", pages, index=pages.index(st.session_state.get("page","Movies")) if st.session_state.get("page","Movies") in pages else 0)
        st.session_state.page = page
        if st.sidebar.button("Logout"):
            del st.session_state.user
            st.session_state.page = "Movies"
            st.rerun()
        try:
            if page == "Movies": movie_catalogue()
            elif page == "Shows": show_list()
            elif page == "Seats": seat_booking()
            elif page == "My bookings": my_bookings()
            elif page == "Admin": admin_panel()
        except Error as e:
            st.error(f"Database connection/query failed: {e}")
            st.info("Check the database host, credentials, SSL settings and that the movie_booking schema is imported.")
    else:
        st.sidebar.info("Log in or create an account to book tickets.")
        login_panel()
        st.divider()
        try:
            movie_catalogue()
        except Error as e:
            st.error(f"Could not load movies: {e}")

if __name__ == "__main__":
    main()
