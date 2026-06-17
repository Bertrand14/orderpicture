import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

IMAGE_EXT = {'.jpg', '.jpeg', '.tif', '.tiff'}
IMAGE_EXT_ALL = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff'}
VIDEO_EXT = {'.mp4', '.mkv', '.mov', '.avi', '.flv', '.wmv', '.3gp', '.m4v', '.mts', '.m2ts'}
SKIP_EXT = {'.json', '.sfk', '.trashinfo', '.db', '.ini', '.nomedia'}


# ---------------------------------------------------------------------------
# Google Photos JSON
# ---------------------------------------------------------------------------

def find_google_json(filepath):
    """Return path to the Google Photos supplemental JSON, or None."""
    p = Path(filepath)
    candidates = [
        str(p) + '.supplemental-metadata.json',
        str(p) + '.json',
    ]
    # Google sometimes truncates long filenames at ~46 chars before the extension
    # e.g. IMG_20241201_200724_BURST28.jpg → IMG_20241201_200724_BURST28.jpg.supplem...json
    parent = p.parent
    stem_prefix = p.stem[:40]
    for f in parent.glob('*.json'):
        name = f.name
        if name.startswith(stem_prefix) and ('supplemental' in name or name == p.name + '.json'):
            candidates.append(str(f))

    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def read_google_json(json_path):
    """Parse a Google Photos supplemental JSON file."""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}

    result = {}

    if 'photoTakenTime' in data:
        try:
            ts = int(data['photoTakenTime']['timestamp'])
            result['datetime'] = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            pass

    for geo_key in ('geoData', 'geoDataExif'):
        geo = data.get(geo_key, {})
        lat = geo.get('latitude', 0)
        lon = geo.get('longitude', 0)
        if lat != 0 or lon != 0:
            result['gps_lat'] = lat
            result['gps_lon'] = lon
            break

    result['people'] = [p['name'] for p in data.get('people', []) if 'name' in p]

    desc = data.get('description', '').strip()
    if desc:
        result['description'] = desc

    return result


# ---------------------------------------------------------------------------
# EXIF reading
# ---------------------------------------------------------------------------

def _dms_to_decimal(dms, ref):
    if not dms or not ref:
        return None
    try:
        d = dms[0][0] / dms[0][1]
        m = dms[1][0] / dms[1][1]
        s = dms[2][0] / dms[2][1]
        dec = d + m / 60 + s / 3600
        if ref in (b'S', b'W'):
            dec = -dec
        return dec
    except Exception:
        return None


def _decode(val):
    if isinstance(val, bytes):
        return val.decode('utf-8', errors='ignore').rstrip('\x00')
    return str(val) if val else ''


def read_exif(filepath):
    """Read EXIF data from an image. Returns a dict."""
    if not HAS_PIEXIF:
        return {}
    result = {}
    try:
        exif = piexif.load(str(filepath))

        # Date
        for ifd, tag in [('Exif', piexif.ExifIFD.DateTimeOriginal),
                          ('0th',  piexif.ImageIFD.DateTime)]:
            val = exif.get(ifd, {}).get(tag)
            if val:
                try:
                    result['datetime'] = datetime.strptime(_decode(val), '%Y:%m:%d %H:%M:%S')
                    break
                except ValueError:
                    pass

        # GPS
        gps = exif.get('GPS', {})
        lat = _dms_to_decimal(gps.get(piexif.GPSIFD.GPSLatitude),
                              gps.get(piexif.GPSIFD.GPSLatitudeRef))
        lon = _dms_to_decimal(gps.get(piexif.GPSIFD.GPSLongitude),
                              gps.get(piexif.GPSIFD.GPSLongitudeRef))
        if lat is not None and lon is not None:
            result['gps_lat'] = lat
            result['gps_lon'] = lon

        # Camera
        make  = _decode(exif.get('0th', {}).get(piexif.ImageIFD.Make, b''))
        model = _decode(exif.get('0th', {}).get(piexif.ImageIFD.Model, b''))
        cam = f"{make} {model}".strip()
        if cam:
            result['camera'] = cam

        # Description
        desc = _decode(exif.get('0th', {}).get(piexif.ImageIFD.ImageDescription, b''))
        if desc:
            result['description'] = desc

        # Keywords (XPKeywords - Windows/IPTC style, UTF-16LE)
        kw_raw = exif.get('0th', {}).get(40094)
        if kw_raw:
            try:
                kw_str = kw_raw.decode('utf-16-le', errors='ignore').rstrip('\x00')
                result['keywords'] = [k for k in kw_str.split(';') if k]
            except Exception:
                pass

    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Filename date parsing
# ---------------------------------------------------------------------------

_FILENAME_PATTERNS = [
    r'(\d{4})(\d{2})(\d{2})[_\-T](\d{2})(\d{2})(\d{2})',   # YYYYMMDD_HHMMSS
    r'(\d{4})-(\d{2})-(\d{2})[_\-T](\d{2})-(\d{2})-(\d{2})',  # YYYY-MM-DD_HH-MM-SS
    r'(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})',          # YYYYMMDDHHmmSS (no sep)
]

def read_filename_date(filename):
    for pat in _FILENAME_PATTERNS:
        m = re.search(pat, filename)
        if m:
            try:
                return datetime(*[int(x) for x in m.groups()])
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------------------
# Unified metadata getter
# ---------------------------------------------------------------------------

def get_metadata(filepath):
    """
    Return the best available metadata for a file.
    Priority: Google Photos JSON > EXIF > filename > mtime
    """
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    meta = {
        'people': [],
        'keywords': [],
        'source': 'none',
        'original_name': filepath.name,
        'original_stem': filepath.stem,
        'extension': ext.lstrip('.').lower(),
    }

    if ext in IMAGE_EXT_ALL:
        meta['file_type'] = 'image'
    elif ext in VIDEO_EXT:
        meta['file_type'] = 'video'
    else:
        meta['file_type'] = 'other'

    # 1. Google Photos JSON
    json_path = find_google_json(filepath)
    if json_path:
        gdata = read_google_json(json_path)
        meta.update(gdata)
        meta['google_json'] = json_path
        if 'datetime' in gdata:
            meta['source'] = 'google_json'

    # 2. EXIF (images only, fill in missing fields)
    if ext in IMAGE_EXT_ALL:
        exif = read_exif(filepath)
        if 'datetime' not in meta and 'datetime' in exif:
            meta['source'] = 'exif'
        for k, v in exif.items():
            if k not in meta:
                meta[k] = v

    # 3. Filename
    if 'datetime' not in meta:
        d = read_filename_date(filepath.name)
        if d:
            meta['datetime'] = d
            meta['source'] = 'filename'

    # 4. File mtime (last resort)
    if 'datetime' not in meta:
        meta['datetime'] = datetime.fromtimestamp(filepath.stat().st_mtime)
        meta['source'] = 'mtime'

    return meta


# ---------------------------------------------------------------------------
# EXIF writing
# ---------------------------------------------------------------------------

def _decimal_to_dms(decimal):
    d = int(decimal)
    m = int((decimal - d) * 60)
    s_float = ((decimal - d) * 60 - m) * 60
    s = round(s_float * 10000)
    return [(d, 1), (m, 1), (s, 10000)]


def write_exif(filepath, meta):
    """Write metadata back to a JPEG/TIFF EXIF. Returns True on success."""
    if not HAS_PIEXIF:
        return False

    filepath = Path(filepath)
    if filepath.suffix.lower() not in IMAGE_EXT:
        return False

    try:
        try:
            exif_dict = piexif.load(str(filepath))
        except Exception:
            exif_dict = {'0th': {}, 'Exif': {}, 'GPS': {}, 'Interop': {}, '1st': {}}

        dt = meta.get('datetime')
        if dt:
            date_str = dt.strftime('%Y:%m:%d %H:%M:%S').encode()
            exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = date_str
            exif_dict['0th'][piexif.ImageIFD.DateTime] = date_str

        lat = meta.get('gps_lat')
        lon = meta.get('gps_lon')
        if lat is not None and lon is not None:
            exif_dict['GPS'] = {
                piexif.GPSIFD.GPSLatitudeRef:  b'N' if lat >= 0 else b'S',
                piexif.GPSIFD.GPSLatitude:     _decimal_to_dms(abs(lat)),
                piexif.GPSIFD.GPSLongitudeRef: b'E' if lon >= 0 else b'W',
                piexif.GPSIFD.GPSLongitude:    _decimal_to_dms(abs(lon)),
            }

        desc = meta.get('description', '')
        if desc:
            exif_dict['0th'][piexif.ImageIFD.ImageDescription] = desc.encode('utf-8')

        tags = list(meta.get('people', [])) + list(meta.get('keywords', []))
        if tags:
            kw = ';'.join(tags).encode('utf-16-le') + b'\x00\x00'
            exif_dict['0th'][40094] = kw

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(filepath))
        return True

    except Exception:
        return False
