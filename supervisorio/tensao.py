"""Consulta somente leitura das medições do monitor de bancada."""
from datetime import datetime
from pathlib import Path
import sqlite3
from flask import Blueprint, jsonify, render_template
from config import ROOT_DIR

BANCO_TENSAO = ROOT_DIR / "Estacoes_2_3_Integradas" / "tensao_estacao2.db"
LIMITE = 1.10
TETO_NOMINAL = 2.20


def consultar_tensao(banco=BANCO_TENSAO, *, simulacao=False, agora=None):
    resposta = {"online": False, "simulacao": simulacao, "leituras": [], "ultima": None,
                "limite_v": LIMITE, "teto_nominal_v": TETO_NOMINAL}
    if simulacao:
        return resposta
    banco = Path(banco)
    if not banco.is_file():
        return resposta
    with sqlite3.connect(banco.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as con:
        con.row_factory = sqlite3.Row
        linhas = con.execute("""SELECT id, horario_local, tensao_v, resultado, porta
            FROM medicoes_tensao ORDER BY id DESC LIMIT 120""").fetchall()
    for linha in linhas:
        item = dict(linha)
        item["saturada"] = item["tensao_v"] >= 2.19
        item["avaliacao"] = "SATURADA / NÃO VALIDADA" if item["saturada"] else item["resultado"]
        resposta["leituras"].append(item)
    if resposta["leituras"]:
        ultima = resposta["leituras"][0]
        resposta["ultima"] = ultima
        try:
            idade = ((agora or datetime.now().astimezone()) - datetime.fromisoformat(ultima["horario_local"])).total_seconds()
            resposta["online"] = 0 <= idade <= 5
        except (ValueError, TypeError):
            pass
    return resposta


def registrar_tensao(app, *, simulacao=False, banco=None):
    bp = Blueprint("tensao", __name__)
    @bp.get("/tensao")
    def pagina():
        return render_template("tensao.html")
    @bp.get("/api/tensao")
    def api():
        try:
            return jsonify(consultar_tensao(BANCO_TENSAO if banco is None else banco, simulacao=simulacao))
        except sqlite3.Error:
            return jsonify(erro="Banco de tensão indisponível. Verifique o leitor Serial."), 503
    app.register_blueprint(bp)
