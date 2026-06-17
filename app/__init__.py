from flask import Flask
from pathlib import Path

def create_app():
    app = Flask(__name__)
    app.secret_key = 'mediasort-local-2024'
    # Always re-read templates from disk (this app restarts rarely; avoids
    # stale UI after edits without needing a server restart).
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    data_dir = Path(__file__).parent.parent / 'data'
    (data_dir / 'profiles').mkdir(parents=True, exist_ok=True)

    from .routes import bp
    app.register_blueprint(bp)

    return app
