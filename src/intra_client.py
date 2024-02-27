########################################################
# UniceAPI                                             #
# Votre ENT. Dans votre poche.                         #
# Développé par Hugo Meleiro (@hugofnm) / MetrixMedia  #
# Basé sur les travaux de : @itskatt/extracursus       #
# 2022 - 2024                                          #
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

        resp = self.sess.get("https://intracursus.unice.fr/ic/dlogin/cas.php", timeout = 20)
        html_page = resp.text

        # trois valeurs importantes
        route_login = "/login?service=https%3A%2F%2Fintracursus.unice.fr%2Fic%2Fdlogin%2Fcas.php"
        execution = html_page.split('type="hidden" name="execution" value="')[1].split('"')[0]

        payload = {
            "username": username,
            "password": password,

            "execution": execution,
            "_eventId": "submit",
            "submit": "SE CONNECTER"
        }

        resp = self.sess.post(
            f"https://login.univ-cotedazur.fr{route_login}", data=payload, allow_redirects=False, timeout = 20)

        # si on a donné des mauvais identifiants
        if "Location" not in resp.headers:
            return False

        url_location = resp.headers["Location"]
        resp = self.sess.get(url_location, timeout = 20)

        ticket = url_location.split('ticket=')[1]
        self.sess.cookies.set("SESSID", ticket, domain="planier.univ-cotedazur.fr")
        return True

    def logout(self):
        """
        Déconnexion de l'intranet
        """
        self.sess.get("https://login.univ-cotedazur.fr/logout", timeout = 20)

    def get_semesters(self):
        """
        Se connecte a intracursus et renvoie la liste des des semestres disponible
        """
        # connection a intracursus
        resp = self.sess.get("https://intracursus.unice.fr/ic/dlogin/cas.php")
        html_page = resp.text

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

    def get_name(self):
        """
        Renvoie le nom de l'utilisateur
        """
        resp = self.sess.get("https://intracursus.unice.fr/ic/dlogin/cas.php")
        string = resp.text

        soup = BeautifulSoup(string, 'html.parser')

        pattern = "Notes et absences de [A-Z]* [A-Z]*"
        name = soup.find(string=re.compile(pattern))
        name = str(name)

        # remove the unwanted part
        name = name.strip("Notes et absences de ")

        # split the name by "("
        substrings = name.split("(")

        # remove the last part
        name = substrings[0]
        name = name.rstrip()

        if name == "":
            name = "Étudiant"
        
        if len(name) > 20:
            # on prend juste le premier nom
            name = name.split()[0]

        # on met la premiere lettre de chaque nom en majuscule
        name = name.title()

        return name

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

        avatar = self.sess.get("https://login.univ-cotedazur.fr/login?service=https%3A%2F%2Fintracursus.unice.fr%2Fic%2Fetudiant/" + img_url)

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
        # semestre actuel
        semester = self.current_semester
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

    def get_absences(self): # ce code est plus bancal que le batiment de l'iut
        self.sess.get("https://iut-gpu-personnels.unice.fr/sat/index.php", verify=False, timeout = 20)
        resp = self.sess.get("https://login.univ-cotedazur.fr/login?service=https%3A%2F%2Fiut-gpu-personnels.unice.fr%2Fmobile%2Findex.php%3Faim%3Dconsultabs", verify=False, timeout = 20)

        soup = BeautifulSoup(resp.text, 'html.parser')

        whichone = 1
        absences_data = []
        retards_data = []
        exclusions_data = []
        
        # Find the tables by tag or other attributes
        text_element = soup.find(lambda tag: tag.name == 'p' and "par les absences" in tag.text)
        if not "Aucun enseignement" in str(text_element.find_next().find_next()) :
            absences_table = soup.find_all('table')[whichone]  # Find the first table
            # Extract absences data
            whichone += 2
            rows = absences_table.find_all('tr')
            for row in rows[1:]:  # Skip the header row
                cells = row.find_all('td')
                absence_date = cells[0].text.strip()
                absence_hour = cells[1].text.strip()
                absence_type = cells[2].text.strip()
                absence_class = ' '.join((cells[3].text.strip()).split())
                absence_prof = cells[4].text.strip()
                absence_justified = cells[5].text.strip() == 'Oui'
                absence_reason = cells[6].text.strip()
                absences_data.append({
                    'date': absence_date,
                    'hour': absence_hour,
                    'type': absence_type,
                    'class': absence_class,
                    'prof' : absence_prof,
                    'justified': absence_justified,
                    'reason': absence_reason
                })            
        
        text_element = soup.find(lambda tag: tag.name == 'p' and "par les retards" in tag.text)
        if not "Aucun enseignement" in str(text_element.find_next().find_next()) :
            retards_table = soup.find_all('table')[whichone]  # Find the second table
            # Extract retards data
            whichone += 2
            rows = retards_table.find_all('tr')
            for row in rows[1:]:
                cells = row.find_all('td')
                retard_date = cells[0].text.strip()
                retard_hour = cells[1].text.strip()
                retard_type = cells[2].text.strip()
                retard_class = ' '.join((cells[3].text.strip()).split())
                retard_prof = cells[4].text.strip()
                retard_justified = cells[5].text.strip() == 'Oui'
                retard_reason = cells[6].text.strip()
                retards_data.append({
                    'date': retard_date,
                    'hour': retard_hour,
                    'type': retard_type,
                    'class': retard_class,
                    'prof' : retard_prof,
                    'justified': retard_justified,
                    'reason': retard_reason
                })
        
        text_element = soup.find(lambda tag: tag.name == 'p' and "par les exclusions" in tag.text)
        if not "Aucun enseignement" in str(text_element.find_next().find_next()) :
            exclusions_table = soup.find_all('table')[whichone]  # Find the third table
            # Extract exclusions data
            rows = exclusions_table.find_all('tr')
            for row in rows[1:]:
                cells = row.find_all('td')
                exclusion_date = cells[0].text.strip()
                exclusion_hour = cells[1].text.strip()
                exclusion_type = cells[2].text.strip()
                exclusion_class = ' '.join((cells[3].text.strip()).split())
                exclusion_prof = cells[4].text.strip()
                exclusion_justified = cells[5].text.strip() == 'Oui'
                exclusion_reason = cells[6].text.strip()
                exclusions_data.append({
                    'date': exclusion_date,
                    'hour': exclusion_hour,
                    'type': exclusion_type,
                    'class': exclusion_class,
                    'prof' : exclusion_prof,
                    'justified': exclusion_justified,
                    'reason': exclusion_reason
                })            
                
        # Create a JSON object containing all the data
        result = {
            'absences': absences_data,
            'retards': retards_data,
            'exclusions': exclusions_data
        }

        return result