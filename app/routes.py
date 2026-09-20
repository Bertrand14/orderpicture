import json
import os
import queue
import re
import threading
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, render_template, request, send_file, stream_with_context
from PIL import Image

from .core.scanner import scan_summary
from .core.sorter import process_file
from .core.faces import (
    HAS_FACE_RECOGNITION, get_known_names, add_face, delete_person, rename_person, load_db
)
from .core.captioning import HAS_CAPTIONING, LANGUAGE_LABELS
from .core.blogideas import (
    find_clusters, DEFAULT_MIN_CLUSTER_SIZE, DEFAULT_MAX_GAP_DAYS, DEFAULT_GPS_MAX_KM
)
from .core.metadata import IMAGE_EXT_ALL

bp = Blueprint('main', __name__)

DATA_DIR    = Path(__file__).parent.parent / 'data'
PROFILES_DIR = DATA_DIR / 'profiles'

# Active processing queues keyed by session_id
_queues = {}

# Face pause/resume: per session, one Event + one answer slot
_face_events  = {}   # session_id -> threading.Event
_face_answers = {}   # session_id -> str (name provided by user)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/profile')
@bp.route('/profile/<name>')
def profile(name=None):
    return render_template('profile.html', profile_name=name or '')


@bp.route('/process')
def process():
    return render_template('process.html')


@bp.route('/faces')
def faces_page():
    return render_template('faces.html')


@bp.route('/billets')
def billets_page():
    return render_template('billets.html')


# ---------------------------------------------------------------------------
# API — filesystem helpers
# ---------------------------------------------------------------------------

@bp.route('/api/browse', methods=['POST'])
def browse_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title='Sélectionner un dossier')
        root.destroy()
        return jsonify({'path': folder or ''})
    except Exception as e:
        return jsonify({'path': '', 'error': str(e)})


@bp.route('/api/scan', methods=['POST'])
def api_scan():
    data = request.json or {}
    folder = data.get('folder', '').strip()
    subdirs = data.get('subdirs', True)
    if not folder or not os.path.isdir(folder):
        return jsonify({'error': 'Dossier introuvable : ' + folder}), 400
    try:
        return jsonify(scan_summary(folder, subdirs))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# API — billets (blog-post candidate detector)
# ---------------------------------------------------------------------------

@bp.route('/api/billets/scan', methods=['POST'])
def api_billets_scan():
    data = request.json or {}
    folder = data.get('folder', '').strip()
    subdirs = data.get('subdirs', True)
    if not folder or not os.path.isdir(folder):
        return jsonify({'error': 'Dossier introuvable : ' + folder}), 400

    min_cluster_size = int(data.get('min_cluster_size') or DEFAULT_MIN_CLUSTER_SIZE)
    max_gap_days      = int(data.get('max_gap_days') or DEFAULT_MAX_GAP_DAYS)
    gps_max_km        = float(data.get('gps_max_km') or DEFAULT_GPS_MAX_KM)

    try:
        clusters, total_files_scanned = find_clusters(
            folder, subdirs,
            min_cluster_size=min_cluster_size,
            max_gap_days=max_gap_days,
            gps_max_km=gps_max_km,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    for cluster in clusters:
        cluster['thumbnails'] = [
            f"/api/billets/thumb?folder={quote(folder)}&path={quote(p)}"
            for p in cluster.pop('thumbnail_paths')
        ]

    return jsonify({
        'folder': folder,
        'total_files_scanned': total_files_scanned,
        'clusters': clusters,
    })


@bp.route('/api/billets/thumb')
def api_billets_thumb():
    folder = request.args.get('folder', '')
    path = request.args.get('path', '')
    if not folder or not path:
        return '', 404

    try:
        root = Path(folder).resolve()
        target = Path(path).resolve()
        target.relative_to(root)
    except (ValueError, OSError):
        return '', 403

    if target.suffix.lower() not in IMAGE_EXT_ALL or not target.is_file():
        return '', 404

    try:
        img = Image.open(target).convert('RGB')
        img.thumbnail((320, 320))
        buf = BytesIO()
        img.save(buf, format='JPEG', quality=80)
        buf.seek(0)
    except Exception:
        return '', 404

    resp = send_file(buf, mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'public, max-age=3600'
    return resp


# ---------------------------------------------------------------------------
# API — profiles
# ---------------------------------------------------------------------------

@bp.route('/api/profiles', methods=['GET'])
def get_profiles():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profiles = []
    for f in sorted(PROFILES_DIR.glob('*.json')):
        try:
            with open(f, encoding='utf-8') as fh:
                profiles.append(json.load(fh))
        except Exception:
            pass
    return jsonify(profiles)


@bp.route('/api/profiles/<name>', methods=['GET'])
def get_profile(name):
    path = PROFILES_DIR / f'{_safe_name(name)}.json'
    if not path.exists():
        return jsonify({'error': 'Profil introuvable'}), 404
    with open(path, encoding='utf-8') as f:
        return jsonify(json.load(f))


@bp.route('/api/profiles', methods=['POST'])
def save_profile():
    data = request.json or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Nom du profil requis'}), 400
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROFILES_DIR / f'{_safe_name(name)}.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True, 'name': name})


@bp.route('/api/profiles/<name>', methods=['DELETE'])
def delete_profile(name):
    path = PROFILES_DIR / f'{_safe_name(name)}.json'
    if path.exists():
        path.unlink()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# API — processing (with face pause/resume)
# ---------------------------------------------------------------------------

@bp.route('/api/process/start', methods=['POST'])
def start_process():
    data = request.json or {}
    session_id = data.get('session_id', 'default')
    files      = data.get('files', [])
    profile    = data.get('profile', {})

    if not files:
        return jsonify({'error': 'Aucun fichier à traiter'}), 400

    q = queue.Queue()
    _queues[session_id] = q

    use_faces = profile.get('face_recognition', False) and HAS_FACE_RECOGNITION

    def make_face_callback():
        """
        Called from the processing thread when an unknown face is found.
        Sends a 'face_pause' SSE event, then BLOCKS until the user responds
        via POST /api/faces/respond/<session_id>.
        Returns the user-provided name (str, possibly empty).
        """
        event = threading.Event()
        _face_events[session_id] = event

        def callback(face):
            q.put({
                'type':           'face_pause',
                'crop_b64':       face['crop_b64'],
                'known_names':    get_known_names(),
            })
            event.wait(timeout=300)   # wait up to 5 min for user input
            event.clear()
            return _face_answers.pop(session_id, '')

        return callback

    def run():
        total = len(files)
        ok = errors = 0
        cb = make_face_callback() if use_faces else None
        for i, filepath in enumerate(files):
            result = process_file(filepath, profile, counter=i + 1, face_callback=cb)
            if result['status'] == 'ok':
                ok += 1
            else:
                errors += 1
            q.put({'type': 'progress', 'index': i + 1, 'total': total, 'result': result})
        q.put({'type': 'done', 'ok': ok, 'errors': errors, 'total': total})
        # Clean up
        _face_events.pop(session_id, None)
        _face_answers.pop(session_id, None)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({'ok': True, 'session_id': session_id})


@bp.route('/api/process/stream/<session_id>')
def stream_progress(session_id):
    q = _queues.get(session_id)
    if q is None:
        return jsonify({'error': 'Session inconnue'}), 404

    def generate():
        while True:
            msg = q.get()
            yield f'data: {json.dumps(msg, ensure_ascii=False)}\n\n'
            if msg.get('type') == 'done':
                _queues.pop(session_id, None)
                break

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


# ---------------------------------------------------------------------------
# API — face identification (called from browser when user names a face)
# ---------------------------------------------------------------------------

@bp.route('/api/faces/respond/<session_id>', methods=['POST'])
def face_respond(session_id):
    """
    Receive the user's answer for an unknown face and unblock the
    processing thread.
    """
    data = request.json or {}
    name = data.get('name', '').strip()

    _face_answers[session_id] = name
    event = _face_events.get(session_id)
    if event:
        event.set()

    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# API — face database management
# ---------------------------------------------------------------------------

@bp.route('/api/faces', methods=['GET'])
def list_faces():
    db = load_db()
    persons = [{'name': p['name'], 'count': len(p.get('encodings', [])), 'thumbnail': p.get('thumbnail')}
               for p in db.get('persons', [])]
    return jsonify({
        'available': HAS_FACE_RECOGNITION,
        'persons': persons,
    })


@bp.route('/api/faces/<name>', methods=['DELETE'])
def remove_face(name):
    delete_person(name)
    return jsonify({'ok': True})


@bp.route('/api/faces/<name>/rename', methods=['POST'])
def rename_face(name):
    """
    Rename a person. If the new name already matches another known person,
    the two are merged (encodings combined under the existing name).
    """
    data = request.json or {}
    new_name = data.get('new_name', '').strip()
    if not new_name:
        return jsonify({'error': 'Nouveau nom requis'}), 400

    ok = rename_person(name, new_name)
    if not ok:
        return jsonify({'error': 'Personne introuvable ou nom inchangé'}), 400

    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# API — automatic captioning status
# ---------------------------------------------------------------------------

@bp.route('/api/captioning', methods=['GET'])
def captioning_status():
    return jsonify({
        'available': HAS_CAPTIONING,
        'languages': LANGUAGE_LABELS,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_name(name):
    return re.sub(r'[^\w\s\-]', '', name).strip().replace(' ', '_')
