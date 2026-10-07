"""Ciclos, migração, falhas, evidência e ACK sem equipamento físico."""
from contextlib import redirect_stdout, closing
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy as np
import config as cfg
from ciclo import CicloInspecao
import inferencia
from supervisorio import database as db
from supervisorio.app import create_app
from supervisorio.simulador import simular_ciclo


D = {'resultado': 'OK', 'classe_detectada': 'tampa_ok', 'confianca': .92}


class CicloTests(unittest.TestCase):
    def test_inicio_estabilidade_uma_confirmacao_e_cooldown(self):
        c = CicloInspecao(frames=2, timeout=5, cooldown=2)
        self.assertIsNone(c.atualizar(D, agora=0))
        self.assertTrue(c.iniciar(0))
        self.assertFalse(c.iniciar(.1))
        self.assertIsNone(c.atualizar(D, agora=.1))
        evento = c.atualizar(D, agora=.2)
        self.assertEqual(evento['resultado'], 'OK')
        self.assertEqual(evento['duracao_ms'], 200)
        self.assertIsNone(c.atualizar(D, agora=.3))
        self.assertFalse(c.iniciar(1))
        self.assertTrue(c.iniciar(3))
        self.assertNotEqual(c.ciclo_id, evento['ciclo_id'])

    def test_prazo_sem_deteccao_inconclusivo_sem_inventar_classe(self):
        c = CicloInspecao(timeout=1)
        c.iniciar(0)
        evento = c.atualizar(None, 'SEM_DETECCAO', agora=1)
        self.assertEqual(evento['resultado'], 'INCONCLUSIVO')
        self.assertIsNone(evento['confianca'])
        self.assertIsNone(evento['classe_detectada'])
        self.assertEqual(c.estado, 'CONCLUIDO')

    def test_frame_tardio_nao_aprova(self):
        c = CicloInspecao(frames=1, timeout=1)
        c.iniciar(0)
        self.assertEqual(c.atualizar(D, agora=1.1)['resultado'], 'INCONCLUSIVO')

    def test_falha_camera_nao_reprova_peca(self):
        c = CicloInspecao()
        self.assertIsNone(c.falhar('SEM_CAMERA', agora=0))
        c.iniciar(1)
        evento = c.falhar('CAMERA_DESCONECTADA', agora=2)
        self.assertEqual(evento['resultado'], 'INCONCLUSIVO')
        self.assertEqual(c.estado, 'FALHA')
        self.assertIsNone(c.falhar('repetida', agora=3))

    def test_simulador_de_falhas(self):
        for cenario in ('sem-deteccao', 'camera-falha'):
            evento, estado, serial = simular_ciclo(cenario)
            self.assertEqual(evento['resultado'], 'INCONCLUSIVO')
            self.assertEqual(serial, 'nao_aplicavel')
        evento, estado, serial = simular_ciclo('serial-falha')
        self.assertIn(evento['resultado'], ('OK', 'NOK'))
        self.assertEqual(serial, 'simulado_erro')


class BancoCicloTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'banco.db'

    def tearDown(self):
        self.tmp.cleanup()

    def test_migracao_preserva_dados_e_ids(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("""CREATE TABLE inspecoes (id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL, resultado TEXT CHECK(resultado IN ('OK','NOK')),
                classe_detectada TEXT NOT NULL, confianca REAL NOT NULL, origem TEXT NOT NULL)""")
            conn.execute("INSERT INTO inspecoes VALUES(7,'2026-10-07T00:00:00-03:00','OK','tampa_ok',.9,'real')")
        db.inicializar_banco(self.path)
        db.inicializar_banco(self.path)
        antigo = db.buscar_inspecao(7, self.path)
        self.assertEqual(antigo['ciclo_id'], 'legado-7')
        self.assertEqual(antigo['confianca'], .9)
        novo = db.registrar_inspecao('INCONCLUSIVO', motivo='TEMPO_LIMITE', db_path=self.path)
        self.assertGreater(novo, 7)
        self.assertEqual(db.buscar_contagem(self.path)['inconclusivo'], 1)

    def test_ciclo_duplicado_nao_repete_registro(self):
        identificador = uuid4().hex
        db.registrar_inspecao(**D, ciclo_id=identificador, db_path=self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            db.registrar_inspecao(**D, ciclo_id=identificador, db_path=self.path)
        self.assertEqual(db.buscar_contagem(self.path)['total'], 1)

    def test_heartbeat_obsoleto_nao_parece_online(self):
        db.publicar_estado('sessao', {'ativo': True, 'estado': 'AGUARDANDO', 'camera': True}, self.path)
        self.assertTrue(db.buscar_status(self.path)['estacao']['online'])
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("UPDATE estado_estacao SET atualizado_em='2000-01-01T00:00:00+00:00'")
        estado = db.buscar_status(self.path)['estacao']
        self.assertFalse(estado['online'])
        self.assertEqual(estado['estado'], 'SEM_CONEXAO')

    def test_sessoes_concorrentes_recusadas(self):
        db.publicar_estado('real', {'ativo': True, 'estado': 'AGUARDANDO'}, self.path)
        with self.assertRaises(RuntimeError):
            db.publicar_estado('simulador', {'ativo': True}, self.path)
        db.publicar_estado('real', {'ativo': False}, self.path)
        db.publicar_estado('simulador', {'ativo': True}, self.path)

    def test_imagem_real_gravada_e_servida_sem_traversal(self):
        imagens = Path(self.tmp.name) / 'imagens'
        evento, _, _ = simular_ciclo('normal')
        frame = np.full((50, 80, 3), 120, dtype=np.uint8)
        with patch.object(cfg, 'IMAGE_DIR', imagens), patch.object(cfg, 'USE_SERIAL', False), redirect_stdout(io.StringIO()):
            info = inferencia.registrar_ciclo(evento, frame=frame, db_path=self.path)
        self.assertTrue((imagens / info['imagem_path']).is_file())
        client = create_app(self.path, imagens).test_client()
        response = client.get(f"/api/inspecoes/{info['id']}/imagem")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/jpeg')
        response.close()
        indevido = db.registrar_inspecao(**D, imagem_path='../privado.jpg', db_path=self.path)
        self.assertEqual(client.get(f'/api/inspecoes/{indevido}/imagem').status_code, 404)
        self.assertEqual(client.get('/api/inspecoes/999/imagem').status_code, 404)

    def test_falha_imagem_preserva_resultado(self):
        evento, _, _ = simular_ciclo('normal')
        with patch('cv2.imwrite', return_value=False), patch.object(cfg, 'IMAGE_DIR', Path(self.tmp.name)), \
             patch.object(cfg, 'USE_SERIAL', False), redirect_stdout(io.StringIO()):
            info = inferencia.registrar_ciclo(evento, frame=np.zeros((5,5,3), dtype=np.uint8), db_path=self.path)
        registro = db.buscar_inspecao(info['id'], self.path)
        self.assertIsNone(registro['imagem_path'])
        self.assertIn('IMAGEM_NAO_SALVA', registro['motivo'])

    def test_queda_da_camera_durante_ciclo_persiste_inconclusivo(self):
        from unittest.mock import MagicMock
        frame = np.zeros((100, 400, 3), dtype=np.uint8)
        camera = MagicMock()
        camera.read.side_effect = [(True, frame), (False, None)]
        registrar = inferencia.registrar_ciclo
        with patch.object(inferencia, 'carregar_modelo', return_value=MagicMock()), \
             patch.object(inferencia, 'versao_modelo', return_value='TESTE'), \
             patch.object(inferencia, 'abrir_camera', return_value=camera), \
             patch.object(inferencia, 'conectar_serial', return_value=None), \
             patch.object(inferencia, 'inicializar_banco', side_effect=lambda: db.inicializar_banco(self.path)), \
             patch.object(inferencia, 'publicar_estado', side_effect=lambda s,d: db.publicar_estado(s,d,self.path)), \
             patch.object(inferencia, 'registrar_ciclo', side_effect=lambda e,p,f,v: registrar(e,p,f,v,db_path=self.path)), \
             patch.object(inferencia, 'processar_frame', return_value=(frame, [])), \
             patch('cv2.imshow'), patch('cv2.destroyAllWindows'), \
             patch('cv2.waitKey', return_value=ord('i')), redirect_stdout(io.StringIO()):
            self.assertEqual(inferencia.main(), 1)
        registro = db.buscar_status(self.path)['ultima']
        self.assertEqual(registro['resultado'], 'INCONCLUSIVO')
        self.assertIn('CAMERA_SEM_FRAME', registro['motivo'])
        self.assertIsNone(registro['imagem_path'])
        self.assertFalse(db.buscar_status(self.path)['estacao']['camera'])
        camera.release.assert_called_once()

    def test_modelo_ausente_nao_cria_inspecao_ficticia(self):
        with patch.object(inferencia, 'carregar_modelo', side_effect=FileNotFoundError('best.pt ausente')), \
             patch.object(inferencia, 'inicializar_banco', side_effect=lambda: db.inicializar_banco(self.path)), \
             patch.object(inferencia, 'publicar_estado', side_effect=lambda s,d: db.publicar_estado(s,d,self.path)), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(inferencia.main(), 1)
        dados = db.buscar_status(self.path)
        self.assertEqual(dados['contagens']['total'], 0)
        self.assertFalse(dados['estacao']['modelo'])
        self.assertFalse(dados['estacao']['online'])
        self.assertEqual(dados['estacao']['ultimo_estado'], 'FALHA')
        self.assertIn('best.pt ausente', dados['estacao']['ultimo_motivo'])


class PortaSimulada:
    """Representa respostas do Uno; não é hardware nem loopback físico."""
    def __init__(self, correta=True):
        self.timeout = 1
        self.correta = correta
        self.mensagem = None

    def reset_input_buffer(self):
        pass

    def write(self, mensagem):
        self.mensagem = mensagem
        return len(mensagem)

    def flush(self):
        pass

    def readline(self):
        _, ciclo, resultado = self.mensagem.decode().strip().split(';')
        if not self.correta:
            ciclo = '0' * 32  # ACK de outra peça nunca deve valer.
        return f'ACK;{ciclo};{resultado}\n'.encode()


class AckTests(unittest.TestCase):
    def test_ack_correto_e_correlacionado(self):
        porta = PortaSimulada()
        ciclo = uuid4().hex
        with patch.object(cfg, 'USE_SERIAL', True):
            self.assertEqual(inferencia.transmitir_resultado(porta, 'OK', ciclo), 'confirmado')
        self.assertEqual(porta.timeout, 1)

    def test_ack_de_outro_ciclo_recusado(self):
        porta = PortaSimulada(correta=False)
        with patch.object(cfg, 'USE_SERIAL', True), patch.object(cfg, 'SERIAL_ACK_TIMEOUT', .01), redirect_stdout(io.StringIO()):
            self.assertEqual(inferencia.transmitir_resultado(porta, 'NOK', uuid4().hex), 'sem_confirmacao')

    def test_inconclusivo_nao_enviado_como_nok(self):
        porta = PortaSimulada()
        with patch.object(cfg, 'USE_SERIAL', True):
            self.assertEqual(inferencia.transmitir_resultado(porta, 'INCONCLUSIVO', uuid4().hex), 'nao_aplicavel')
        self.assertIsNone(porta.mensagem)


if __name__ == '__main__':
    unittest.main()
