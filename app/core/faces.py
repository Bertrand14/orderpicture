"""
Face recognition module.
Requires: pip install face_recognition (which needs dlib + cmake)
Gracefully disabled if not installed.
"""

import base64
import json
from io import BytesIO
from pathlib import Path

try:
    import face_recognition
    import numpy as np
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False

DB_PATH = Path(__file__).parent.parent.parent / 'data' / 'faces' / 'database.json'

# Tolerance: lower = stricter matching (0.5 strict, 0.6 default, 0.65 permissive)
TOLERANCE = 0.6


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def load_db():
    if not DB_PATH.exists():
        return {'persons': []}
    try:
        with open(DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'persons': []}


def save_db(db):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def get_known_names():
    """Return sorted list of all known person names."""
    db = load_db()
    return sorted({p['name'] for p in db['persons'] if p.get('name')})


def add_face(name, encoding, thumbnail_b64=None):
    """
    Add (or append) a face encoding to a named person.
    `thumbnail_b64` (base64 JPEG crop) is stored once per person, as a
    visual reference shown on the /faces page — kept on first add only.
    """
    db = load_db()
    enc_list = encoding.tolist() if hasattr(encoding, 'tolist') else list(encoding)
    for person in db['persons']:
        if person['name'] == name:
            person['encodings'].append(enc_list)
            if thumbnail_b64 and not person.get('thumbnail'):
                person['thumbnail'] = thumbnail_b64
            save_db(db)
            return
    person = {'name': name, 'encodings': [enc_list]}
    if thumbnail_b64:
        person['thumbnail'] = thumbnail_b64
    db['persons'].append(person)
    save_db(db)


def delete_person(name):
    db = load_db()
    db['persons'] = [p for p in db['persons'] if p['name'] != name]
    save_db(db)


def rename_person(old_name, new_name):
    """
    Rename a person. If `new_name` already exists, the two entries are
    merged (all encodings combined under the existing name) — this is how
    two separate recognitions of the same person get grouped together.
    Returns False if `old_name` doesn't exist.
    """
    new_name = new_name.strip()
    if not new_name or new_name == old_name:
        return False

    db = load_db()
    old_person = next((p for p in db['persons'] if p['name'] == old_name), None)
    if old_person is None:
        return False

    target = next((p for p in db['persons'] if p['name'] == new_name), None)
    if target is not None:
        # Merge: combine encodings into the existing person, drop the old one
        target['encodings'].extend(old_person['encodings'])
        db['persons'] = [p for p in db['persons'] if p is not old_person]
    else:
        old_person['name'] = new_name

    save_db(db)
    return True


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------

def _build_known(db):
    """Return (list_of_encodings, list_of_names) from the database."""
    if not HAS_FACE_RECOGNITION:
        return [], []
    known_encs, known_names = [], []
    for person in db['persons']:
        for enc in person.get('encodings', []):
            known_encs.append(np.array(enc))
            known_names.append(person['name'])
    return known_encs, known_names


def _crop_b64(image_array, location, size=120):
    """Crop a face from a numpy image array and return as base64 JPEG."""
    from PIL import Image
    top, right, bottom, left = location
    h, w = image_array.shape[:2]
    pad = int((bottom - top) * 0.3)
    top    = max(0, top    - pad)
    bottom = min(h, bottom + pad)
    left   = max(0, left   - pad)
    right  = min(w, right  + pad)
    face_img = Image.fromarray(image_array[top:bottom, left:right])
    face_img.thumbnail((size, size))
    buf = BytesIO()
    face_img.save(buf, format='JPEG', quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def recognize_faces(image_path):
    """
    Detect and recognise all faces in an image.

    Returns a list of dicts:
        name        — known name or None (= unknown)
        crop_b64    — base64 JPEG of the face crop (for display)
        encoding    — raw numpy array (to store if user names it)
        location    — (top, right, bottom, left) tuple
    """
    if not HAS_FACE_RECOGNITION:
        return []

    try:
        image = face_recognition.load_image_file(str(image_path))
        locations = face_recognition.face_locations(image, model='hog')
        if not locations:
            return []
        encodings = face_recognition.face_encodings(image, locations)
    except Exception:
        return []

    db = load_db()
    known_encs, known_names = _build_known(db)

    results = []
    for loc, enc in zip(locations, encodings):
        name = None  # None = unknown

        if known_encs:
            distances = face_recognition.face_distance(known_encs, enc)
            best_idx = int(np.argmin(distances))
            if distances[best_idx] <= TOLERANCE:
                name = known_names[best_idx]

        results.append({
            'name':     name,
            'crop_b64': _crop_b64(image, loc),
            'encoding': enc,
            'location': loc,
        })

    return results
