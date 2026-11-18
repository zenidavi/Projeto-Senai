"""Relatórios reais do SQLite da Estação 3; consultas somente leitura."""
from __future__ import annotations
import csv
import io
import sqlite3
from datetime import date
from pathlib import Path
from flask import Blueprint, Response, jsonify, render_template, request
from config import DATABASE_PATH
from supervisorio.database import buscar_status

COLUNAS = ("id", "timestamp", "resultado", "classe_detectada", "confianca",
           "origem", "ciclo_id", "inicio_timestamp", "duracao_ms", "motivo",
           "modelo_versao", "imagem_path", "serial_status")
MAX_EXPORTACAO = 50000


def filtros(req):
    partes, parametros = [], []
    for campo in ("inicio", "fim"):
        valor = (req.get(campo) or "").strip()
        if valor:
            if len(valor) != 10 or date.fromisoformat(valor).isoformat() != valor:
                raise ValueError(f"Data {campo} inválida: use AAAA-MM-DD.")
            partes.append("substr(timestamp, 1, 10) " + (">=" if campo == "inicio" else "<=") + " ?")
            parametros.append(valor)
    if req.get("inicio") and req.get("fim") and req["inicio"] > req["fim"]:
        raise ValueError("Data inicial posterior à final.")
    for campo, coluna, aceitos in (
        ("resultado", "resultado", ("OK", "NOK", "INCONCLUSIVO")),
        ("origem", "origem", ("real", "simulador")),
        ("classe", "classe_detectada", None),
        ("versao", "modelo_versao", None),
    ):
        valor = (req.get(campo) or "").strip()
        if not valor:
            continue
        if len(valor) > 160 or (aceitos and valor not in aceitos):
            raise ValueError(f"Filtro {campo} inválido.")
        partes.append(coluna + " = ?")
        parametros.append(valor)
    return (" WHERE " + " AND ".join(partes)) if partes else "", parametros


def conexao(banco):
    c = sqlite3.connect(str(banco), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA query_only=ON")
    c.execute("PRAGMA busy_timeout=10000")
    return c


def consultar(banco, onde, parametros, pagina=1, limite=30):
    pagina, limite = max(1, min(int(pagina), 1000000)), max(1, min(int(limite), 100))
    with conexao(banco) as conn:
        c = conn.cursor()
        r = dict(c.execute(f"""SELECT COUNT(*) total,
            COALESCE(SUM(resultado='OK'),0) ok,
            COALESCE(SUM(resultado='NOK'),0) nok,
            COALESCE(SUM(resultado='INCONCLUSIVO'),0) inconclusivos,
            ROUND(AVG(duracao_ms),1) duracao_media_ms,
            ROUND(AVG(CASE WHEN resultado IN ('OK','NOK') THEN confianca END)*100,1) confianca_media_pct
            FROM inspecoes {onde}""", parametros).fetchone())
        concluidos = r["ok"] + r["nok"]
        r["conformidade_pct"] = round(100 * r["ok"] / concluidos, 1) if concluidos else None
        r["inconclusivos_pct"] = round(100 * r["inconclusivos"] / r["total"], 1) if r["total"] else None
        grupos = {}
        for nome, coluna in (("origens", "origem"), ("classes", "classe_detectada"),
                             ("comunicacao", "serial_status"), ("modelos", "modelo_versao")):
            grupos[nome] = [dict(x) for x in c.execute(
                f"SELECT {coluna} categoria, COUNT(*) quantidade FROM inspecoes {onde} "
                f"GROUP BY {coluna} ORDER BY quantidade DESC LIMIT 20", parametros)]
        tendencia = [dict(x) for x in c.execute(
            f"SELECT substr(timestamp,1,10) data, COUNT(*) total,"
            f" SUM(resultado='OK') ok, SUM(resultado='NOK') nok,"
            f" SUM(resultado='INCONCLUSIVO') inconclusivos FROM inspecoes {onde}"
            f" GROUP BY substr(timestamp,1,10) ORDER BY data DESC LIMIT 30", parametros)]
        historico = [dict(x) for x in c.execute(
            f"SELECT * FROM inspecoes {onde} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*parametros, limite, (pagina-1)*limite])]
        return {"resumo": r, "grupos": grupos, "tendencia": list(reversed(tendencia)),
                "historico": historico, "pagina": pagina, "por_pagina": limite,
                "paginas": max(1, (r["total"]+limite-1)//limite)}


def exportar(banco, onde, parametros):
    with conexao(banco) as conn:
        linhas = [dict(x) for x in conn.execute(
            f"SELECT * FROM inspecoes {onde} ORDER BY id DESC LIMIT ?",
            [*parametros, MAX_EXPORTACAO+1])]
    if len(linhas) > MAX_EXPORTACAO:
        raise OverflowError("Exportação muito grande. Filtre o período.")
    return linhas


def csv_bytes(linhas):
    stream = io.StringIO(newline="")
    stream.write("\ufeff")
    writer = csv.writer(stream, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUNAS)
    for item in linhas:
        valores = []
        for campo in COLUNAS:
            valor = "" if item.get(campo) is None else str(item[campo])
            if valor.lstrip().startswith(("=", "+", "-", "@")):
                valor = "'" + valor  # evita injeção de fórmula no Excel
            valores.append(valor)
        writer.writerow(valores)
    return stream.getvalue().encode("utf-8")


def pdf_bytes(dados, linhas):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from xml.sax.saxutils import escape
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=16*mm,
                            rightMargin=16*mm, topMargin=16*mm, bottomMargin=16*mm)
    estilos = getSampleStyleSheet()
    r = dados["resumo"]
    story = [Paragraph("ESTAÇÃO 3 | RELATÓRIO DE INSPEÇÕES", estilos["Title"]),
             Paragraph("Dados extraídos do SQLite; amostra de até 100 registros.", estilos["Normal"]),
             Spacer(1, 7*mm)]
    metricas = [["Inspeções", "OK", "NOK", "Inconclusivos", "Conformidade"],
                [r["total"], r["ok"], r["nok"], r["inconclusivos"],
                 str(r["conformidade_pct"])+"%" if r["conformidade_pct"] is not None else "—"]]
    tabela = Table(metricas, colWidths=[45*mm]*5)
    tabela.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#18344b")),
                                ("TEXTCOLOR",(0,0),(-1,0),colors.white),
                                ("ALIGN",(0,0),(-1,-1),"CENTER")]))
    story += [tabela, Spacer(1, 7*mm)]
    valores = [["ID", "Data", "Resultado", "Classe", "Origem", "Serial"]]
    for item in linhas[:100]:
        valores.append([str(item.get("id","")),
                       str(item.get("timestamp",""))[:19].replace("T"," "),
                       str(item.get("resultado") or "-"), str(item.get("classe_detectada") or "-")[:24],
                       str(item.get("origem") or "-"), str(item.get("serial_status") or "-")[:27]])
    tabela = Table(valores, repeatRows=1, colWidths=[16*mm,42*mm,36*mm,48*mm,39*mm,62*mm])
    tabela.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#18344b")),
                                ("TEXTCOLOR",(0,0),(-1,0),colors.white),
                                ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
                                ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#edf3f7")]),
                                ("FONTSIZE",(0,0),(-1,-1),8)]))
    story.append(tabela)
    doc.build(story)
    return buf.getvalue()


def registrar_analises(app, db_path=None):
    banco = Path(db_path) if db_path is not None else DATABASE_PATH
    bp = Blueprint("analises_est3", __name__)

    def validar():
        try:
            return filtros(request.args), None
        except ValueError as erro:
            return None, (jsonify(erro=str(erro)), 400)

    @bp.get("/analises")
    def pagina():
        return render_template("analises.html")

    @bp.get("/api/analises/dados")
    def dados():
        f, erro = validar()
        if erro:
            return erro
        try:
            return jsonify(consultar(banco, *f, pagina=request.args.get("pagina",1),
                                    limite=request.args.get("por_pagina",30)))
        except ValueError:
            return jsonify(erro="Paginação inválida."), 400

    @bp.get("/api/analises/opcoes")
    def opcoes():
        with conexao(banco) as conn:
            return jsonify({
                "classes": [x[0] for x in conn.execute("SELECT DISTINCT classe_detectada FROM inspecoes WHERE classe_detectada IS NOT NULL ORDER BY 1")],
                "versoes": [x[0] for x in conn.execute("SELECT DISTINCT modelo_versao FROM inspecoes WHERE modelo_versao IS NOT NULL ORDER BY 1")]
            })

    @bp.get("/api/analises/diagnostico")
    def diagnostico():
        estacao = buscar_status(db_path=banco)["estacao"]
        return jsonify({"online": estacao.get("online", False),
                        "estado": estacao.get("estado", "SEM_CONEXAO"),
                        "camera": estacao.get("camera"), "modelo": estacao.get("modelo"),
                        "serial": estacao.get("serial"),
                        "atualizado_em": estacao.get("atualizado_em"),
                        "fps_inferencia": estacao.get("fps_inferencia"),
                        "fps_transmissao": estacao.get("fps_transmissao")})

    @bp.get("/api/analises/exportar.csv")
    def csv():
        f, erro = validar()
        if erro:
            return erro
        try:
            linhas = exportar(banco,*f)
        except OverflowError as exc:
            return jsonify(erro=str(exc)),413
        return Response(csv_bytes(linhas), mimetype="text/csv",
                        headers={"Content-Disposition":"attachment; filename=estacao3_inspecoes.csv"})

    @bp.get("/api/analises/relatorio.pdf")
    def pdf():
        f, erro = validar()
        if erro:
            return erro
        try:
            linhas = exportar(banco,*f)
            relatorio = consultar(banco,*f)
            return Response(pdf_bytes(relatorio,linhas),mimetype="application/pdf",
                            headers={"Content-Disposition":"attachment; filename=estacao3_relatorio.pdf"})
        except ImportError:
            return jsonify(erro="Instale reportlab para gerar PDF."),503
        except OverflowError as exc:
            return jsonify(erro=str(exc)),413

    app.register_blueprint(bp)
