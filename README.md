# MediaSort

Application locale pour trier, organiser et enrichir une photothèque familiale (photos et vidéos), pensée pour simplifier la rédaction de billets de blog familial.

Tout fonctionne **en local** — aucune donnée n'est envoyée sur Internet (à l'exception du téléchargement initial des modèles IA depuis Hugging Face, lors de la première utilisation de la description automatique).

---

## Fonctionnalités

- **Tri automatique** des fichiers médias par date, en lisant dans l'ordre de priorité :
  1. les métadonnées JSON d'un export Google Photos (date exacte, GPS, personnes déjà identifiées)
  2. les métadonnées EXIF déjà présentes dans le fichier
  3. le nom du fichier (formats `IMG_YYYYMMDD_HHMMSS`, etc.)
  4. la date de modification du fichier (dernier recours)
- **Organisation et nommage personnalisables** via un constructeur de jetons par glisser-déposer (année, mois, jour, lieu, appareil, nom original, texte libre…)
- **Reconnaissance faciale** optionnelle : le traitement se met en pause à chaque nouveau visage détecté pour le nommer (ou sélectionner une personne déjà connue) ; les visages peuvent ensuite être renommés ou fusionnés sur la page *Visages*
- **Description automatique par IA** (modèle BLIP) si aucune description n'existe déjà, avec traduction au choix (finnois, français, ou anglais sans traduction)
- **Suppression automatique** des fichiers JSON Google Photos une fois leurs métadonnées écrites avec succès dans l'EXIF
- **Profils réutilisables** : chaque combinaison de réglages (architecture de dossiers, nommage, options) peut être sauvegardée et réappliquée
- Pensé pour les **gros volumes** (testé sur des dizaines de milliers de fichiers) avec un traitement entièrement automatique, sans confirmation fichier par fichier

---

## Installation

Prérequis : Python 3.10+, ~2 Go d'espace disque (dépendances IA : torch, transformers, dlib).

```bash
git clone https://github.com/Bertrand14/orderpicture.git
cd orderpicture
./start.sh
```

Le script `start.sh` :
1. crée un environnement virtuel Python (`venv/`) s'il n'existe pas déjà ;
2. installe les dépendances (`requirements.txt`), avec une variante CPU de PyTorch (plus légère que la version par défaut) ;
3. démarre le serveur et ouvre automatiquement le navigateur sur `http://localhost:5050`.

Les lancements suivants sont immédiats : `./start.sh` suffit.

---

## Utilisation

1. **Importer** — indiquer le dossier source et les dossiers de destination (photos / vidéos / autres), avec ou sans sous-dossiers
2. **Profil** — choisir un profil existant ou en créer un nouveau (page *Profils*)
3. **Analyser** — l'application scanne le dossier et affiche le nombre de fichiers par type
4. **Traiter** — lance le tri ; si la reconnaissance faciale est activée, une fenêtre apparaît à chaque visage inconnu pour le nommer
5. **Rapport** — à la fin du traitement, un journal détaillé est consultable et exportable

---

## Profils et constructeur de jetons

Un profil définit comment les fichiers sont renommés et organisés, par glisser-déposer de jetons dans deux zones :

- **Structure des dossiers** — chaque jeton devient un niveau de dossier (ex. `ANNÉE / MOIS / JOUR`)
- **Nom du fichier** — les jetons et du texte libre se combinent (ex. `Vacances en Finlande - ANNÉE_MOIS_JOUR-HEURE_MIN_SEC`)

Jetons disponibles : `ANNEE`, `MOIS`, `JOUR`, `HEURE`, `MIN`, `SEC`, `NOM_ORIGINAL`, `LIEU`, `PAYS`, `APPAREIL`, `COMPTEUR`, ainsi que du texte libre.

Chaque profil peut aussi définir : l'action (copier/déplacer), la suppression des JSON Google Photos, l'activation de la reconnaissance faciale et de la description IA (avec sa langue).

---

## Reconnaissance faciale

Désactivée par défaut, à activer dans le profil. Fonctionnement :

- Les personnes déjà identifiées dans un JSON Google Photos sont reprises directement (pas de nouvelle reconnaissance nécessaire)
- Pour les autres photos, chaque visage détecté est comparé à la base locale (`data/faces/database.json`)
- Visage connu → ajouté automatiquement aux métadonnées
- Visage inconnu → le traitement **se met en pause**, une vignette du visage s'affiche, et il est possible de saisir un nouveau nom ou de sélectionner une personne déjà connue

Sur la page **Visages**, chaque personne peut être renommée ou supprimée. Renommer une personne vers un nom déjà existant **fusionne** automatiquement les deux entrées (utile si une même personne a été enregistrée deux fois sous des noms différents).

---

## Description automatique par IA

Utilise le modèle [`Salesforce/blip-image-captioning-base`](https://huggingface.co/Salesforce/blip-image-captioning-base) pour générer une description en anglais, traduite ensuite (modèles Helsinki-NLP) si la langue choisie n'est pas l'anglais.

Ne se déclenche que si **aucune description n'existe déjà** (ni dans le JSON Google Photos, ni dans l'EXIF) — pas de travail redondant. Les modèles sont téléchargés automatiquement au premier usage et mis en cache localement.

---

## Confidentialité

Le dossier `data/` (profils personnels, base de visages avec encodages biométriques) n'est **jamais versionné** — il est exclu via `.gitignore` et reste strictement local à la machine.

---

## Structure du projet

```
app/
├── core/
│   ├── metadata.py      # Lecture/écriture EXIF, parsing JSON Google Photos
│   ├── scanner.py        # Scan récursif des dossiers
│   ├── sorter.py          # Moteur de tri, application des jetons, renommage
│   ├── faces.py            # Base de visages, reconnaissance, fusion/renommage
│   └── captioning.py        # Description IA (BLIP) + traduction
├── routes.py                 # Routes Flask et API
├── templates/                 # Interface (Jinja2 + Tailwind CSS)
└── static/                     # CSS/JS (SortableJS pour le glisser-déposer)
data/                            # Données locales non versionnées (profils, visages)
run.py                            # Point d'entrée (ouvre le navigateur automatiquement)
start.sh                          # Script d'installation et de lancement
requirements.txt                   # Dépendances Python
```

---

## Stack technique

Flask · Pillow / piexif (EXIF) · face_recognition / dlib (reconnaissance faciale) · PyTorch + Transformers (BLIP, traduction Helsinki-NLP) · SortableJS · Tailwind CSS
