"""Na raiz: python supervisorio/app.py ou python -m supervisorio.app."""
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlite3
from pathlib import Path
from flask import Flask, jsonify, render_template, send_file, abort
from config import FLASK_HOST, FLASK_PORT, POLL_INTERVAL_MS, IMAGE_DIR
from supervisorio.database import (inicializar_banco, buscar_status,
                                   buscar_inspecoes_recentes, buscar_inspecao)


def create_app(db_path=None, image_dir=IMAGE_DIR):
    app = Flask(__name__)
    opcoes = {"db_path": db_path} if db_path is not None else {}
    inicializar_banco(**opcoes)

    @app.get("/")
    def index():
        return render_template("index.html", poll_interval=POLL_INTERVAL_MS)

    @app.get("/api/status")
    def status():
        return jsonify(buscar_status(**opcoes))

    @app.get("/api/historico")
    def historico():
        return jsonify(buscar_inspecoes_recentes(**opcoes))

    @app.get("/api/inspecoes/<int:identificador>/imagem")
    def imagem(identificador):
        registro = buscar_inspecao(identificador, **opcoes)
        if not registro or not registro['imagem_path']:
            abort(404)
        raiz = Path(image_dir).resolve()
        caminho = (raiz / registro['imagem_path']).resolve()
        if not caminho.is_relative_to(raiz) or not caminho.is_file():
            abort(404)
        return send_file(caminho, mimetype="image/jpeg")

    @app.after_request
    def sem_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(sqlite3.Error)
    def erro_banco(erro):
        app.logger.error("Falha SQLite: %s", erro)
        return jsonify(erro="Banco indisponível. Tente novamente."), 503

    return app


if __name__ == "__main__":
    create_app().run(host=FLASK_HOST, port=FLASK_PORT, debug=False)
