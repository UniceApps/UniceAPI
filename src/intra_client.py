########################################################
# UniceAPI                                             #
# Votre ENT. Dans votre poche.                         #
# Développé par Hugo Meleiro (@hugofnm) / MetrixMedia  #
# Basé sur les travaux de : @itskatt/extracursus       #
# 2022 - 2025                                          #
########################################################

from requests import Session
import re
from bs4 import BeautifulSoup

class IntraClient:
    """
    Un client pour se connecter à Intracursus
    """
    def __init__(self):
        self.sess = Session()
        self.sess.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        })
        # self.sess.headers.update({
        #     "User-Agent": "Mozilla/5.0 (compatible; UniceAPI/1.0; +https://notes.metrixmedia.fr)"
        # })
        self.semesters = []
        self.current_semester = None

    def close(self):
        self.sess.close()

    def login(self, username, password):
        """
        Authentification sur login.univ-cotedazur.fr
        """

        # si on est en mode demo
        if(username == "demo" and password == "demo"):
            return True

        login_url = "https://login.univ-cotedazur.fr/login?service=https%3A%2F%2Flogin.univ-cotedazur.fr"

        resp = self.sess.get(login_url, timeout = 5)
        html_page = resp.text

        # deux valeurs importantes
        execution = html_page.split('type="hidden" name="execution" value="')[1].split('"')[0]
        payload = {
            "username": username,
            "password": password,

            "execution": execution,
            "_eventId": "submit",
            "submit": "SE CONNECTER"
        }

        resp = self.sess.post(login_url, data=payload, allow_redirects=False, timeout = 5)

        # si on a donné des mauvais identifiants
        if "Location" not in resp.headers:
            return False

        url_location = resp.headers["Location"]
        resp = self.sess.get(url_location, timeout = 5)

        ticket = url_location.split('ticket=')[1]
        self.sess.cookies.set("SESSID", ticket, domain="planier.univ-cotedazur.fr")
        return True

    def logout(self):
        """
        Déconnexion de l'intranet
        """
        self.sess.get("https://login.univ-cotedazur.fr/logout", timeout = 10)

    def get_semesters(self):
        """
        Se connecte a intracursus et renvoie la liste des des semestres disponible
        """
        # connexion a intracursus
        try:
            resp = self.sess.get("https://intracursus.unice.fr/ic/dlogin/cas.php", timeout = 15)
            html_page = resp.text
        except Exception:
            return None

        semesters = {}
        # recuperation du semestre actuel
        # il se peut qu'il n'existe pas
        try:
            current_semester = html_page.split("<b>Relevé des notes et absences de ")[1].split()[0]
            semesters[current_semester] = current_semester
            self.current_semester = current_semester
        except IndexError:
            pass

        # recuperation des autres semestres
        try:
            raw_semesters = html_page.split(
                '<select id="idautreinscription" name="idautreinscription" size="1">')[1].split("</select>")[0].strip()
            for line in raw_semesters.splitlines():
                id = line.split('value="')[1].split('"')[0]
                name = line.split('">')[1].split()[0]
                semesters[name] = id
        except Exception: # on a pas pu trouver d'autres semestres
            pass

        self.semesters = semesters
        return list(semesters.keys())

    def get_info(self):
        """
        Renvoie les infos de l'utilisateur
        """
        informations = {}
        try:
            resp = self.sess.get("https://login.univ-cotedazur.fr/login", timeout = 5)
            string = resp.text
        except Exception:
            return None

        soup = BeautifulSoup(string, 'html.parser')

        infos = soup.find_all('table')[0]

        for row in infos.tbody.find_all('tr'):    
            # Find all data for each column
            columns = row.find_all('td')
            informations[columns[0].text] = columns[1].text.strip('\n[]')

        # Traitement du nom
        name = informations["displayName"]

        if name == "":
            name = "Étudiant"
        
        if len(name) > 20:
            # on prend juste le premier nom
            name = name.split()[0]

        # on met la premiere lettre de chaque nom en majuscule
        name = name.title()

        informations["displayName"] = name

        return informations

    def get_avatar(self):
        """
        Renvoie l'avatar de l'utilisateur
        """
        resp = self.sess.get("https://intracursus.unice.fr/ic/dlogin/cas.php").text

        soup = BeautifulSoup(resp, 'html.parser')
        img_tags = soup.find_all("img")

        img_url = None

        for tag in img_tags:
            src = tag.get("src")
            if src and "etudiant" in src:
                img_url = src
                break

        if not img_url:
            return None

        try:
            avatar = self.sess.get("https://login.univ-cotedazur.fr/login?service=https%3A%2F%2Fintracursus.unice.fr%2Fic%2Fetudiant/" + img_url)
        except Exception:
            return None

        if avatar.status_code != 200:
            return None

        return avatar.content

    def get_semester_pdf(self, semester):
        # semestre actuel
        if self.current_semester and any(v == semester for v in self.semesters.values()):
            payload = {
            "telrelevepresences": f"Télécharger le relevé des notes et absences de {semester}"
        }
        # autre semestre
        else:
            payload = {
                "idautreinscription": self.semesters[semester],
                "telreleveanterieur": "Télécharger le relevé du parcours sélectionné"
            }

        # téléchargement...
        resp = self.sess.post(
            "https://intracursus.unice.fr/ic/etudiant/ic-notes-presences.php",
            data=payload
        )
        return resp.content
    
    def get_latest_semester_pdf(self):
        resp = self.sess.post(
            "https://intracursus.unice.fr/ic/etudiant/ic-notes-presences.php"
        )
        if resp.status_code != 200:
            return None

        return resp.content