########################################################
# UniceAPI                                             #
# Votre ENT. Dans votre poche.                         #
# Développé par Hugo Meleiro (@hugofnm) / MetrixMedia  #
# MIT License                                          #
# 2022 - 2024                                          #
########################################################

import base64
from datetime import datetime
import pytz
import io
import os
import time
from datetime import timedelta
from functools import lru_cache
import json
import bugsnag
from bugsnag.flask import handle_exceptions
from bugsnag.handlers import BugsnagHandler

from flask import (Flask, abort, make_response, redirect, render_template,
                   request, send_file, send_from_directory, session)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix

import requests
import logging

from intra_client import IntraClient
from pdf_reader import get_pdf_data

import icalendar
import flask_monitoringdashboard as dashboard

CACHE_DURATION = 900 # 15 minutes

def extract_key_value(key):
    """Extracts a specific key-value pair from a JSON data"""
    with open("status.json", "r") as json_data:
        json_data = json_data.read()
        data = json.loads(json_data)
        value = data.get(key)
    return value

# get the secret key from the file "token.json" and take the "secret" value
with open("secret.json", "r") as f:
    tempjson = json.load(f)
    key = tempjson.get("secret")
    bugsnagAPI = tempjson.get("bugsnag") # old key destroyed dont worry :p
    whichServer = tempjson.get("whichServer")
    banned = tempjson.get("banned")

bugsnag.configure(
    api_key=bugsnagAPI,
    project_root="./",
)

if whichServer == "prod" or whichServer == "dev":
    logging.basicConfig(filename='UniceAPI.log', level=logging.ERROR)
    logger = logging.getLogger("UniceAPI.log")
    handler = BugsnagHandler()
    handler.setLevel(logging.ERROR)
    logger.addHandler(handler)

app = Flask(__name__)
handle_exceptions(app)
dashboard.config.init_from(file='config.cfg')

# Only for debug
#app.debug = True

if not key:
    app.logger.warning("Using developement key")
    key = "debug"
app.secret_key = key
app.permanent_session_lifetime = timedelta(minutes=10)

Talisman(app, content_security_policy=None)

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://"
)

active_clients = {}

# Test API -----------------------------------------------------------------------
@app.route('/greet/<name>')
def greet(name):
    if name == "crash":
        bugsnag.notify(Exception('Test error'))
    return "Hello, " + name

# PDF caching -----------------------------------------------------------------------
@lru_cache(maxsize=64)
def _dl_pdf_cached(username, semester, ttl_hash=None):
    """
    Dowloads a PDF or returns the one in cache
    """
    client = active_clients[username]
    if semester == "latest":
        pdf = client.get_latest_semester_pdf()
    else:
        pdf = client.get_semester_pdf(semester)
    return pdf

@lru_cache(maxsize=64)
def _parse_pdf_cached(username, semester, ttl_hash=None):
    """
    Dowloads or gets the cached pdf and parses it
    """
    pdf = _dl_pdf_cached(username, semester, ttl_hash)
    return get_pdf_data(pdf)

def _get_ttl_hash(seconds):
    """
    Return the same value withing `seconds` time period
    """
    return round(time.time() / seconds)

def dl_and_parse_pdf(username, semester):
    """
    Will only get and parse a fresh new pdf once every hour
    """
    return _parse_pdf_cached(username, semester, _get_ttl_hash(CACHE_DURATION))

def dl_pdf(username, semester):
    """
    Downloads the pdf
    """
    return _dl_pdf_cached(username, semester, _get_ttl_hash(CACHE_DURATION))

# Index API -----------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# Login API -----------------------------------------------------------------------
@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
@limiter.limit("1 per second")
def login():
    data = request.get_json()
    if not data:
        data = request.form

    try:
        username = data["username"]
        password = data["password"]
    except (KeyError, TypeError):
        abort(400)

    client = IntraClient()

    # we try to login
    if not client.login(username, password):
        return {
            "success": False
        }

    if(username == "demo" and password == "demo"):
        # close the client on fresh login
        if username in active_clients.keys():
            active_clients[username].close()

        active_clients[username] = client
        session["username"] = username
        return {
            "success": True,
            "name": "Anaïs Démeaux",
            "semesters": ["TBIS1T"]
        }

    # login was a sucess
    semesters = client.get_semesters()
    
    resSem = []
    temp = {}
    i = 0
    for sem in semesters:
        temp = {
            "id": i,
            "semester": sem
        }
        resSem.append(temp)
        i += 1

    semesters = resSem
    name = client.get_name()

    # close the client on fresh login
    if username in active_clients.keys():
        active_clients[username].close()

    active_clients[username] = client
    session["username"] = username

    return {
        "success": True,
        "name": name,
        "semesters": semesters
    }

# Get avatar -----------------------------------------------------------------------
@app.route("/avatar")
def avatar():
    user = session.get("username")
    if not user:
        return send_from_directory(".", "profile.png")

    client = active_clients.get(user)
    if client is None:
        return send_from_directory(".", "profile.png")

    if(user == "demo"):
        return send_from_directory(".", "./demo/demo.png")

    avatar = client.get_avatar()

    if not avatar:
        return send_from_directory(".", "profile.png")

    return send_file(io.BytesIO(avatar), mimetype="image/png")

# Load pdf -----------------------------------------------------------------------
@app.route("/load_pdf")
def load_pdf():
    user = session.get("username")
    if not user:
        abort(401)

    client = active_clients.get(user)
    if client is None:
        abort(401)

    semester = request.args.get("sem", client.current_semester)

    if(user == "demo"):
        return "OK"

    dl_pdf(user, semester)

    return "OK"

# Scrape pdf -----------------------------------------------------------------------
@app.route("/scrape_pdf")
def scrape_pdf():
    user = session.get("username")
    if not user:
        abort(401)

    client = active_clients.get(user)
    if client is None:
        abort(401)

    # if no semester is provided, we select the current one
    semester = request.args.get("sem", client.current_semester)

    if(user == "demo"):
        with open("./demo/demo.json", "rb") as f:
            pdf_data = json.load(f)
        return json.dumps(pdf_data)

    pdf_data = dl_and_parse_pdf(user, semester)
    
    return json.dumps(pdf_data)

# Auto mode -----------------------------------------------------------------------
@app.route("/auto_login", methods=["POST"])
def auto_login():
    # get api key
    global key

    # compare headers for api key
    if request.headers.get("X-API-Key") != key:
        abort(403)

    data = request.get_json()
    if not data:
        data = request.form

    try:
        username = data["username"]
        password = data["password"]
    except (KeyError, TypeError):
        abort(400)

    client = IntraClient()

    # we try to login
    if not client.login(username, password):
        return {
            "success": False
        }

    # close the client on fresh login
    if username in active_clients.keys():
        active_clients[username].close()

    active_clients[username] = client
    session["username"] = username

    semester = request.args.get("sem")

    if(username == "demo"):
        with open("./demo/demo.json", "rb") as f:
            pdf_data = json.load(f)
        return json.dumps(pdf_data)
    else:
        pdf_data = dl_and_parse_pdf(username, semester)
        return json.dumps(pdf_data)

# Whoami -----------------------------------------------------------------------
@app.route("/whoami")
def whoami():
    user = session.get("username")
    if not user:
        return {}
    
    client = active_clients.get(user)
    if client is None:
        return {}
       
    username = session.get("username", "403")
    semesters = client.get_semesters()

    resSem = []
    temp = {}
    i = 0
    for sem in semesters:
        temp = {
            "id": i,
            "semester": sem
        }
        resSem.append(temp)
        i += 1

    semesters = resSem
    
    name = client.get_name()
    resp = {
        "username": username,
        "semesters": semesters
    }
    return resp

# Logout -----------------------------------------------------------------------
@app.route("/logout")
def logout():
    user = session.get("username")
    if not user:
        return "No one to logout"
        abort(401)

    client = active_clients.get(user)
    if client is None:
        abort(401)

    if user:
        if user != "demo":
            client.logout()
        client.close()
        del active_clients[user]
        session.pop("username", None)
        return f"Logged out {user}"

# Status -----------------------------------------------------------------------
@app.route("/status")
def status():
    global banned

    resp = requests.get("https://github.com/UniceApps/UniceNotes/releases/latest").text
    # get the version number on the title of the page
    resp = resp.split("<title>")[1].split("</title>")[0].split(" ")[1]

    ip = get_remote_address()
    isBanned = False
    if ip in banned:
        isBanned = True

    # send response as json
    resp = {
        "banned": isBanned, # true if the ip is banned
        "version": resp, # version de l'app
        "isAvailable": extract_key_value("disponible"),
        "maintenance": extract_key_value("maintenance") 
    }

    return resp

# iCal API -----------------------------------------------------------------------
@app.route("/edt/<username>", methods=["POST"])
def edt(username):
    password = request.args.get("password")

    if not username:
        abort(400)

    if username == "demo":
        username = "vermaelen"

    if password is None:
        response = requests.get("https://iut-ical.unice.fr/gpucal.php?name=" + username, verify=False)
    else:
        response = requests.get("https://iut-ical.unice.fr/gpucal.php?name=" + username + "&password=" + password, verify=False)

    if response.status_code != 200:
        abort(500)  # internal server error

    ical_string = response.content

    # parse icalendar string
    calendar = icalendar.Calendar.from_ical(ical_string)
    
    # convert calendar to JSON
    id = 0
    events = []
    for component in calendar.walk():
        if component.name == "VEVENT":
            event = {
                "id": id, 
                "summary": component.get("summary").to_ical().decode(),
                "location": component.get("location").to_ical().decode(),
                "description": component.get("description").to_ical().decode(),
                "start_time": component.get("dtstart").dt.isoformat(),
                "end_time": component.get("dtend").dt.isoformat(),
            }
            events.append(event)
            id += 1
    
    events_json = json.dumps(events)
    
    # send response as ical
    return events_json

# Get the current event in the calendar -----------------------------------------------------------------------
@app.route("/edt/<username>/nextevent", methods=["GET"])
@limiter.limit("1 per second")
@limiter.limit("5 per minute")
def nextevent(username):
    password = request.args.get("password")

    if not username:
        abort(400)

    if username == "demo":
        username = "vermaelen"

    if password is None:
        response = requests.get("https://iut-ical.unice.fr/gpucal.php?name=" + username, verify=False)
    else:
        response = requests.get("https://iut-ical.unice.fr/gpucal.php?name=" + username + "&password=" + password, verify=False)

    if response.status_code != 200:
        abort(500)  # internal server error

    ical_string = response.content

    # parse icalendar string
    calendar = icalendar.Calendar.from_ical(ical_string)

    # get the current time
    tz_PA = pytz.timezone('Europe/Paris')
    now = datetime.now(tz_PA)

    # get the next event
    next_event = None
    next_event_time = None
    for component in calendar.walk():
        if component.name == "VEVENT":
            if component.get("dtstart").dt > now and (next_event_time is None or next_event_time > component.get("dtstart").dt):
                next_event = component
                next_event_time = component.get("dtstart").dt

    # if there is no next event
    if next_event is None:
        return {}
    
    # return the next event as json
    event = {
        "summary": next_event.get("summary").to_ical().decode(),
        "location": next_event.get("location").to_ical().decode(),
        "description": next_event.get("description").to_ical().decode(),
        "start_time": next_event.get("dtstart").dt.isoformat(),
        "end_time": next_event.get("dtend").dt.isoformat(),
    }
    event_json = json.dumps(event)
    return event_json            

# Absences API -----------------------------------------------------------------------
@app.route("/absences", methods=["GET"])
def absences():
    user = session.get("username")
    if not user:
        abort(401)

    client = active_clients.get(user)
    if client is None:
        abort(401)

    if(user == "demo"):
        with open("./demo/demoabs.json", "rb") as f:
            pdf_data = json.load(f)
        return json.dumps(pdf_data)

    absences_data = client.get_absences()
            
    # Convert the result to JSON string
    absences_data = json.dumps(absences_data)
    
    return absences_data

# Admin --------------------------------------------------------------------------
@app.route("/admin", methods=["GET", "POST"])
@limiter.limit("2 per hour")
def admin():
    # get api key
    global key

    # get authorized ip
    with open("secret.json", "r") as f:
        autorized_ip = json.load(f).get("ip")

    # check if the ip is correct (authorized ip is a list)
    if get_remote_address() not in autorized_ip:
        app.logger.warning(f"Unauthorized access from {get_remote_address()}")
        abort(403)

    if request.method == "GET":
        resp = {
            "disponible": extract_key_value("disponible"),
            "maintenance": extract_key_value("maintenance")
        }
        return resp

    if request.method == "POST":
        # get the form data
        data = request.get_json()
        api_key = data.get("api_key")

        # check if the api key is correct
        if api_key != key:
            abort(403)
        elif api_key == key:
            for res in data.keys():
                if res not in ["maintenance", "disponible", "api_key"]:
                    abort(400)
                elif res == "api_key":
                    del data[res]
                    with open("status.json", "w") as f:
                        f.flush()
                        f.write(json.dumps(data))
                    app.logger.info(f"Admin updated maintenance to {data['maintenance']} and disponible to {data['disponible']}")
                    return "OK"
        else :
            abort(400)

dashboard.bind(app)

if __name__ == '__main__':
    app.run()