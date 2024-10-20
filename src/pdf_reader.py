########################################################
# UniceAPI                                             #
# Votre ENT. Dans votre poche.                         #
# Développé par Hugo Meleiro (@hugofnm) / MetrixMedia  #
# Basé sur les travaux de : @itskatt/extracursus       #
# 2022 - 2025                                          #
########################################################

import io
import re

from PyPDF4 import PdfFileReader

SUBJECTS_REGEX = re.compile(r"Code .+ .+ :")
COMMENTS_REGEX = re.compile(r"Séance.+-")
GRADE_REGEX = re.compile(r"((\d+\.\d+ )?\(coeff (\d+\.\d+)\))|(Résultats non publiés)|(ABI ?\(coeff (\d+\.\d+)\))") # note (et coeff)


def remove0s(float_):
    return str(float_).rstrip("0").rstrip(".")

def extract_text(pdf):
    with io.BytesIO(pdf) as f:
        reader = PdfFileReader(f)

        # extraction et premier filtrage du texte
        text = []
        for page in range(reader.getNumPages()):
            page = reader.getPage(page).extractText().splitlines()
            page = page[1:-3]  # on enleve les trucs inutiles
            text.append("\n".join([line.strip() for line in page]))

    return "\n".join(text)

def extract_subjects(text):
    out = []

    # extraction des notes par matiere
    subjects = [m.start() for m in SUBJECTS_REGEX.finditer(text)]

    # Aucunes notes trouvée parce que le pdf est vide
    if not subjects:
        return out

    for i in range(len(subjects) - 1):
        subject = text[subjects[i]:subjects[i + 1]]
        subject = subject.splitlines()

        # 1ere ligne: nom de la matiere
        name: str = subject[0].split(" : ")[-1]

        name = name.replace("?", "'")

        # 2nde ligne: nom du prof + moyenne de la matiere
        # prof
        if "Responsable" in subject[1]:
            teacher = subject[1].split(" : ")[-1]
        else:
            teacher = "Pas de prof"
        # moyenne
        if "Moyenne" in subject[1]:
            average = remove0s(subject[1].split(" : ")[1].split(" ")[0])
        else:
            # average = "Pas de moyenne disponible sur le PDF"
            average = None

        # le reste des lignes de la matière sont les notes + commentaires
        grades_text = subject[3:]

        # extraction des commentaires et des notes
        raw_grades = []
        comments = []
        comment = []
        for line in grades_text:
            # on verifie si notre ligne est le début d'un commentaire de note
            if COMMENTS_REGEX.match(line):
                # si on était en train de remplir un commentaire, on l'ajoute a la liste
                if comment:
                    comments.append(" ".join(comment))
                    comment.clear()

                # ensuite on commence a remplir le suivant
                comment.append(line)
            
            # si on atteind une note, on s'arrete ET on ajoute la note a la liste
            elif grade_match := GRADE_REGEX.match(line):  # walrus operator!
                raw_grades.append(grade_match)
                if comment:
                    comments.append(" ".join(comment))
                    comment.clear()

            # sinon, on ajoute !
            else:
                comment.append(line)

        # a la fin, si il reste des trucs, on les ajoute aussi
        if comment:
            comments.append(" ".join(comment))

        # filtrage des notes
        grades = []
        for match in filter(lambda g: g is not None, raw_grades):
            if match.group(5): # ABI
                grades.append((match.group(),)) 
                
                # faudra mettre au cas ou ABI vaut 0
                """

                grades.append((
                    float(-1), # note
                    float(match.group(6)) # coef
                ))

                """
                
            elif match.groups()[-1] is None and match.group(2): # note (qui existe) + coef
                grades.append((
                    float(match.group(2)), # note
                    float(match.group(3)) # coef
                ))
            elif match.group()=="Résultats non publiés": # "Résultats non publiés"
                grades.append(("(coeff 1.0000)",))
            else: 
                grades.append((match.group(),))

        # calcul de la moyenne si elle n'apparait pas sur le PDF
        if not average:
            filtered = list(filter(lambda g: len(g) > 1, grades))
            if filtered: # on calcule la moyenne uniquement si on a des notes
                divide_by = sum((g[1] for g in filtered)) or 1 # si coef 0
                average = sum((g[0] * g[1] for g in filtered)) / divide_by
                average = f"{remove0s(round(average, 3))} (calculée)"
            else:
                average = "Pas de moyenne disponible"

        # on enelve les 0s inutiles a la fin des notes et coefs
        grades = ((
            remove0s(pair[0]),
            remove0s(pair[1])
        )  if len(pair) == 2 else pair for pair in grades)

        # correspondance du commentaire avec la note
        grades = list(zip(comments, grades))

        out.append({
            "name": name,
            "teacher": teacher,
            "average": average,
            "grades": grades,
            "empty": "empty" if all((g[1][0] == "Résultats non publiés" for g in grades if g)) else ""
        })

    return out

def extract_header_data(text):
    lines = text.split("Nombre d'absences")[0].splitlines()

    adm = avg = pos = ""
    for line in lines:
        if line.startswith("Décision"):
            adm = line.split(":")[-1].strip()
        elif line.startswith("Moyenne"):
            avg = line.split(":")[-1].strip()
        elif line.startswith("Classement"):
            pos = line.split(":")[-1].strip()

    return adm, avg, pos

def get_pdf_data(pdf):
    text = extract_text(pdf)
    adm, avg, pos = extract_header_data(text)

    return {
        "grades": extract_subjects(text),
        "admission": adm,
        "average": avg,
        "position": pos
    }