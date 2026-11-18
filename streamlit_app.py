import os, uuid, tempfile
from datetime import datetime, timedelta
from decimal import Decimal
import mysql.connector
from mysql.connector import Error, IntegrityError
import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash

st.set_page_config(page_title="CineBook", page_icon="🎬", layout="wide")

def cfg(k, d=None):
    try:
        v = st.secrets.get(k)
        if v not in (None, ""): return v
    except Exception: pass
    return os.getenv(k, d)

required = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "DB_SSL_CA"]
missing = [key for key in required if not cfg(key)]
if missing:
    st.error("Missing Streamlit Secrets: " + ", ".join(missing))
    st.stop()

ca_value = str(cfg("DB_SSL_CA")).strip()
if "-----BEGIN CERTIFICATE-----" not in ca_value:
    st.error("DB_SSL_CA must contain the complete PEM certificate, not a file path.")
    st.stop()

_ca_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False, encoding="utf-8")
_ca_file.write(ca_value + "\n")
_ca_file.flush()
_ca_file.close()

DB = dict(
    host=str(cfg("DB_HOST")).strip(),
    port=int(cfg("DB_PORT")),
    user=str(cfg("DB_USER")).strip(),
    password=str(cfg("DB_PASSWORD")),
    database=str(cfg("DB_NAME")).strip(),
    connection_timeout=20,
    ssl_ca=_ca_file.name,
    ssl_verify_cert=True,
    ssl_verify_identity=True,
)

st.markdown("""
<style>
.stApp{background:#0c1018;color:#f4f5f7}.block-container{max-width:1250px;padding-top:1.5rem}
.hero{padding:2.2rem;border-radius:22px;background:linear-gradient(120deg,#171d2b,#29203a);border:1px solid #343b4d}
.eyebrow{color:#f4b860;letter-spacing:.18em;font-size:.75rem;font-weight:700}
div[data-testid="stMetric"]{background:#171e2a;border:1px solid #30394a;padding:12px;border-radius:12px}
</style>""", unsafe_allow_html=True)

def db():
    return mysql.connector.connect(**DB)
def all_rows(sql, p=()):
    c=db()
    try:
        q=c.cursor(dictionary=True); q.execute(sql,p); return q.fetchall()
    finally: c.close()
def one(sql,p=()):
    r=all_rows(sql,p); return r[0] if r else None
def write(sql,p=()):
    c=db()
    try:
        q=c.cursor(); q.execute(sql,p); c.commit(); return q.lastrowid
    except Exception:
        c.rollback(); raise
    finally: c.close()
def cash(v): return f"₹{Decimal(str(v or 0)):,.2f}"

for k,v in {"user":None,"page":"Home","movie":None,"show":None}.items():
    if k not in st.session_state: st.session_state[k]=v

def logout():
    st.session_state.user=None; st.session_state.page="Home"; st.rerun()

with st.sidebar:
    st.title("🎬 CineBook"); st.caption("YOUR CINEMA, YOUR SEAT")
    if st.session_state.user:
        st.success(st.session_state.user["name"])
        nav=["Home"] + (["Movie"] if st.session_state.movie else []) + (["Seats"] if st.session_state.show else []) + ["My Bookings"] + (["Admin"] if st.session_state.user["role"]=="admin" else []) + ["Logout"]
    else: nav=["Home"]
    n=st.radio("Navigation",nav,index=nav.index(st.session_state.page) if st.session_state.page in nav else 0)
    if st.session_state.page in nav:
        if n=="Logout": logout()
        else: st.session_state.page=n

st.markdown('<div class="eyebrow">TEAM 09 · MOVIE TICKET BOOKING</div>',unsafe_allow_html=True)
st.title("CineBook")
try: one("SELECT 1")
except Error as e:
    st.error("Database connection failed. Check your Streamlit Secrets.")
    st.code(str(e)); st.stop()

def auth():
    a,b=st.tabs(["Sign in","Create account"])
    with a:
        with st.form("login"):
            email=st.text_input("Email").strip().lower()
            pw=st.text_input("Password",type="password")
            go=st.form_submit_button("Sign in",use_container_width=True)
        if go:
            u=one("SELECT * FROM users WHERE email=%s",(email,))
            if u and u.get("status")=="Active" and check_password_hash(u["password_hash"],pw):
                st.session_state.user={k:u[k] for k in ("user_id","name","role")}
                st.session_state.page="Home"; st.rerun()
            else: st.error("Incorrect login or inactive account.")
    with b:
        with st.form("register"):
            name=st.text_input("Full name")
            email=st.text_input("Email address").strip().lower()
            pw=st.text_input("Password (8+ characters)",type="password")
            confirm=st.text_input("Confirm password",type="password")
            go=st.form_submit_button("Create account",use_container_width=True)
        if go:
            if not name.strip() or not email or len(pw)<8 or pw!=confirm: st.error("Check your name, email and matching password (8+ characters).")
            else:
                try:
                    write("INSERT INTO users(name,email,password_hash,role) VALUES(%s,%s,%s,'user')",(name.strip(),email,generate_password_hash(pw)))
                    st.success("Account created. Sign in now.")
                except IntegrityError: st.error("That email is already registered.")
                except Error as e: st.error(str(e))

def home():
    st.markdown('<div class="hero"><div class="eyebrow">YOUR CINEMA, YOUR SEAT</div><h1>Big stories.<br><span style="color:#f4b860">Better seats.</span></h1><p>Discover movies, choose your showtime and book your favourite seats.</p></div>',unsafe_allow_html=True)
    st.subheader("Now showing")
    movies=all_rows("SELECT * FROM movies WHERE status='Active' ORDER BY movie_id DESC")
    if not movies: st.info("No active movies. Ask an administrator to add movies.")
    cols=st.columns(3)
    for i,m in enumerate(movies):
        with cols[i%3], st.container(border=True):
            if m.get("poster_url"): st.image(m["poster_url"],use_container_width=True)
            st.subheader(m["title"]); st.caption(f"{m.get('genre') or 'Movie'} · {m.get('language') or 'Various'} · {m['duration_minutes']} min")
            st.write((m.get("description") or "")[:180])
            if st.button("View showtimes",key=f"m{m['movie_id']}",use_container_width=True):
                st.session_state.movie=m["movie_id"]; st.session_state.page="Movie"; st.rerun()

def movie_page(mid):
    m=one("SELECT * FROM movies WHERE movie_id=%s AND status='Active'",(mid,))
    if not m: st.error("Movie not found."); return
    if st.button("← All movies"): st.session_state.page="Home"; st.rerun()
    x,y=st.columns([1,2])
    with x:
        if m.get("poster_url"): st.image(m["poster_url"],use_container_width=True)
    with y:
        st.header(m["title"]); st.write(f"{m.get('genre') or ''} · {m.get('language') or ''} · {m['duration_minutes']} min"); st.write(m.get("description") or "")
    shows=all_rows("""
      SELECT sh.show_id,sh.start_time,sh.end_time,sh.base_price,sc.screen_id,sc.screen_name,
      th.name theatre_name,th.location,
      (SELECT COUNT(*) FROM seats s WHERE s.screen_id=sc.screen_id) total_seats,
      (SELECT COUNT(*) FROM booking_seats bs WHERE bs.show_id=sh.show_id AND bs.allocation_status IN ('Held','Booked')) booked_seats
      FROM shows sh JOIN screens sc ON sc.screen_id=sh.screen_id JOIN theatres th ON th.theatre_id=sc.theatre_id
      WHERE sh.movie_id=%s AND sh.status='Scheduled' AND sh.start_time>NOW() ORDER BY sh.start_time
    """,(mid,))
    st.subheader("Available showtimes")
    if not shows: st.info("No upcoming shows available.")
    for s in shows:
        with st.container(border=True):
            a,b,c=st.columns([3,2,1]); a.markdown(f"**{s['theatre_name']}**"); a.caption(f"{s['location']} · {s['screen_name']}")
            b.write(s["start_time"].strftime("%a, %d %b %Y · %I:%M %p")); b.caption(cash(s["base_price"]))
            c.metric("Seats left",max(0,s["total_seats"]-s["booked_seats"]))
            if c.button("Select seats",key=f"s{s['show_id']}"):
                st.session_state.show=s["show_id"]; st.session_state.page="Seats"; st.rerun()

def book(show_id, ids):
    conn=db()
    try:
        conn.start_transaction(); q=conn.cursor(dictionary=True)
        q.execute("SELECT show_id,screen_id,base_price FROM shows WHERE show_id=%s AND status='Scheduled' FOR UPDATE",(show_id,))
        sh=q.fetchone()
        if not sh: raise ValueError("Show is no longer available.")
        ids=sorted(set(map(int,ids)))
        if not ids: raise ValueError("Select at least one seat.")
        marks=",".join(["%s"]*len(ids))
        q.execute(f"SELECT seat_id FROM seats WHERE screen_id=%s AND seat_id IN ({marks}) ORDER BY seat_id FOR UPDATE",tuple([sh["screen_id"]]+ids))
        seats=q.fetchall()
        if len(seats)!=len(ids): raise ValueError("Invalid seat selection.")
        q.execute(f"SELECT seat_id FROM booking_seats WHERE show_id=%s AND seat_id IN ({marks}) AND allocation_status IN ('Held','Booked') FOR UPDATE",tuple([show_id]+ids))
        if q.fetchall(): raise ValueError("A selected seat was just booked. Refresh and try again.")
        price=Decimal(str(sh["base_price"])); ref="CB"+uuid.uuid4().hex[:12].upper()
        q.execute("INSERT INTO bookings(booking_reference,user_id,show_id,total_amount,status) VALUES(%s,%s,%s,%s,'Confirmed')",(ref,st.session_state.user["user_id"],show_id,price*len(seats)))
        bid=q.lastrowid
        for seat in seats:
            q.execute("INSERT INTO booking_seats(booking_id,show_id,seat_id,price,allocation_status) VALUES(%s,%s,%s,%s,'Booked')",(bid,show_id,seat["seat_id"],price))
        conn.commit(); st.success(f"Booking confirmed! Reference: {ref}"); st.balloons()
    except (ValueError,IntegrityError,Error) as e:
        conn.rollback(); st.error(str(e))
    finally: conn.close()

def seats_page(sid):
    if not st.session_state.user: st.warning("Sign in to book seats."); auth(); return
    sh=one("""SELECT sh.*,m.title,sc.screen_id,sc.screen_name,th.name theatre_name,th.location
      FROM shows sh JOIN movies m ON m.movie_id=sh.movie_id JOIN screens sc ON sc.screen_id=sh.screen_id
      JOIN theatres th ON th.theatre_id=sc.theatre_id WHERE sh.show_id=%s AND sh.status='Scheduled'""",(sid,))
    if not sh: st.error("Show unavailable."); return
    if st.button("← Back to movie"): st.session_state.page="Movie"; st.rerun()
    st.subheader(sh["title"]); st.caption(f"{sh['theatre_name']} · {sh['screen_name']} · {sh['start_time']}")
    st.markdown("### Screen this way")
    seats=all_rows("""SELECT s.seat_id,s.row_label,s.seat_number,s.seat_type,%s price,
      IF(bs.seat_id IS NULL,0,1) is_booked FROM seats s LEFT JOIN booking_seats bs
      ON bs.seat_id=s.seat_id AND bs.show_id=%s AND bs.allocation_status IN ('Held','Booked')
      WHERE s.screen_id=%s ORDER BY s.row_label,s.seat_number""",(sh["base_price"],sid,sh["screen_id"]))
    chosen=[]
    for row in sorted(set(z["row_label"] for z in seats)):
        st.write(f"**Row {row}**"); rs=[z for z in seats if z["row_label"]==row]; cs=st.columns(len(rs))
        for col,z in zip(cs,rs):
            with col:
                v=st.checkbox(f"{z['seat_number']} · {'Booked' if z['is_booked'] else cash(z['price'])}",key=f"seat{sid}_{z['seat_id']}",disabled=bool(z["is_booked"]))
                if v: chosen.append(z["seat_id"])
    st.write(f"Selected {len(chosen)} · Total **{cash(Decimal(str(sh['base_price']))*len(chosen))}**")
    if st.button("Confirm booking",type="primary",disabled=not chosen,use_container_width=True): book(sid,chosen)

def bookings_page():
    if not st.session_state.user: st.info("Sign in to view bookings."); auth(); return
    rows=all_rows("""SELECT b.booking_id,b.booking_reference,b.total_amount,b.status,b.booked_at,m.title,sh.start_time,
      th.name theatre_name,sc.screen_name,GROUP_CONCAT(CONCAT(s.row_label,s.seat_number) ORDER BY s.row_label,s.seat_number SEPARATOR ', ') seat_names
      FROM bookings b JOIN shows sh ON sh.show_id=b.show_id JOIN movies m ON m.movie_id=sh.movie_id
      JOIN screens sc ON sc.screen_id=sh.screen_id JOIN theatres th ON th.theatre_id=sc.theatre_id
      LEFT JOIN booking_seats bs ON bs.booking_id=b.booking_id LEFT JOIN seats s ON s.seat_id=bs.seat_id
      WHERE b.user_id=%s GROUP BY b.booking_id,b.booking_reference,b.total_amount,b.status,b.booked_at,m.title,sh.start_time,th.name,sc.screen_name
      ORDER BY b.booked_at DESC""",(st.session_state.user["user_id"],))
    st.subheader("My bookings")
    if not rows: st.info("No bookings yet.")
    for r in rows:
        with st.container(border=True):
            a,b,c=st.columns([3,2,1]); a.subheader(r["title"]); a.write(f"{r['theatre_name']} · {r['screen_name']}")
            a.caption(f"{r['start_time']} · Seats: {r['seat_names'] or '—'} · {r['booking_reference']}")
            b.metric("Total",cash(r["total_amount"])); b.write(f"Status: {r['status']}")
            if r["status"]=="Confirmed" and c.button("Cancel",key=f"cancel{r['booking_id']}"):
                cancel(r["booking_id"]); st.rerun()

def cancel(bid):
    c=db()
    try:
        c.start_transaction(); q=c.cursor(dictionary=True)
        q.execute("SELECT * FROM bookings WHERE booking_id=%s AND user_id=%s FOR UPDATE",(bid,st.session_state.user["user_id"]))
        r=q.fetchone()
        if not r or r["status"]!="Confirmed": raise ValueError("Booking cannot be cancelled.")
        q.execute("UPDATE bookings SET status='Cancelled',cancelled_at=NOW() WHERE booking_id=%s",(bid,))
        q.execute("UPDATE booking_seats SET allocation_status='Released' WHERE booking_id=%s AND allocation_status IN ('Held','Booked')",(bid,))
        c.commit(); st.success("Booking cancelled.")
    except (ValueError,Error) as e: c.rollback(); st.error(str(e))
    finally: c.close()

def admin_page():
    if not st.session_state.user or st.session_state.user["role"]!="admin": st.error("Admin access required."); return
    st.subheader("Administrator dashboard")
    t1,t2,t3=st.tabs(["Add movie","Schedule show","Overview"])
    with t1:
        with st.form("addmovie"):
            title=st.text_input("Movie title"); genre=st.text_input("Genre"); language=st.text_input("Language")
            duration=st.number_input("Duration (minutes)",1,600,120); poster=st.text_input("Poster URL"); desc=st.text_area("Description")
            submit=st.form_submit_button("Add movie")
        if submit:
            try:
                write("INSERT INTO movies(title,genre,language,duration_minutes,description,poster_url,status) VALUES(%s,%s,%s,%s,%s,%s,'Active')",(title.strip(),genre.strip(),language.strip(),int(duration),desc.strip(),poster.strip()))
                st.success("Movie added."); st.rerun()
            except Error as e: st.error(str(e))
    with t2:
        movies=all_rows("SELECT movie_id,title,duration_minutes FROM movies WHERE status='Active' ORDER BY title")
        screens=all_rows("SELECT sc.screen_id,sc.screen_name,th.name theatre_name,th.location FROM screens sc JOIN theatres th ON th.theatre_id=sc.theatre_id ORDER BY th.name,sc.screen_name")
        if not movies or not screens: st.info("Add a movie and configure a screen first.")
        else:
            with st.form("schedule"):
                mm={f"{m['title']} ({m['duration_minutes']} min)":m for m in movies}; ss={f"{s['theatre_name']} — {s['screen_name']}":s for s in screens}
                ml=st.selectbox("Movie",list(mm)); sl=st.selectbox("Screen",list(ss)); day=st.date_input("Date"); tm=st.time_input("Start time")
                price=st.number_input("Ticket price (₹)",0.0,10000.0,200.0,10.0); submit=st.form_submit_button("Schedule show")
            if submit:
                m=mm[ml]; s=ss[sl]; start=datetime.combine(day,tm); end=start+timedelta(minutes=int(m["duration_minutes"])+20)
                conflict=one("SELECT show_id FROM shows WHERE screen_id=%s AND status='Scheduled' AND start_time<%s AND end_time>%s LIMIT 1",(s["screen_id"],end,start))
                if conflict: st.error("Screen already has a show during this time.")
                else:
                    try:
                        write("INSERT INTO shows(movie_id,screen_id,start_time,end_time,status,base_price) VALUES(%s,%s,%s,%s,'Scheduled',%s)",(m["movie_id"],s["screen_id"],start,end,Decimal(str(price))))
                        st.success("Show scheduled."); st.rerun()
                    except Error as e: st.error(str(e))
    with t3:
        a,b,c=st.columns(3); a.metric("Movies",one("SELECT COUNT(*) n FROM movies")["n"]); b.metric("Shows",one("SELECT COUNT(*) n FROM shows")["n"]); c.metric("Bookings",one("SELECT COUNT(*) n FROM bookings")["n"])
        recent=all_rows("SELECT b.booking_reference,b.status,b.total_amount,b.booked_at,u.name,m.title FROM bookings b JOIN users u ON u.user_id=b.user_id JOIN shows sh ON sh.show_id=b.show_id JOIN movies m ON m.movie_id=sh.movie_id ORDER BY b.booked_at DESC LIMIT 20")
        st.dataframe(recent,use_container_width=True,hide_index=True)

p=st.session_state.page
if p=="Home":
    if not st.session_state.user: auth()
    home()
elif p=="Movie": movie_page(st.session_state.movie)
elif p=="Seats": seats_page(st.session_state.show)
elif p=="My Bookings": bookings_page()
elif p=="Admin": admin_page()
