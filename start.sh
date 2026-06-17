#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "Création de l'environnement virtuel…"
  python3 -m venv venv
  # torch CPU-only build (PyPI default pulls a much larger CUDA build)
  venv/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu
  venv/bin/pip install -q -r requirements.txt
  echo "Installation terminée."
fi

echo "Démarrage de MediaSort → http://localhost:5050"
venv/bin/python run.py
