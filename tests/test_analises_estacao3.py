"""Testes sem webcam, YOLO, Arduino nem servidor de rede."""
import csv
from contextlib import closing
import io
import os
import re
from pathlib import Path
import sqlite3
import stat
import tempfile
import time
import unittest
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile
import config as cfg
from supervisorio import camera_web
from supervisorio.app import create_app
from supervisorio.database import inicializar_banco, publicar_estado
from supervisorio.simulador import banco_da_simulacao
from supervisorio.analises_dados import (
    Filtros, FiltroInvalido, consultar_analises, gerar_csv, gerar_pdf,
    opcoes_filtros, registros_para_exportacao
)


class DadosTestes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'inspecoes.db'
        inicializar_banco(self.db)
        with closing(sqlite3.connect(self.db)) as c, c:
            linhas = [
                (1,'a'*32,'2026-11-10T10:00:00-03:00','OK','tampa_ok',.92,350,
                 'DETECCAO_ESTAVEL','real','tampa-v1:abc','desabilitada','imagem-1.jpg',None),
                (2,'b'*32,'2026-11-10T10:10:00-03:00','NOK','tampa_nok',.85,500,
                 'DETECCAO_ESTAVEL','real','tampa-v1:abc','confirmado',None,None),
                (3,'c'*32,'2026-11-11T13:00:00-03:00','INCONCLUSIVO',None,None,5000,
                 'SEM_DETECCAO','real','tampa-v1:abc','nao_aplicavel',None,None),
                (4,'d'*32,'2026-11-11T13:20:00-03:00','OK','tampa_ok',.98,280,
                 'DETECCAO_ESTAVEL','simulador','tampa-v1:abc','simulado_confirmado',None,None),
            ]
            c.executemany('''INSERT INTO inspecoes (
                id, ciclo_id, timestamp, resultado, classe_detectada, confianca, duracao_ms,
                motivo, origem, modelo_versao, serial_status, imagem_path, inicio_timestamp
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', linhas)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resumo_distingue_real_simulado_e_inconclusivo(self):
        todos=consultar_analises(self.db,Filtros())
        r=todos['resumo']
        self.assertEqual((r['total'],r['ok'],r['nok'],r['inconclusivos']),(4,2,1,1))
        self.assertEqual(r['taxa_conformidade_pct'],66.7)
        self.assertEqual(r['taxa_inconclusivo_pct'],25.0)
        self.assertEqual(r['cobertura_imagens_pct'],25.0)
        self.assertEqual(len(todos['tendencia']),2)
        real=consultar_analises(self.db,Filtros(origem='real'))
        self.assertEqual((real['resumo']['total'],real['resumo']['ok']),(3,1))
        somente_nok=consultar_analises(self.db,Filtros(resultado='NOK'))
        self.assertEqual(somente_nok['resumo']['total'],1)
        self.assertEqual(somente_nok['resumo']['taxa_conformidade_pct'],0.0)
        self.assertEqual(opcoes_filtros(self.db)['classes'],['tampa_nok','tampa_ok'])

    def test_datas_validacao_e_periodo(self):
        f=Filtros.ler({'inicio':'2026-11-11','fim':'2026-11-11'})
        self.assertEqual(consultar_analises(self.db,f)['resumo']['total'],2)
        for qs in [{'inicio':'2026-13-01'}, {'inicio':'10/11/2026'},
                   {'inicio':'2026-12-10','fim':'2026-11-10'}, {'origem':'inventada'},
                   {'resultado':'FALHA'}]:
            with self.assertRaises(FiltroInvalido): Filtros.ler(qs)

    def test_paginacao_e_sem_dados(self):
        d=consultar_analises(self.db,Filtros(),pagina=2,por_pagina=2)
        self.assertEqual(len(d['historico']),2)
        self.assertEqual(d['paginas'],2)
        d=consultar_analises(self.db,Filtros(classe='NAO_EXISTE'))
        self.assertEqual(d['resumo']['total'],0)
        self.assertIsNone(d['resumo']['taxa_conformidade_pct'])
        self.assertEqual(d['historico'],[])

    def test_csv_sem_formula_excel(self):
        registros=registros_para_exportacao(self.db,Filtros())
        registros[0]['motivo']='=HIPERLINK("http://fake", "clique")'
        txt=gerar_csv(registros).decode('utf-8-sig')
        linhas=list(csv.reader(io.StringIO(txt),delimiter=';'))
        self.assertEqual(len(linhas),5)
        self.assertTrue(any(r[7].startswith("'=") for r in linhas[1:]))

    def test_pdf_gerado(self):
        try:
            import reportlab  # opcional para o PDF
        except ImportError:
            self.skipTest("Instale reportlab para testar exportacao PDF")
        registros=registros_para_exportacao(self.db,Filtros())
        pdf=gerar_pdf(consultar_analises(self.db,Filtros()),Filtros(),registros)
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertGreater(len(pdf),2000)

    def test_rotas_consultam_e_exportam_o_mesmo_recorte(self):
        client = create_app(db_path=self.db).test_client()
        self.assertEqual(client.get('/analises').status_code, 200)
        self.assertEqual(client.get('/api/analises/diagnostico').json['estado'], 'SEM_CONEXAO')
        filtros = {'inicio': '2026-11-10', 'fim': '2026-11-10', 'origem': 'real',
                   'resultado': 'NOK', 'classe': 'tampa_nok', 'versao': 'tampa-v1:abc'}
        dados = client.get('/api/analises/dados', query_string=filtros).json
        self.assertEqual(dados['resumo']['total'], 1)
        self.assertEqual([item['id'] for item in dados['historico']], [2])

        csv_resp = client.get('/api/analises/exportar.csv', query_string=filtros)
        self.assertEqual(csv_resp.status_code, 200)
        leitor = csv.DictReader(io.StringIO(csv_resp.data.decode('utf-8-sig')), delimiter=';')
        self.assertEqual([row['ID'] for row in leitor], ['2'])

        pdf_resp = client.get('/api/analises/relatorio.pdf', query_string=filtros)
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertTrue(pdf_resp.data.startswith(b'%PDF-'))
        for rota in ['dados', 'exportar.csv', 'exportar.xlsx', 'relatorio.pdf']:
            resposta = client.get('/api/analises/' + rota, query_string={'inicio': '2026-02-30'})
            self.assertEqual(resposta.status_code, 400)

    def test_excel_filtrado_preserva_tipos_e_texto(self):
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute("UPDATE inspecoes SET motivo=? WHERE id=2", ('=1+1',))
        client = create_app(db_path=self.db, somente_leitura=True).test_client()
        resposta = client.get('/api/analises/exportar.xlsx?origem=real&resultado=NOK')
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.headers['Content-Disposition'].endswith('estacao3_inspecoes.xlsx"'))
        namespace = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with ZipFile(io.BytesIO(resposta.data)) as livro:
            resumo = ElementTree.fromstring(livro.read('xl/worksheets/sheet1.xml'))
            historico = ElementTree.fromstring(livro.read('xl/worksheets/sheet2.xml'))
            self.assertEqual(resumo.find(".//s:c[@r='B6']/s:v", namespace).text, '1')
            self.assertEqual(historico.find(".//s:c[@r='A6']/s:v", namespace).text, '2')
            self.assertEqual(historico.find(".//s:c[@r='F6']/s:v", namespace).text, '0.85')
            self.assertEqual(historico.find(".//s:c[@r='H6']/s:is/s:t", namespace).text, '=1+1')
            self.assertIsNone(historico.find('.//s:f', namespace))
            self.assertEqual(historico.find('.//s:autoFilter', namespace).get('ref'), 'A5:M6')
            self.assertEqual(historico.find('.//s:pane', namespace).get('topLeftCell'), 'B6')
        with patch('supervisorio.analises_dados.MAX_EXPORTACAO', 1):
            self.assertEqual(client.get('/api/analises/exportar.xlsx').status_code, 413)

    def test_diagnostico_preview_e_falha_sqlite(self):
        imagens = Path(self.tmp.name) / 'imagens'
        client = create_app(db_path=self.db, image_dir=imagens).test_client()
        rota = '/api/analises/diagnostico'
        self.assertEqual(client.get(rota).json['preview']['estado'], 'indisponivel')
        publicar_estado('teste', {
            'origem': 'real', 'ativo': True, 'estado': 'AGUARDANDO',
            'falhas_publicacao_jpeg': 2, 'ultimo_erro_publicacao_jpeg': 'WinError 5',
        }, db_path=self.db)
        jpeg = camera_web.caminho_preview(imagens)
        jpeg.parent.mkdir(parents=True)
        jpeg.touch()
        self.assertEqual(client.get(rota).json['preview']['estado'], 'recente')
        instante = time.time() - 60
        os.utime(jpeg, (instante, instante))
        diag = client.get(rota).json
        self.assertEqual(diag['sqlite'], 'leitura_ok')
        self.assertEqual(diag['preview']['estado'], 'expirado')
        self.assertEqual(diag['falhas_publicacao_jpeg'], 2)
        self.assertEqual(diag['ultimo_erro_publicacao_jpeg'], 'WinError 5')
        self.assertIsNone(diag['fps_inferencia'])
        with patch('supervisorio.analises.consultar_estado', side_effect=sqlite3.OperationalError):
            falha = client.get(rota)
        self.assertEqual(falha.status_code, 503)
        self.assertEqual(falha.json['sqlite'], 'indisponivel')

    def test_simulacao_isolada_e_identificada(self):
        sim = Path(self.tmp.name) / 'simulacao.db'
        with patch.object(cfg, 'SIMULATION_DATABASE_PATH', sim):
            with patch.dict(os.environ, {'ESTACAO3_DB': str(self.db)}), patch.object(cfg, 'DATABASE_PATH', self.db):
                with self.assertRaisesRegex(ValueError, 'apenas'):
                    banco_da_simulacao()
            with patch.dict(os.environ, {'ESTACAO3_DB': str(sim)}), patch.object(cfg, 'DATABASE_PATH', sim):
                self.assertEqual(banco_da_simulacao(), sim)
                with patch('supervisorio.app.SIMULATION_DATABASE_PATH', sim):
                    client = create_app(db_path=sim).test_client()
                self.assertIn(b'Modo simula', client.get('/').data)
                self.assertIn(b'Modo simula', client.get('/analises').data)
                self.assertEqual(client.get('/api/video/frame').status_code, 404)
                self.assertEqual(client.get('/api/analises/diagnostico').json['preview']['estado'], 'simulacao')
                publicar_estado('real', {'origem': 'real', 'ativo': False, 'estado': 'AGUARDANDO'}, db_path=sim)
                with self.assertRaisesRegex(ValueError, 'outra origem'):
                    banco_da_simulacao()

    def test_simulador_recusa_alias_do_banco_real(self):
        sim = Path(self.tmp.name) / 'simulacao.db'
        os.link(self.db, sim)
        with patch.multiple(cfg, SIMULATION_DATABASE_PATH=sim, REAL_DATABASE_PATH=self.db, DATABASE_PATH=sim):
            with patch.dict(os.environ, {'ESTACAO3_DB': str(sim)}):
                with self.assertRaisesRegex(ValueError, 'inspeções reais'):
                    banco_da_simulacao()

    def test_painel_somente_leitura_com_banco_protegido(self):
        imagens = Path(self.tmp.name) / 'imagens'
        imagens.mkdir()
        (imagens / 'imagem-1.jpg').write_bytes(b'evidencia')
        jpeg = camera_web.caminho_preview(imagens)
        jpeg.parent.mkdir()
        jpeg.write_bytes(b'preview')
        publicar_estado('teste', {
            'origem': 'real', 'ativo': True, 'estado': 'AGUARDANDO',
            'camera': True, 'modelo': True,
        }, db_path=self.db)
        original = self.db.read_bytes()
        self.db.chmod(stat.S_IREAD)
        try:
            with patch('supervisorio.app.inicializar_banco', side_effect=AssertionError), \
                 patch('supervisorio.database.inicializar_banco', side_effect=AssertionError):
                client = create_app(self.db, imagens, somente_leitura=True).test_client()
                inicio = client.get('/')
                self.assertIn(b'Modo somente leitura', inicio.data)
                self.assertNotIn(b'id="camera-web-iniciar"', inicio.data)
                self.assertEqual(client.get('/api/status').json['contagens']['total'], 4)
                self.assertEqual(len(client.get('/api/historico').json), 4)
                with client.get('/api/inspecoes/1/imagem') as evidencia:
                    self.assertEqual(evidencia.data, b'evidencia')
                self.assertEqual(client.get('/api/video/frame').data, b'preview')
                self.assertFalse(client.get('/api/video/controle/estado').json['pronto'])
                self.assertEqual(client.post('/api/video/controle/inspecionar').status_code, 403)
                self.assertFalse(camera_web.caminho_comando(imagens).exists())
                for rota in ('/analises', '/api/analises/dados', '/api/analises/diagnostico',
                             '/api/analises/exportar.csv', '/api/analises/relatorio.pdf'):
                    self.assertEqual(client.get(rota).status_code, 200)
            self.assertEqual(self.db.read_bytes(), original)
        finally:
            self.db.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_painel_somente_leitura_nao_cria_nem_migra(self):
        ausente = self.db.with_name('ausente.db')
        with self.assertRaises(sqlite3.OperationalError):
            create_app(ausente, somente_leitura=True)
        self.assertFalse(ausente.exists())
        with closing(sqlite3.connect(ausente)) as conn, conn:
            conn.execute('CREATE TABLE inspecoes (id INTEGER)')
        original = ausente.read_bytes()
        with self.assertRaisesRegex(sqlite3.OperationalError, 'schema v2'):
            create_app(ausente, somente_leitura=True)
        self.assertEqual(ausente.read_bytes(), original)

    def test_fluxo_de_tratamento_preserva_inspecao(self):
        client = create_app(self.db).test_client()
        fila = client.get('/ocorrencias').data
        self.assertIn(b'Abrir #2', fila)
        self.assertIn(b'Abrir #3', fila)
        self.assertNotIn(b'Abrir #1', fila)
        self.assertEqual(client.get('/ocorrencias/1').status_code, 404)
        detalhe = client.get('/ocorrencias/2').data
        token = re.search(rb'name="token" value="([a-f0-9]+)"', detalhe)[1].decode()
        form = {'token': token, 'status': 'resolvida', 'responsavel': 'Equipe A', 'acao': ''}
        self.assertEqual(client.post('/ocorrencias/2', data=form).status_code, 400)
        form['acao'] = 'Ajuste verificado.'
        self.assertEqual(client.post('/ocorrencias/2', data=form).status_code, 303)
        self.assertEqual(client.post('/ocorrencias/2', data=form).status_code, 409)
        self.assertIn(b'Equipe A', client.get('/ocorrencias?status=resolvida').data)
        self.assertNotIn(b'Abrir #2', client.get('/ocorrencias?status=pendente').data)
        leitura = create_app(self.db, somente_leitura=True).test_client()
        self.assertIn(b'Ajuste verificado.', leitura.get('/ocorrencias/2').data)
        self.assertEqual(leitura.post('/ocorrencias/2', data=form).status_code, 403)
        with closing(sqlite3.connect(self.db)) as conn:
            self.assertEqual(conn.execute('SELECT resultado, motivo FROM inspecoes WHERE id=2').fetchone(),
                             ('NOK', 'DETECCAO_ESTAVEL'))

    def test_comparacao_e_recorte_por_motivo(self):
        client = create_app(self.db, somente_leitura=True).test_client()
        datas = {'inicio_a': '2026-11-10', 'fim_a': '2026-11-10',
                 'inicio_b': '2026-11-11', 'fim_b': '2026-11-11', 'origem': 'real'}
        comparacao = client.get('/analises/comparar', query_string=datas)
        self.assertEqual(comparacao.status_code, 200)
        self.assertIn(b'50,0%', comparacao.data)
        self.assertIn(b'100,0%', comparacao.data)
        self.assertEqual(client.get('/analises/comparar?inicio_a=2026-11-10').status_code, 400)
        motivo = {'motivo': 'SEM_DETECCAO'}
        dados = client.get('/api/analises/dados', query_string=motivo).json
        self.assertEqual([item['id'] for item in dados['historico']], [3])
        exportacao = client.get('/api/analises/exportar.csv', query_string=motivo)
        linhas = csv.DictReader(io.StringIO(exportacao.data.decode('utf-8-sig')), delimiter=';')
        self.assertEqual([linha['ID'] for linha in linhas], ['3'])

if __name__ == '__main__':
    unittest.main()
