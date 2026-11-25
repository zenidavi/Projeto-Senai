"""Blueprint de dados e relatorios. Nao controla motor, Arduino ou camera."""
from __future__ import annotations

from pathlib import Path
import sqlite3
from flask import Blueprint, Response, jsonify, render_template, request
from config import DATABASE_PATH, IMAGE_DIR
from supervisorio.analises_dados import (
    Filtros, FiltroInvalido, ExportacaoGrande, consultar_analises, consultar_estado,
    registros_para_exportacao, gerar_csv, gerar_pdf, opcoes_filtros, consultar_exportacao_excel,
    comparar_periodos,
)
from supervisorio.camera_web import diagnosticar_preview
from supervisorio.relatorio_excel import gerar_xlsx


def registrar_analises(app, db_path=None, *, image_dir=IMAGE_DIR, simulacao=False):
    """Acrescenta paginas e API de analises a mesma instancia do Flask existente."""
    if 'estacao3_analises' in app.blueprints:
        return
    banco = Path(db_path) if db_path is not None else DATABASE_PATH
    bp = Blueprint('estacao3_analises', __name__)

    def filtros_da_requisicao():
        try:
            return Filtros.ler(request.args), None
        except FiltroInvalido as exc:
            return None, (jsonify({'erro': str(exc)}), 400)

    @bp.get('/analises')
    def pagina_analises():
        return render_template('analises.html')

    @bp.get('/analises/comparar')
    def comparacao():
        resultados = None
        erro = None
        if request.args:
            try:
                periodos = [Filtros.ler({
                    'inicio': request.args.get(f'inicio_{sufixo}'),
                    'fim': request.args.get(f'fim_{sufixo}'),
                    'origem': request.args.get('origem'),
                }) for sufixo in ('a', 'b')]
                if any(not (periodo.inicio and periodo.fim) for periodo in periodos):
                    raise FiltroInvalido('Preencha as duas datas de cada período.')
                resultados = comparar_periodos(banco, periodos)
            except FiltroInvalido as exc:
                erro = str(exc)
        return render_template('comparar.html', resultados=resultados, erro=erro), 400 if erro else 200

    @bp.get('/api/analises/opcoes')
    def opcoes():
        return jsonify(opcoes_filtros(banco))

    @bp.get('/api/analises/dados')
    def dados():
        filtros, erro = filtros_da_requisicao()
        if erro:
            return erro
        try:
            pagina = int(request.args.get('pagina', '1'))
            por_pagina = int(request.args.get('por_pagina', '30'))
        except ValueError:
            return jsonify({'erro': 'Pagina e limite precisam ser inteiros.'}), 400
        return jsonify(consultar_analises(banco, filtros, pagina, por_pagina))

    @bp.get('/api/analises/diagnostico')
    def diagnostico():
        try:
            s = consultar_estado(banco)
        except sqlite3.Error as exc:
            app.logger.error('Falha SQLite no diagnóstico: %s', exc)
            return jsonify(sqlite='indisponivel', erro='SQLite indisponível para leitura.'), 503
        simulado = simulacao or s.get('origem') == 'simulador'
        preview = {'estado': 'simulacao', 'idade_segundos': None} if simulado else diagnosticar_preview(image_dir)
        return jsonify({
            'sqlite': 'leitura_ok',
            'preview': preview,
            'simulacao': simulado,
            'online': bool(s.get('online')),
            'estado': s.get('estado', 'SEM_CONEXAO'),
            'camera': s.get('camera'),
            'modelo': s.get('modelo'),
            'serial': s.get('serial', 'nao_informado'),
            'origem': s.get('origem', ''),
            'atualizado_em': s.get('atualizado_em'),
            'idade_segundos': s.get('idade_segundos'),
            'motivo': s.get('motivo', ''),
            'modelo_versao': s.get('modelo_versao', ''),
            # Nenhum FPS e inventado: so aparece se a inferencia publicar essa metrica.
            'fps_inferencia': s.get('fps_inferencia'),
            'fps_transmissao': s.get('fps_transmissao'),
            'latencia_inferencia_ms': s.get('latencia_inferencia_ms'),
            'latencia_captura_ms': s.get('latencia_captura_ms'),
            'latencia_codificacao_jpeg_ms': s.get('latencia_codificacao_jpeg_ms'),
            'latencia_publicacao_jpeg_ms': s.get('latencia_publicacao_jpeg_ms'),
            'falhas_publicacao_jpeg': s.get('falhas_publicacao_jpeg') if not simulado else None,
            'ultimo_erro_publicacao_jpeg': s.get('ultimo_erro_publicacao_jpeg') if not simulado else None,
        })

    @bp.get('/api/analises/exportar.csv')
    def exportar_csv():
        filtros, erro = filtros_da_requisicao()
        if erro:
            return erro
        try:
            registros = registros_para_exportacao(banco, filtros)
        except ExportacaoGrande as exc:
            return jsonify({'erro': str(exc)}), 413
        dados = gerar_csv(registros)
        return Response(dados, content_type='text/csv; charset=utf-8', headers={
            'Content-Disposition': 'attachment; filename="estacao3_inspecoes.csv"',
            'Cache-Control': 'no-store',
        })

    @bp.get('/api/analises/exportar.xlsx')
    def exportar_xlsx():
        filtros, erro = filtros_da_requisicao()
        if erro:
            return erro
        try:
            resumo, registros = consultar_exportacao_excel(banco, filtros)
            arquivo = gerar_xlsx(resumo, filtros, registros)
        except ExportacaoGrande as exc:
            return jsonify({'erro': str(exc)}), 413
        except ImportError as exc:
            app.logger.warning('Dependência de Excel indisponível: %s', exc)
            return jsonify({'erro': 'Dependência de Excel indisponível neste ambiente Python.'}), 503
        return Response(arquivo, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': 'attachment; filename="estacao3_inspecoes.xlsx"'})

    @bp.get('/api/analises/relatorio.pdf')
    def relatorio_pdf():
        filtros, erro = filtros_da_requisicao()
        if erro:
            return erro
        relatorio = consultar_analises(banco, filtros, por_pagina=100)
        try:
            pdf = gerar_pdf(relatorio, filtros, relatorio['historico'])
        except ImportError as exc:
            app.logger.warning('Dependência de PDF indisponível: %s', exc)
            return jsonify({'erro': 'Dependências do PDF indisponíveis neste ambiente Python.'}), 503
        return Response(pdf, mimetype='application/pdf', headers={
            'Content-Disposition': 'attachment; filename="estacao3_relatorio.pdf"',
            'Cache-Control': 'no-store',
        })

    app.register_blueprint(bp)
