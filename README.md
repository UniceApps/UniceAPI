![Placeholder UniceAPI](https://i.imgur.com/fct8lte.png)

# `</> UniceAPI`

Le code est fondé sur la base publiée par le dépôt : [@itskatt/extracursus](https://github.com/itskatt/Extracursus). UniceAPI s'appuie sur les fichiers `intra_client.py` et `pdf_reader.py` qui ont été modifiés pour fonctionner avec notre infrastructure.

> [!CAUTION]
> Cette API n'est PAS officielle et n'est pas supportée par l'Université Côte d'Azur ou l'I.U.T. de Nice Côte d'Azur. L'API est fournie "telle quelle" sans garantie d'aucune sorte. 
> L'utilisation de cette API est à vos risques et périls. Nous ne sommes pas responsables des problèmes qui pourraient survenir suite à l'utilisation de cette API (ne faites pas comme moi). 
> Nous vous rappelons que l'accès frauduleux à un système de traitement automatisé de données (STAD) sans autorisation explicite est interdit par la loi.
> **De plus, l'exploitation frauduleuse de ce code (phishing, récupération des logins, ...) est STRICTEMENT INTERDITE.**

> [!WARNING] 
> Si vous décidez d'utiliser votre propre instance de notre API nous ne seront pas en mesure de vous aider et nous ne proposerons aucun support concernant l'utilisation de l'API et les problèmes qui pourrait vous arriver suite à votre propre gestion de cette dernière.

## Déploiement
### Docker (recommandé)
Un fichier `Dockerfile` est disponible pour créer une image Docker de l'API. Pour cela, il suffit de lancer la commande suivante :
```sh
docker build -t uniceapi .
```

Une fois l'image créée, il suffit de lancer un conteneur avec la commande suivante :
```sh
docker run -d -p 5000:5000 uniceapi
```

### Bare-metal
Vous devez installer **Python 3.10 minimum** et **PiP**.<br/>
Ensuite installer les dépendances avec les commandes suivantes :

```sh
pip install -r requirements.txt
```

Une fois les pré-requis en place vous pouvez exécuter le serveur avec la commande suivante :
```sh
python3 run.py
```

Veuillez noter que le serveur est prévu pour fonctionner sur notre infrastructure, il est donc possible que vous deviez modifier le code pour qu'il fonctionne sur votre propre serveur. De plus, il est **nécessaire** de modifier/créer le fichier `secret.json` afin de contenir une clé secrète pour l'API ainsi qu'une liste d'adresses IP autorisées à utiliser certains endpoints de l'API (`/admin`).
```sh
git clone -b main https://github.com/UniceApps/UniceAPI
cd UniceAPI/src
python3 run.py
```
*Cela va lancer le serveur local sur le port 5000.*

> [!WARNING] 
> Il est possible que le serveur ne fonctionne pas à cause d'un problème de certificats SSL. Il est conseillé d'utiliser soit un certificat auto-signé soit un certificat valide (certbot par exemple) pour que l'API fonctionne correctement.

### Déployer rapidement (non recommandé)

> [!TIP]
> Cette méthode est déconseillée car elle n'a pas été testée et peut ne pas fonctionner (modifications de fichiers, dépendances manquantes, ...).

Ok, j'ai compris vous voulez pas vous faire chier à lire la doc, vous voulez juste déployer l'API rapidement. Voici comment faire :

1. Créez un compte sur [Render](https://render.com/) ou [Heroku](https://www.heroku.com/)
2. Cliquez sur le bouton ci-dessous pour déployer l'API sur le service de votre choix.
- [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/UniceApps/UniceAPI)
- [![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/UniceApps/UniceAPI)
3. Créez le fichier `secret.json` conformément à la documentation.
4. Récupérez l'URL de votre API.
5. Coller l'URL dans l'application mobile UniceNotes. (Paramètres > Serveur > Custom > Accepter les avertissements)

> [!WARNING]
> Les serveurs Render, Heroku et autres ne sont pas forcément localisés en France. Un géoblocage est mis en place par l'IUT afin de limiter l'accès à l'ENT depuis l'étranger (surtout sur les sites Satellys GPU). Il est donc possible que l'API ne fonctionne pas si elle est déployée sur un serveur en dehors de la France.

## Documentation
### Schéma de fonctionnement

![Schéma de fonctionnement](https://raw.githubusercontent.com/UniceApps/UniceAPI/main/.github/assets/uniceapi.png)

### Requêtes
Un client doit faire la requête initiale `POST /login` avec le body suivant :
| Paramètre | Utilité | Exemple |
|--|--|--|
| `username: str` | Nom d'utilisateur | `np123456` |
| `password: str` | Mot de passe | `azerty12345` |

Le serveur se connecte à l'ENT et récupère le token d'authentification ainsi qu'un cookie de session. Le token d'authentification est gardé par le serveur (car lié à l'IP du serveur) et le cookie de session est renvoyé au client. L'un sans l'autre ne permet pas d'accéder à l'ENT de l'Université (voyez cela comme une sorte de double authentification basée sur la confiance entre le client et le serveur).

Le token d'authentification ainsi que le cookie sont valables pendant 15 minutes. Si l'utilisateur fait une requête avec un token expiré, le serveur se reconnecte à l'ENT et récupère un nouveau token.

Ensuite vous pouvez utiliser les appels de fonction de l'API.
Voici la liste des URLs en rapport avec la partie IUT :

| URL | Method | Utilité | Réponse |
|--|--|--|--|
| `/avatar` | GET | Renvoie la photo de l'utilisateur | *(l'image)* |
| `/load_pdf` | GET | Télécharge le PDF avec le descriptif des notes sur le cache serveur | OK si PDF téléchargé. Failed sinon |
| `/scrape_pdf` | GET | Récupère les notes du PDF | *(un JSON contenant un array de JSON avec toutes les notes et moyennes)* |
| `/auto_login` | POST | Connexion automatique au CAS et récupération du PDF et des notes | *(un JSON contenant un array de JSON avec toutes les notes et moyennes)* |
| `/absences` | GET | Renvoie les absences, retards et exclusions de l'étudiant | *(un JSON contenant un array de JSON)* |
| `/edt/<username>` | POST | Renvoie l'emploi du temps de l'étudiant | *(un JSON contenant un array de JSON)* |
| `/edt/<username>/nextevent` | POST | Renvoie le prochain événement de l'emploi du temps de l'étudiant | *(un JSON contenant des informations sur le prochain cours)* |
| `/whoami` | GET | Renvoie les informations de l'étudiant | *(un JSON contenant le nom et les semestres de l'étudiant)* |
| `/logout` | GET | Déconnecte l'utilisateur | OK |

Voici la liste des URLs en rapport avec la partie API :
| URL | Utilité | Paramètres | Réponse
|--|--|--|--|
| `/greet/<name>` | Renvoie un message de bienvenue (test) | (str) name | *Bonjour name* |
| `/status` | Envoie des informations utiles pour l'application |  | *un JSON contenant un int version, un str maintenance et un bool disponible* |
| `/admin` | Envoie des informations utiles pour l'application | POST : (str) api_key, (bool) isAvailable, (str) maintenance | POST : OK si la clé et l'adresse IP sont valides , GET : *un JSON contenant un str maintenance et un bool isAvailable* |

### Compte démo
Afin de tester l'API sans avoir à créer un compte, nous avons mis en place un compte démo. Ce compte est accessible avec les identifiants suivants :
| Nom d'utilisateur | Mot de passe |
|--|--|
| demo | demo |

### Compte admin
Afin de gérer l'API, nous avons mis en place un compte admin. L'accès à ce compte est limité à certaines adresses IP et à une clé API. Pour ajouter une adresse IP ou modifier la clé API, il suffit de modifier le fichier `secret.json`.

Ce compte admin n'est pas accessible via l'application mobile UniceNotes. Il est accessible via l'URL `/admin` et permet seulement de modifier la disponibilité de l'API et de mettre en maintenance l'API.

### BugSnag
Nous utilisons BugSnag, en tant que prestataire externe, pour gérer les erreurs de l'API. Vous devez définir une clé d'API dans le fichier `secret.json` pour que l'API puisse envoyer les erreurs à BugSnag.