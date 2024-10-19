########################################################
# UniceAPI                                             #
# Votre ENT. Dans votre poche.                         #
# Développé par Hugo Meleiro (@hugofnm) / MetrixMedia  #
# MIT License                                          #
# 2022 - 2025                                          #
########################################################

from datetime import datetime
import pytz
import io
import os
import re
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
ADE_PROJECT = 4 # Projet 2024-2025
ADE_DATE = "&firstDate=2024-09-01&lastDate=2025-08-31"

def extract_key_value(key):
    """Extracts a specific key-value pair from a JSON data"""
    with open("status.json", "r") as f:
        data = json.load(f)
        value = data.get(key)
        f.close()
    return value

# get the secret key from the file "token.json" and take the "secret" value
with open("secret.json", "r") as f:
    tempjson = json.load(f)
    key = tempjson.get("secret")
    bugsnagAPI = tempjson.get("bugsnag") # old key destroyed dont worry :p
    whichServer = tempjson.get("whichServer")
    banned = tempjson.get("banned")
    f.close()

bugsnag.configure(
    api_key=bugsnagAPI,
    project_root="./",
)

if whichServer == "prod" or whichServer == "dev":
    logging.basicConfig(filename='UniceAPI.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
    logger = logging.getLogger("UniceAPI.log")
    handler = BugsnagHandler()
    handler.setLevel(logging.ERROR)
    logger.addHandler(handler)

app = Flask(__name__)
handle_exceptions(app)
dashboard.config.init_from(file='config.cfg')

# Only for debug
# app.debug = True

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

# Status -----------------------------------------------------------------------
@app.route("/status")
def status():
    global banned

    resp = "v2.2.0"

    ip = get_remote_address()
    isBanned = False
    if ip in banned:
        isBanned = True

    # send response as json
    resp = {
        "banned": isBanned, # true if the ip is banned
        "version": resp, # version de l'app
        "isAvailable": extract_key_value("isAvailable"),
        "maintenance": extract_key_value("maintenance")
    }

    return resp

# Login API -----------------------------------------------------------------------
@app.route("/login", methods=["POST"])
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

    if(username == "demo" and password == "demo"):
        # close the client on fresh login
        if username in active_clients.keys():
            active_clients[username].close()

        active_clients[username] = client
        session["username"] = username
        return {
            "name": "Anaïs Démeaux",
            "userADEData": {
                "cursus" : "demo",
                "uid" : "demo"
            },
            "semesters": [{
                "id": 0,
                "semester": "TBIS1T"
            }],
            "success": True
        }

    # we try to login
    if not client.login(username, password):
        return {
            "success": False
        }

    # login was a sucess
    semesters = client.get_semesters()
    
    resSem = []
    temp = {}
    i = 0
    try:
        for sem in semesters:
            temp = {
                "id": i,
                "semester": sem
            }
            resSem.append(temp)
            i += 1
    except:
        resSem.append({
            "id": 0,
            "semester": "Intracursus Indisponible"
        })

    semesters = resSem
    info = client.get_info()

    # close the client on fresh login
    if username in active_clients.keys():
        active_clients[username].close()

    active_clients[username] = client
    session["username"] = username

    try:
        name = info["displayName"]
        userADEData = {
            "cursus" : info["diplomep"] + "-VET",
            "uid" : info["uid"]
        }
    except KeyError:
        return {
            "success": False
        }

    return {
        "name": name,
        "userADEData": userADEData,
        "semesters": semesters,
        "success": True
    }

# First Login API -----------------------------------------------------------------------
@app.route("/signup", methods=["POST"])
@limiter.limit("1 per second")
def signup():
    data = request.get_json()
    if not data:
        data = request.form

    try:
        username = data["username"]
        password = data["password"]
        eula = data["eula"]
    except (KeyError, TypeError):
        abort(400)

    client = IntraClient()

    if(username == "demo" and password == "demo"):
        # close the client on fresh login
        if username in active_clients.keys():
            active_clients[username].close()

        active_clients[username] = client
        session["username"] = username
        return {
            "name": "Anaïs Démeaux",
            "userADEData": {
                "cursus" : "demo",
                "uid" : "demo"
            },
            "semesters": [{
                "id": 0,
                "semester": "TBIS1T"
            }],
            "success": True
        }

    # we try to login
    if not client.login(username, password):
        return {
            "success": False
        }

    # login was a sucess
    semesters = client.get_semesters()
    
    resSem = []
    temp = {}
    i = 0
    try:
        for sem in semesters:
            temp = {
                "id": i,
                "semester": sem
            }
            resSem.append(temp)
            i += 1
    except:
        resSem.append({
            "id": 0,
            "semester": "Indisponible"
        })

    semesters = resSem
    info = client.get_info()

    # close the client on fresh login
    if username in active_clients.keys():
        active_clients[username].close()

    active_clients[username] = client
    session["username"] = username

    try:
        name = info["displayName"]
        userADEData = {
            "cursus" : info["diplomep"] + "-VET",
            "uid" : info["uid"]
        }
    except KeyError:
        return {
            "success": False
        }

    return {
        "name": name,
        "userADEData": userADEData,
        "semesters": semesters,
        "success": True
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

    try:
        dl_pdf(user, semester)
    except Exception as e:
        session['not_intra'] = True
        return "OK"

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

    if(session.get("not_intra")):
        with open("./demo/notintra.json", "rb") as f:
            pdf_data = json.load(f)
            f.close()
        return json.dumps(pdf_data)

    if(user == "demo"):
        with open("./demo/demo.json", "rb") as f:
            pdf_data = json.load(f)
            f.close()
        return json.dumps(pdf_data)

    try:
        pdf_data = dl_and_parse_pdf(user, semester)
    except :
        with open("./demo/notintra.json", "rb") as f:
            pdf_data = json.load(f)
            f.close()
        return json.dumps(pdf_data)
    
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

    if(username == "demo"):
        return {
            "username": username,
            "semesters": [{
                "id": 0,
                "semester": "TBIS1T"
            }]
        }

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

# iCal API -----------------------------------------------------------------------
@app.route("/edt/<adeid>", methods=["POST"])
@limiter.limit("10 per minute")
def edt(adeid):
    if not adeid:
        abort(400)

    try:
        response = requests.get(f"https://edtweb.univ-cotedazur.fr/jsp/custom/modules/plannings/anonymous_cal.jsp?code={adeid}&projectId={ADE_PROJECT}&calType=ical{ADE_DATE}", timeout = 3)
    except Exception as e:
        return [{
            "id": 0,
            "summary": "ADE Indisponible",
            "location": "Emplois du temps indisponibles.",
            "description": "",
            "start_time": datetime.now().isoformat(),
            "end_time": (datetime.now() + timedelta(hours=1)).isoformat()
        }]
    
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

            # Clean some ADE shit
            desc = component.get("description").to_ical().decode()
            desc = desc.replace("\\n", "\n")
            desc = desc.replace("\\,", ",")
            desc = re.sub(r"\(Exporté le:[^)]+\)", "", desc).strip()

            event = {
                "id": id, 
                "summary": component.get("summary").to_ical().decode(),
                "location": component.get("location").to_ical().decode(),
                "description": desc,
                "start_time": component.get("dtstart").dt.isoformat(),
                "end_time": component.get("dtend").dt.isoformat(),
            }
            events.append(event)
            id += 1
    
    events_json = json.dumps(events)
    
    # send response as ical
    return events_json

# Get the current event in the calendar -----------------------------------------------------------------------
@app.route("/edt/<adeid>/nextevent", methods=["GET"])
@limiter.limit("15 per minute")
def nextevent(adeid):
    if not adeid:
        abort(400)

    try :
        response = requests.get(f"https://edtweb.univ-cotedazur.fr/jsp/custom/modules/plannings/anonymous_cal.jsp?code={adeid}&projectId={ADE_PROJECT}&calType=ical{ADE_DATE}", timeout = 3)
    except Exception as e:
        return {
            "summary": "ADE Indisponible",
            "location": "Emplois du temps indisponibles."
        }

    if response.status_code != 200:
        return {
            "summary": "ADE Indisponible",
            "location": "Emplois du temps indisponibles."
        }

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
            if component.get("dtstart").dt > (now - timedelta(minutes = 15)) and (next_event_time is None or next_event_time > component.get("dtstart").dt):
                next_event = component
                next_event_time = component.get("dtstart").dt

    # if there is no next event
    if next_event is None:
        return {
            "summary": "Non disponible",
            "location": "Pas de cours en vue :)"
        }
    
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

# Dashboard -----------------------------------------------------------------------
def get_username():
    return session.get("username")

dashboard.config.group_by = get_username
dashboard.bind(app)

if __name__ == '__main__':
    app.run()