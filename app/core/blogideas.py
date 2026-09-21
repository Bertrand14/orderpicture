"""
Blog-post candidate detector.

Re-reads an already-sorted media library (EXIF written by `sorter.py`:
date, GPS, AI caption/keywords) and looks for groups of photos/videos from
the same day — or several consecutive days showing the same guessed
activity — worth turning into a family blog post. Read-only: nothing is
written back to disk.
"""

import json
import math
import re
from pathlib import Path

from .metadata import get_metadata, IMAGE_EXT_ALL, VIDEO_EXT
from .scanner import scan_folder
from .faces import get_known_names

ACTIVITY_DICT_PATH = Path(__file__).parent.parent.parent / 'data' / 'activity_categories.json'

DEFAULT_MAX_GAP_DAYS     = 1
DEFAULT_GPS_MAX_KM       = 50
DEFAULT_MIN_CLUSTER_SIZE = 3
MAX_THUMBNAILS           = 8


# ---------------------------------------------------------------------------
# Activity dictionary
# ---------------------------------------------------------------------------

def load_activity_dictionary():
    """Load the activity-category dictionary from data/activity_categories.json."""
    try:
        with open(ACTIVITY_DICT_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('categories', [])
    except Exception:
        return []


def _compile_category_patterns(categories):
    """
    Pre-compile a case-insensitive, word-boundary regex per keyword, grouped
    by category id, across all languages (fr/fi/en) — a description or
    keyword list can be in any of the three depending on which profile
    produced it.
    """
    compiled = {}
    for cat in categories:
        terms = set()
        for lang_terms in cat.get('keywords', {}).values():
            terms.update(lang_terms)
        patterns = [re.compile(r'\b' + re.escape(term.lower()) + r'\b') for term in terms]
        compiled[cat['id']] = {
            'label': cat.get('label', {}),
            'patterns': list(zip(terms, patterns)),
        }
    return compiled


# ---------------------------------------------------------------------------
# People vs. activity-keyword split
# ---------------------------------------------------------------------------

def _split_people_and_keywords(raw_keywords, known_names_lower):
    """
    `raw_keywords` is the flat list read back from XPKeywords (people names
    and caption keywords are merged there by `sorter.write_exif`). Anything
    matching a known face-database name (case-insensitive) is a person;
    everything else is treated as an activity keyword.
    """
    people, keywords = [], []
    for kw in raw_keywords or []:
        if kw.lower() in known_names_lower:
            people.append(kw)
        else:
            keywords.append(kw)
    return people, keywords


# ---------------------------------------------------------------------------
# Activity guessing
# ---------------------------------------------------------------------------

def guess_activity(description, keywords, compiled_categories):
    """
    Match `description` (free text) and `keywords` (list of words) against
    the compiled activity dictionary.

    Returns dict: category_id (None if nothing matched), label (dict or None),
    matched_keywords (sorted list of distinct matched terms for the winner),
    confidence (0..1 — how much the winning category dominates all matches),
    confidence_level ('none'/'low'/'medium'/'high').
    """
    text = ' '.join(filter(None, [description] + list(keywords or []))).lower()

    matches = {}  # category_id -> set of matched terms
    if text.strip():
        for cat_id, cat in compiled_categories.items():
            found = {term for term, pattern in cat['patterns'] if pattern.search(text)}
            if found:
                matches[cat_id] = found

    total_matches = sum(len(terms) for terms in matches.values())
    if total_matches == 0:
        return {
            'category_id': None,
            'label': None,
            'matched_keywords': [],
            'confidence': 0.0,
            'confidence_level': 'none',
        }

    best_id = max(matches, key=lambda cid: len(matches[cid]))
    best_terms = matches[best_id]
    confidence = len(best_terms) / total_matches

    if len(best_terms) >= 3 and confidence >= 0.6:
        level = 'high'
    elif len(best_terms) >= 2 and confidence >= 0.4:
        level = 'medium'
    else:
        level = 'low'

    return {
        'category_id': best_id,
        'label': compiled_categories[best_id]['label'],
        'matched_keywords': sorted(best_terms),
        'confidence': round(confidence, 2),
        'confidence_level': level,
    }


# ---------------------------------------------------------------------------
# GPS helper
# ---------------------------------------------------------------------------

def _haversine_km(coord1, coord2):
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _gps_centroid(records):
    pts = [(r['gps_lat'], r['gps_lon']) for r in records
           if r.get('gps_lat') is not None and r.get('gps_lon') is not None]
    if not pts:
        return None
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

def _collect_file_records(folder, include_subdirs, known_names_lower):
    records = []
    for path_str in scan_folder(folder, include_subdirs):
        path = Path(path_str)
        ext = path.suffix.lower()
        if ext not in IMAGE_EXT_ALL and ext not in VIDEO_EXT:
            continue

        meta = get_metadata(path)
        dt = meta.get('datetime')
        if dt is None:
            continue

        people, keywords = _split_people_and_keywords(meta.get('keywords'), known_names_lower)
        records.append({
            'path':        str(path),
            'file_type':   meta['file_type'],
            'day':         dt.date(),
            'gps_lat':     meta.get('gps_lat'),
            'gps_lon':     meta.get('gps_lon'),
            'description': meta.get('description', ''),
            'people':      people,
            'keywords':    keywords,
        })
    return records


def _group_by_day(records):
    days = {}
    for r in records:
        days.setdefault(r['day'], []).append(r)
    return days


def _build_day_summary(day_date, records, compiled_categories):
    description = ' . '.join(r['description'] for r in records if r['description'])
    keywords = [kw for r in records for kw in r['keywords']]
    people = sorted({p for r in records for p in r['people']})
    guess = guess_activity(description, keywords, compiled_categories)

    return {
        'date':        day_date,
        'records':     records,
        'description': description,
        'keywords':    keywords,
        'people':      people,
        'gps':         _gps_centroid(records),
        'guess':       guess,
    }


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------

def cluster_days(day_summaries, max_gap_days=DEFAULT_MAX_GAP_DAYS, gps_max_km=DEFAULT_GPS_MAX_KM):
    """
    Greedily scan chronologically-sorted day summaries and merge a day into
    the current cluster only if: the calendar gap since the cluster's last
    day is within `max_gap_days`, both share the same (non-None) guessed
    category, and — when GPS is available on both sides — they are within
    `gps_max_km` of each other. A day with no activity guess never merges
    with its neighbours (always starts/ends its own cluster).
    """
    clusters = []
    current = None

    for day in day_summaries:
        cat_id = day['guess']['category_id']
        can_extend = (
            current is not None
            and cat_id is not None
            and cat_id == current['category_id']
            and (day['date'] - current['end_date']).days <= max_gap_days
            and (current['gps'] is None or day['gps'] is None
                 or _haversine_km(current['gps'], day['gps']) <= gps_max_km)
        )
        if can_extend:
            current['days'].append(day)
            current['end_date'] = day['date']
            if day['gps'] is not None:
                current['gps'] = day['gps']
        else:
            if current is not None:
                clusters.append(current)
            current = {
                'category_id': cat_id,
                'start_date':  day['date'],
                'end_date':    day['date'],
                'gps':         day['gps'],
                'days':        [day],
            }

    if current is not None:
        clusters.append(current)

    return clusters


def _finalize_cluster(cluster, compiled_categories):
    records = [r for day in cluster['days'] for r in day['records']]
    description = ' . '.join(day['description'] for day in cluster['days'] if day['description'])
    keywords = [kw for day in cluster['days'] for kw in day['keywords']]
    people = sorted({p for day in cluster['days'] for p in day['people']})
    guess = guess_activity(description, keywords, compiled_categories)

    images = [r for r in records if r['file_type'] == 'image']
    videos = [r for r in records if r['file_type'] == 'video']

    step = max(1, len(images) // MAX_THUMBNAILS)
    thumbnails = [r['path'] for r in images[::step]][:MAX_THUMBNAILS]

    return {
        'start_date':       cluster['start_date'].isoformat(),
        'end_date':          cluster['end_date'].isoformat(),
        'day_count':         len(cluster['days']),
        'file_count':        len(records),
        'image_count':       len(images),
        'video_count':       len(videos),
        'category_id':       guess['category_id'],
        'label':             guess['label'],
        'confidence':        guess['confidence'],
        'confidence_level':  guess['confidence_level'],
        'matched_keywords':  guess['matched_keywords'],
        'people':            people,
        'has_gps':           cluster['gps'] is not None,
        'thumbnail_paths':   thumbnails,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def find_clusters(folder, include_subdirs=True,
                   min_cluster_size=DEFAULT_MIN_CLUSTER_SIZE,
                   max_gap_days=DEFAULT_MAX_GAP_DAYS,
                   gps_max_km=DEFAULT_GPS_MAX_KM):
    """
    Scan `folder`, group media by day, guess an activity per day, merge
    consecutive days sharing the same activity, then filter and sort.

    Returns (clusters, total_files_scanned). Read-only.
    """
    categories = load_activity_dictionary()
    compiled_categories = _compile_category_patterns(categories)
    known_names_lower = {n.lower() for n in get_known_names()}

    records = _collect_file_records(folder, include_subdirs, known_names_lower)
    day_buckets = _group_by_day(records)
    day_summaries = [
        _build_day_summary(day_date, day_records, compiled_categories)
        for day_date, day_records in sorted(day_buckets.items())
    ]

    clusters = cluster_days(day_summaries, max_gap_days, gps_max_km)
    clusters = [_finalize_cluster(c, compiled_categories) for c in clusters]
    clusters = [c for c in clusters if c['file_count'] >= min_cluster_size]
    clusters.sort(key=lambda c: c['start_date'], reverse=True)

    return clusters, len(records)
