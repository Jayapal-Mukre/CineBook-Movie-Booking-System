CineBook — Streamlit + MySQL

Streamlit adaptation of the CineBook movie-ticket booking system.

Features: registration/login, movie catalogue, showtimes, seat selection, transactional bookings, cancellation, admin movie creation and show scheduling.

Database compatibility: this targets the newer schema used by the latest CineBook Flask app: users.status, movies.status='Active', shows.status='Scheduled' with base_price, bookings.booking_reference and booked_at, and booking_seats.allocation_status values Held/Booked/Released. The older schema.sql from the original ZIP is incompatible. Do not import it over your existing database. Back up and verify the live movie_booking schema first.

Local run: pip install -r requirements.txt; streamlit run streamlit_app.py.

Streamlit Community Cloud settings: repository Jayapal-Mukre/CineBook-Movie-Booking-System; branch main; main file streamlit_app.py. Add DB_HOST, DB_PORT, DB_USER, DB_PASSWORD and DB_NAME in App settings → Secrets. Streamlit Cloud cannot connect to MySQL running only on your laptop's localhost. Use a reachable cloud MySQL service and provider-required TLS settings.

Admin: register an account, then run UPDATE users SET role='admin' WHERE email='your-admin-email@example.com'; in MySQL. The app records demo bookings and does not process real payments. Never commit real secrets; rotate any password previously exposed in source code/chat.
