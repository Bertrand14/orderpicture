import socket
import subprocess
import threading
import time
import webbrowser
from app import create_app

PORT = 5050
URL = f'http://localhost:{PORT}'


def _wait_for_server(timeout=10):
    """Poll the port until Flask is actually accepting connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', PORT), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def open_browser():
    if not _wait_for_server():
        print(f"⚠ Le serveur n'a pas démarré à temps — ouvrez {URL} manuellement.")
        return

    if webbrowser.open(URL):
        return

    # Fallback: try xdg-open directly (covers some sandboxed/snap browser setups)
    try:
        subprocess.Popen(['xdg-open', URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        print(f"⚠ Impossible d'ouvrir le navigateur automatiquement — ouvrez {URL} manuellement.")


if __name__ == '__main__':
    app = create_app()
    t = threading.Thread(target=open_browser, daemon=True)
    t.start()
    app.run(host='127.0.0.1', port=PORT, debug=False, threaded=True)
