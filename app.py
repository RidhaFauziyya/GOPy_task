from flask import Flask, redirect, url_for, session, request, render_template, flash
import sqlite3, os
from werkzeug.security import generate_password_hash, check_password_hash
import openmeteo_requests
import pandas as pd
import numpy as np
import requests_cache
from retry_requests import retry
import requests
from models.user import db, User, Quiz
import random
import re

app = Flask(__name__)
app.config["SECRET_KEY"] = "secretkey"
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = \
    'sqlite:///' + os.path.join(BASE_DIR, 'db.sqlite3')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

@app.route("/")
def cuaca():
    city = request.args.get("city", "Surabaya").strip()

    try:
        city_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        city_response = requests.get(city_url, timeout=10)
        city_response.raise_for_status()
        city_response = city_response.json()

        if "results" not in city_response or not city_response["results"]:
            flash("Kota tidak ditemukan.", "error")
            return render_template("home.html", current=None, forecast=[])

        city = city_response["results"][0]
        lat = city["latitude"]
        long = city["longitude"]

        cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
        retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
        openmeteo = openmeteo_requests.Client(session=retry_session)

        responses = openmeteo.weather_api(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": long,
                "daily": [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "rain_sum",
                ],
                "current": [
                    "temperature_2m",
                    "apparent_temperature",
                    "rain",
                    "relative_humidity_2m",
                ],
                "hourly": [
                    "temperature_2m",
                    "apparent_temperature",
                    "weather_code",
                ],
                "timezone": "auto",
                "forecast_days": 3,
            },
        )

        if not responses:
            flash("Data cuaca tidak tersedia.", "error")
            return render_template("home.html", current=None, forecast=[])

        data = responses[0]

        timezone = data.Timezone()
        timezone_2 = data.TimezoneAbbreviation()

        day_indo = {
            "Monday": "Senin",
            "Tuesday": "Selasa",
            "Wednesday": "Rabu",
            "Thursday": "Kamis",
            "Friday": "Jumat",
            "Saturday": "Sabtu",
            "Sunday": "Minggu",
        }

        month_indo = {
            "January": "Januari",
            "February": "Februari",
            "March": "Maret",
            "April": "April",
            "May": "Mei",
            "June": "Juni",
            "July": "Juli",
            "August": "Agustus",
            "September": "September",
            "October": "Oktober",
            "November": "November",
            "December": "Desember",
        }

        current = data.Current()

        current_time = (
            pd.to_datetime(current.Time(), unit="s")
            .tz_localize("UTC")
            .tz_convert("Asia/Jakarta")
        )

        current_data = {
            "time": f"{day_indo[current_time.strftime('%A')]}, {current_time.strftime('%d')} {month_indo[current_time.strftime('%B')]} {current_time.strftime('%Y')}",
            "temperature": round(current.Variables(0).Value()),
            "apparent_temperature": round(current.Variables(1).Value()),
            "current_rain": current.Variables(2).Value(),
            "humidity": round(current.Variables(3).Value(), 1),
            "timezone": timezone,
            "tz_abbr": timezone_2,
            "city": city["name"],
        }

        hourly = data.Hourly()

        hourly_temperature = hourly.Variables(0).ValuesAsNumpy()
        hourly_apparent = hourly.Variables(1).ValuesAsNumpy()
        hourly_weather = hourly.Variables(2).ValuesAsNumpy()

        hourly_dates = pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s")
            .tz_localize("UTC")
            .tz_convert("Asia/Jakarta"),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s")
            .tz_localize("UTC")
            .tz_convert("Asia/Jakarta"),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        )

        mask = hourly_dates.hour.isin([14, 22])

        hourly_df = pd.DataFrame(
            {
                "date": hourly_dates[mask],
                "temperature_2m": np.round(hourly_temperature[mask]).astype(int),
                "apparent_temperature": np.round(hourly_apparent[mask]).astype(int),
                "weather_code": hourly_weather[mask],
            }
        )

        hourly_df["date_only"] = hourly_df["date"].dt.normalize()
        hourly_df["hour"] = hourly_df["date"].dt.hour

        daily = data.Daily()

        daily_dates = pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s")
            .tz_localize("UTC")
            .tz_convert("Asia/Jakarta"),
            end=pd.to_datetime(daily.TimeEnd(), unit="s")
            .tz_localize("UTC")
            .tz_convert("Asia/Jakarta"),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left",
        )

        daily_df = pd.DataFrame(
            {
                "date": [
                    f"{day_indo[d.strftime('%A')]}, {d.strftime('%d')} {month_indo[d.strftime('%B')]} {d.strftime('%Y')}"
                    for d in daily_dates
                ],
                "weather_code": daily.Variables(0).ValuesAsNumpy(),
                "temperature_2m_max": np.round(
                    daily.Variables(1).ValuesAsNumpy()
                ).astype(int),
                "temperature_2m_min": np.round(
                    daily.Variables(2).ValuesAsNumpy()
                ).astype(int),
                "rain_sum": daily.Variables(3).ValuesAsNumpy(),
            }
        )

        daily_df["date_only"] = pd.to_datetime(daily_dates).normalize()

        pivot = hourly_df.pivot(
            index="date_only",
            columns="hour",
            values="temperature_2m",
        )

        pivot = pivot.rename(columns={14: "day_temp", 22: "night_temp"})

        forecast_df = daily_df.merge(
            pivot,
            on="date_only",
            how="left",
        )

        forecast_data = forecast_df[
            [
                "date",
                "date_only",
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "rain_sum",
                "day_temp",
                "night_temp",
            ]
        ].to_dict(orient="records")

        return render_template(
            "home.html",
            current=current_data,
            forecast=forecast_data,
        )

    except requests.exceptions.RequestException:
        flash("Gagal terhubung ke layanan cuaca.", "error")
    except KeyError:
        flash("Format data cuaca tidak sesuai.", "error")
    except Exception as e:
        print(f"Weather Error: {e}")
        flash("Terjadi kesalahan saat mengambil data cuaca.", "error")

    return render_template(
        "home.html",
        current=None,
        forecast=[],
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            if not username or not password:
                flash('Username dan password wajib diisi.', 'error')
                return render_template('auth/login.html')

            user = User.query.filter_by(username=username).first()

            if user and check_password_hash(user.password, password):
                session['user_id'] = user.id
                session['username'] = user.username
                flash('Login berhasil.', 'success')
                return redirect(url_for('cuaca'))

            flash('Username atau password salah.', 'error')

        except Exception as e:
            print(e)
            flash('Terjadi kesalahan saat login.', 'error')

    return render_template('auth/login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not username or not password or not confirm_password:
                flash('Semua field wajib diisi.', 'error')
                return render_template('auth/register.html')

            if len(password) < 8:
                flash('Password minimal 8 karakter.', 'error')
                return render_template('auth/register.html')

            if not re.search(r'[A-Za-z]', password):
                flash('Password harus mengandung huruf.', 'error')
                return render_template('auth/register.html')

            if not re.search(r'\d', password):
                flash('Password harus mengandung angka.', 'error')
                return render_template('auth/register.html')

            if password != confirm_password:
                flash('Password dan konfirmasi password tidak sama.', 'error')
                return render_template('auth/register.html')

            existing_user = User.query.filter_by(username=username).first()

            if existing_user:
                flash('Username sudah digunakan.', 'error')
                return render_template('auth/register.html')

            hashed_password = generate_password_hash(password)

            new_user = User(
                username=username,
                password=hashed_password
            )

            db.session.add(new_user)
            db.session.commit()

            flash('Berhasil daftar, silakan login.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            db.session.rollback()
            print(e)
            flash('Terjadi kesalahan saat registrasi.', 'error')

    return render_template('auth/register.html')


@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    try:
        questions = Quiz.query.all()

        if not questions:
            flash('Belum ada soal quiz.', 'error')
            return render_template(
                'quiz.html',
                questions=None,
                user=None,
                leaderboard=[]
            )

        answered = session.get("answered_questions", [])
        user = None
        user_id = session.get('user_id')
        leaderboard = User.query.order_by(User.score.desc()).limit(10).all()

        available_questions = [
            q for q in questions
            if q.id not in answered
        ]

        if not available_questions:
            flash('Selamat, semua soal sudah selesai.', 'success')
            return render_template(
                'quiz.html',
                questions=None,
                user=user,
                leaderboard=leaderboard
            )
        else:
            current_question = random.choice(available_questions)

        if user_id:
            user = db.session.get(User, user_id)

        if request.method == 'POST':
            answer = request.form.get('answer')
            question_id = request.form.get('question_id')

            question = db.session.get(Quiz, question_id)

            if not question:
                flash('Soal tidak ditemukan.', 'error')
                return redirect(url_for('quiz'))

            if answer == question.answer:
                if user:
                    user.score = (user.score or 0) + 10
                    db.session.commit()

                if question.id not in answered:
                    answered.append(question.id)
                session["answered_questions"] = answered

                flash('Jawaban benar!', 'success')
            else:
                flash('Jawaban salah!', 'error')

            return redirect(url_for('quiz'))


        return render_template(
            'quiz.html',
            questions=current_question,
            user=user,
            leaderboard=leaderboard
        )

    except Exception as e:
        db.session.rollback()
        print(e)
        flash('Terjadi kesalahan saat membuka quiz.', 'error')
        return redirect(url_for('cuaca'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Berhasil logout.', 'success')
    return redirect(url_for('cuaca'))


if __name__ == '__main__':
    app.run(debug=True)


