import os
import re
import shutil
from pathlib import Path
from .metadata import get_metadata, write_exif, IMAGE_EXT
from .faces import HAS_FACE_RECOGNITION, recognize_faces, add_face
from .captioning import HAS_CAPTIONING, describe_image


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------

def _counter_str(n, width=3):
    return str(n).zfill(width)


TOKEN_RESOLVERS = {
    'ANNEE':        lambda m, **_: m['datetime'].strftime('%Y'),
    'MOIS':         lambda m, **_: m['datetime'].strftime('%m'),
    'JOUR':         lambda m, **_: m['datetime'].strftime('%d'),
    'HEURE':        lambda m, **_: m['datetime'].strftime('%H'),
    'MIN':          lambda m, **_: m['datetime'].strftime('%M'),
    'SEC':          lambda m, **_: m['datetime'].strftime('%S'),
    'NOM_ORIGINAL': lambda m, **_: m.get('original_stem', 'fichier'),
    'APPAREIL':     lambda m, **_: sanitize_part(m.get('camera', 'Inconnu')),
    'LIEU':         lambda m, **_: sanitize_part(m.get('city', '')),
    'PAYS':         lambda m, **_: sanitize_part(m.get('country', '')),
    'COMPTEUR':     lambda m, counter=0, **_: _counter_str(counter),
}


def apply_tokens(tokens, meta, counter=0):
    """
    Build a string from a list of token dicts and metadata.
    Token dict format: {"type": "field"|"text", "value": "..."}
    """
    parts = []
    for tok in tokens:
        t = tok.get('type', 'text')
        v = tok.get('value', '')
        if t == 'field' and v in TOKEN_RESOLVERS:
            parts.append(TOKEN_RESOLVERS[v](meta, counter=counter))
        else:
            parts.append(v)
    return ''.join(parts)


def sanitize_part(text):
    """Remove filesystem-unsafe characters from a path component."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text or '')
    return text.strip('. ') or ''


def sanitize_filename(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    return name.strip('. ') or 'sans_nom'


# ---------------------------------------------------------------------------
# Unique path helper
# ---------------------------------------------------------------------------

def get_unique_path(dest_dir, filename):
    path = dest_dir / filename
    if not path.exists():
        return path
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while True:
        candidate = dest_dir / f"{stem}({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Single file processor
# ---------------------------------------------------------------------------

def process_file(filepath, profile, counter=0, face_callback=None):
    """
    Process one file according to the profile.

    face_callback(face_dict) is called for each *unknown* face and must
    return the name the user provided (str) or '' to skip.
    It blocks until the user responds — the caller is responsible for
    wiring up the SSE pause/resume mechanism.

    Returns a result dict.
    """
    filepath = Path(filepath)
    result = {
        'original': str(filepath),
        'filename': filepath.name,
        'status': 'ok',
        'error': None,
        'new_path': None,
        'metadata_source': None,
        'json_deleted': False,
        'exif_written': False,
        'faces_found': [],
        'caption_generated': None,
    }

    try:
        meta = get_metadata(filepath)
        result['metadata_source'] = meta.get('source', 'unknown')

        file_type = meta['file_type']

        # Destination root per file type
        if file_type == 'image':
            dest_root = profile.get('dest_images') or profile.get('dest_root', '')
        elif file_type == 'video':
            dest_root = profile.get('dest_videos') or profile.get('dest_root', '')
        else:
            dest_root = profile.get('dest_others') or profile.get('dest_root', '')

        if not dest_root:
            raise ValueError("Aucun dossier de destination configuré.")

        # Build subfolder from folder tokens
        folder_tokens = profile.get('folder_tokens', [
            {'type': 'field', 'value': 'ANNEE'},
            {'type': 'text',  'value': '/'},
            {'type': 'field', 'value': 'MOIS'},
            {'type': 'text',  'value': '/'},
            {'type': 'field', 'value': 'JOUR'},
        ])
        subfolder = apply_tokens(folder_tokens, meta, counter=counter)
        # Normalize path separators
        subfolder = subfolder.replace('\\', '/')
        dest_dir = Path(dest_root)
        for part in subfolder.split('/'):
            if part:
                dest_dir = dest_dir / sanitize_part(part)

        dest_dir.mkdir(parents=True, exist_ok=True)

        # Build filename from filename tokens
        filename_tokens = profile.get('filename_tokens', [
            {'type': 'field', 'value': 'NOM_ORIGINAL'},
        ])
        new_stem = apply_tokens(filename_tokens, meta, counter=counter)
        new_stem = sanitize_filename(new_stem)
        if not new_stem:
            new_stem = meta['original_stem'] or 'fichier'

        new_filename = f"{new_stem}.{meta['extension']}"
        dest_path = get_unique_path(dest_dir, new_filename)

        # Move or copy
        action = profile.get('action', 'copy')
        if action == 'move':
            shutil.move(str(filepath), str(dest_path))
        else:
            shutil.copy2(str(filepath), str(dest_path))

        result['new_path'] = str(dest_path)

        # --- Face recognition (images only, if enabled) ---
        use_faces = (
            profile.get('face_recognition', False)
            and HAS_FACE_RECOGNITION
            and file_type == 'image'
            and dest_path.suffix.lower() in IMAGE_EXT
        )
        if use_faces:
            # Only run if no people already identified from Google JSON
            has_people_from_json = bool(meta.get('people')) and meta.get('source') == 'google_json'
            if not has_people_from_json:
                faces = recognize_faces(dest_path)
                for face in faces:
                    if face['name'] is not None:
                        # Already known
                        if face['name'] not in meta['people']:
                            meta['people'].append(face['name'])
                        result['faces_found'].append(face['name'])
                    else:
                        # Unknown face — pause and ask user
                        if face_callback is not None:
                            name = face_callback(face)
                        else:
                            name = ''
                        if name:
                            add_face(name, face['encoding'], face.get('crop_b64'))
                            if name not in meta['people']:
                                meta['people'].append(name)
                            result['faces_found'].append(name)
                        else:
                            result['faces_found'].append('Inconnu')

        # --- Automatic AI description (images only, if enabled and missing) ---
        use_caption = (
            profile.get('auto_caption', False)
            and HAS_CAPTIONING
            and file_type == 'image'
            and dest_path.suffix.lower() in IMAGE_EXT
            and not meta.get('description')
        )
        if use_caption:
            lang = profile.get('caption_language', 'fi')
            description, keywords = describe_image(dest_path, lang)
            if description:
                meta['description'] = description
                if not meta.get('keywords'):
                    meta['keywords'] = keywords
                result['caption_generated'] = description

        # Write EXIF for supported images
        if file_type == 'image' and dest_path.suffix.lower() in IMAGE_EXT:
            success = write_exif(dest_path, meta)
            result['exif_written'] = success

        # Delete Google JSON sidecar after successful EXIF write (or for videos)
        json_path = meta.get('google_json')
        if json_path and profile.get('delete_json', True):
            if file_type == 'image' and result['exif_written']:
                try:
                    os.remove(json_path)
                    result['json_deleted'] = True
                except Exception:
                    pass
            elif file_type == 'video':
                # For videos we can't embed metadata easily, keep JSON by default
                pass

    except Exception as e:
        result['status'] = 'error'
        result['error'] = str(e)

    return result
