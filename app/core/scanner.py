from pathlib import Path
from .metadata import IMAGE_EXT_ALL, VIDEO_EXT, SKIP_EXT


def scan_folder(folder_path, include_subdirs=True):
    """
    Scan a folder and return sorted list of media file paths (strings).
    Skips JSON sidecar files and hidden files.
    """
    folder = Path(folder_path)
    files = []

    iterator = folder.rglob('*') if include_subdirs else folder.iterdir()

    for f in iterator:
        if not f.is_file():
            continue
        if f.name.startswith('.') or f.name.startswith('__'):
            continue
        ext = f.suffix.lower()
        if ext in SKIP_EXT:
            continue
        if ext == '.json':
            continue
        if 'supplemental-metadata' in f.name or 'supplemental_metadata' in f.name:
            continue
        files.append(str(f))

    return sorted(files)


def scan_summary(folder_path, include_subdirs=True):
    """
    Quick scan. Returns a dict with counts by type and the full file list.
    """
    files = scan_folder(folder_path, include_subdirs)

    images = videos = others = 0
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in IMAGE_EXT_ALL:
            images += 1
        elif ext in VIDEO_EXT:
            videos += 1
        else:
            others += 1

    return {
        'total': len(files),
        'images': images,
        'videos': videos,
        'others': others,
        'files': files,
    }
