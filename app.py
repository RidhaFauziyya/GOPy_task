from flask import Flask, redirect, url_for, session, request, render_template, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import openmeteo_requests
import pandas as pd
import numpy as np
import requests_cache
from retry_requests import retry
import requests
from models.user import db, User, Quiz
import random

app = Flask(__name__)
app.secret_key = 'secretkey' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

@app.route("/")
def cuaca():
    city = request.args.get('city', 'Yogyakarta')

    city_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
    city_response = requests.get(city_url).json()

    city = city_response["results"][0]
    lat = city["latitude"]
    long = city["longitude"]

    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": lat,
        "longitude": long,
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "rain_sum"],
        "current": ["temperature_2m", "apparent_temperature", "rain", "relative_humidity_2m"],
        "hourly": ["temperature_2m", "apparent_temperature", "weather_code"],
        "timezone": "auto",
        "forecast_days": 3
    }
    responses = openmeteo.weather_api(url, params=params)
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
        "Sunday": "Minggu"
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
        "December": "Desember"
    }

    current = data.Current()
    current_time = pd.to_datetime(current.Time(), unit="s").tz_localize("UTC").tz_convert("Asia/Jakarta")
    current_temperature_2m = round(current.Variables(0).Value())
    current_apparent_temperature = round(current.Variables(1).Value())
    current_rain = current.Variables(2).Value()
    current_relative_humidity_2m = current.Variables(3).Value()

    day_current = day_indo[current_time.strftime("%A")]
    month_current = month_indo[current_time.strftime("%B")]
    date_current = current_time.strftime(f"%d {month_current} %Y")
    time_current = f"{day_current}, {date_current}"

    current_data  = {
        "time": time_current,
        "temperature": current_temperature_2m,
        "apparent_temperature": current_apparent_temperature,
        "current_rain": current_rain,
        "humidity": current_relative_humidity_2m,
        "timezone": timezone,
        "tz_abbr": timezone_2,
        "city": city["name"],
    }

    hourly = data.Hourly()
    hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
    hourly_apparent_temperature = hourly.Variables(1).ValuesAsNumpy()
    hourly_weather_code = hourly.Variables(2).ValuesAsNumpy()
    dates = pd.date_range(
        start = pd.to_datetime(hourly.Time(), unit = "s").tz_localize("UTC").tz_convert("Asia/Jakarta"),
        end = pd.to_datetime(hourly.TimeEnd(), unit = "s").tz_localize("UTC").tz_convert("Asia/Jakarta"),
        freq = pd.Timedelta(seconds = hourly.Interval()),
        inclusive = "left"
    )
    mask = dates.hour.isin([14,22])
    filtered_date = dates[mask]
    hourly_data = {"date": filtered_date }
    hourly_data["temperature_2m"] = np.round(hourly_temperature_2m[mask]).astype(int)
    hourly_data["apparent_temperature"] = np.round(hourly_apparent_temperature[mask]).astype(int)
    hourly_data["weather_code"] = hourly_weather_code[mask]

    hourly_dataframe = pd.DataFrame(data = hourly_data)
    hourly_dataframe["date_only"] = hourly_dataframe["date"].dt.normalize()
    hourly_dataframe["hour"] = hourly_dataframe["date"].dt.hour

    daily = data.Daily()
    daily_weather_code = daily.Variables(0).ValuesAsNumpy()
    daily_temperature_2m_max = daily.Variables(1).ValuesAsNumpy()
    daily_temperature_2m_min = daily.Variables(2).ValuesAsNumpy()
    daily_rain_sum = daily.Variables(3).ValuesAsNumpy()
    
    dates = pd.date_range(
        start = pd.to_datetime(daily.Time(), unit = "s").tz_localize("UTC").tz_convert("Asia/Jakarta"),
        end = pd.to_datetime(daily.TimeEnd(), unit = "s").tz_localize("UTC").tz_convert("Asia/Jakarta"),
        freq = pd.Timedelta(seconds = daily.Interval()),
        inclusive = "left")
    
    date_indo = []
    for d in dates:
        days = day_indo[d.strftime("%A")]
        months = month_indo[d.strftime("%B")]
        dated = d.strftime(f"%d {months} %Y")
        date_indo.append(f"{days}, {dated}")

    daily_data = {"date": date_indo}

    daily_data["weather_code"] = daily_weather_code
    daily_data["temperature_2m_max"] = np.round(daily_temperature_2m_max).astype(int)
    daily_data["temperature_2m_min"] = np.round(daily_temperature_2m_min).astype(int)
    daily_data["rain_sum"] = daily_rain_sum

    daily_df = pd.DataFrame(daily_data)
    daily_df["date_only"] = pd.to_datetime(dates).normalize()

    pivot_temp = hourly_dataframe.pivot(index="date_only", columns="hour", values="temperature_2m")
    pivot_temp.columns = ["day_temp", "night_temp"]

    merged_df = daily_df.merge(pivot_temp, on="date_only", how="left")

    forecast_df = merged_df[[
        "date", "date_only", "weather_code", "temperature_2m_max", "temperature_2m_min", "rain_sum",
        "day_temp", "night_temp"
    ]]

    forecast_data = forecast_df.to_dict(orient="records")

    return render_template('home.html', current=current_data, forecast=forecast_data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect('/')
        else:
            flash('Username atau password salah', 'error')
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password == confirm_password:
            hashed_password  = generate_password_hash(password)
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                flash('Username sudah digunakan', 'error')
            else:
                new_user = User(username=username, password=hashed_password)
                db.session.add(new_user)
                db.session.commit()
                flash('Berhasil daftar, silakan login.', 'success')
                return redirect(url_for('login'))
        else:
            flash('Pasword dan Konfirmasi Passwor tidak sama', 'error')
    return render_template('auth/register.html')


@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    questions = Quiz.query.all()
    current_question = random.choice(questions)
    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None
    if request.method == 'POST':
        answer = request.form.get('answer')
        question_id = request.form.get('question_id')
        question = Quiz.query.get(question_id)

        if answer == question.answer:
            if user:
                user.score += 10
                db.session.commit()
            flash('Jawaban benar!', 'success')
        else:
            flash('Jawaban salah!', 'error')
        return redirect(url_for('quiz'))
    leaderboard = User.query.order_by(User.score.desc()).limit(10).all()
    return render_template('quiz.html', questions=current_question, user=user, leaderboard=leaderboard)


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('Berhasil logout.', 'success')
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)



