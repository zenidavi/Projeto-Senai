"""Na raiz: python supervisorio/app.py ou python -m supervisorio.app."""
if __package__ in (None, ""):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import sqlite3
from pathlib import Path
from flask import Flask, jsonify, render_template, send_file, abort
from config import DATABASE_PATH, FLASK_PORT, POLL_INTERVAL_MS, IMAGE_DIR, SIMULATION_DATABASE_PATH
from supervisorio.analises import registrar_analises
from supervisorio.camera_web import registrar_rotas
from supervisorio.ocorrencias import registrar_ocorrencias
from supervisorio.database import (inicializar_banco, validar_banco_leitura, buscar_status,
                                   mesmo_banco, buscar_inspecoes_recentes, buscar_inspecao)


def create_app(db_path=None, image_dir=IMAGE_DIR, *, camera_web=True, somente_leitura=False):
    app = Flask(__name__)
    banco = DATABASE_PATH if db_path is None else db_path
    simulacao = mesmo_banco(banco, SIMULATION_DATABASE_PATH)
    if somente_leitura:
        validar_banco_leitura(banco)
    else:
        inicializar_banco(banco)

    @app.context_processor
    def dados_da_estacao():
        return {'simulacao': simulacao, 'somente_leitura': somente_leitura, 'abas_qualidade': True}

    @app.get("/")
    def index():
        return render_template("index.html", poll_interval=POLL_INTERVAL_MS)

    @app.get("/api/status")
    def status():
        return jsonify(buscar_status(banco, preparar=False))

    @app.get("/api/historico")
    def historico():
        return jsonify(buscar_inspecoes_recentes(db_path=banco, preparar=False))

    @app.get("/api/inspecoes/<int:identificador>/imagem")
    def imagem(identificador):
        registro = buscar_inspecao(identificador, banco, preparar=False)
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

    if camera_web and not simulacao:
        registrar_rotas(app, db_path=banco, image_dir=image_dir, permitir_comandos=not somente_leitura)
    registrar_analises(app, db_path=banco, image_dir=image_dir, simulacao=simulacao)
    registrar_ocorrencias(app, banco, somente_leitura)
    return app


def main():
    parser = argparse.ArgumentParser(description="Supervisório local da Estação 3.")
    parser.add_argument("--somente-leitura", action="store_true",
                        help="Abre o SQLite v2 existente e desabilita comandos de inspeção.")
    args = parser.parse_args()
    try:
        app = create_app(somente_leitura=args.somente_leitura)
    except sqlite3.Error as exc:
        parser.exit(1, f"SQLite indisponível em {DATABASE_PATH}: {exc}\n")
    # O comando web é de uso local e não tem login.
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=False, threaded=True)


if __name__ == '__main__':
    main()
