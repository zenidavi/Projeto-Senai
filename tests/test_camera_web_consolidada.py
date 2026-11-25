"""Testes locais da integração; sem webcam, Arduino ou pesos reais."""
import re
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import config as cfg
from supervisorio import camera_web as cam
from supervisorio.database import publicar_estado


class TesteCameraWeb(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mock_dir = patch.object(cfg, 'IMAGE_DIR', Path(self.temp.name))
        self.mock_dir.start()
        self.addCleanup(self.mock_dir.stop)

    def test_bloqueios_de_seguranca(self):
        with patch.object(cfg, 'USE_SERIAL', True):
            self.assertFalse(cam.configuracao_segura_controle()[0])
        with patch.object(cfg, 'USE_SERIAL', False), patch.object(cfg, 'INSPECTION_MODE', 'automatico'):
            self.assertFalse(cam.configuracao_segura_controle()[0])
        with patch.object(cfg, 'USE_SERIAL', False), patch.object(cfg, 'INSPECTION_MODE', 'manual'):
            self.assertTrue(cam.configuracao_segura_controle()[0])

    def test_comando_unico_e_confirmacao_logica(self):
        with patch.object(cfg, 'USE_SERIAL', False), patch.object(cfg, 'INSPECTION_MODE', 'manual'):
            ident='a'*32
            cam.gravar_json_atomico(cam.caminho_comando(),
                {'id':ident,'acao':'inspecionar','emitido_em':time.time()})
            iniciar = Mock(return_value=True)
            self.assertTrue(cam.consumir_comando(iniciar))
            self.assertFalse(cam.consumir_comando(iniciar))
            iniciar.assert_called_once()
            self.assertEqual(cam.caminho_ack().read_text(encoding='utf-8').count(ident),1)

    def test_comando_expirado_nao_executado(self):
        with patch.object(cfg, 'USE_SERIAL', False), patch.object(cfg, 'INSPECTION_MODE', 'manual'):
            cam.gravar_json_atomico(cam.caminho_comando(),
                {'id':'b'*32,'acao':'inspecionar','emitido_em':time.time()-30})
            iniciar = Mock()
            self.assertFalse(cam.consumir_comando(iniciar))
            iniciar.assert_not_called()
            self.assertFalse(cam.caminho_comando().exists())

    def test_preview_recupera_de_falha_de_rename(self):
        codificado = SimpleNamespace(tobytes=lambda: b'jpeg')
        cv2 = SimpleNamespace(imencode=Mock(return_value=(True, codificado)),
                              IMWRITE_JPEG_QUALITY=1, error=RuntimeError)
        erro = PermissionError('Arquivo em uso')
        erro.winerror = 5
        preview = cam.PreviewWeb()
        preview.destino.parent.mkdir()
        preview.destino.write_bytes(b'ultimo jpeg valido')
        frame = SimpleNamespace(shape=(100, 100))

        with patch.object(cam.time, 'monotonic', return_value=10), patch.object(cam.os, 'replace', side_effect=erro):
            preview.publicar(cv2, frame)
            preview.publicar(cv2, frame)
        self.assertEqual(preview.destino.read_bytes(), b'ultimo jpeg valido')
        self.assertEqual(preview.metricas['falhas_publicacao_jpeg'], 1)
        self.assertEqual(preview.metricas['ultimo_erro_publicacao_jpeg'], 'WinError 5')
        cv2.imencode.assert_called_once()
        self.assertEqual(list(preview.destino.parent.glob('*.tmp')), [])
        with patch.object(cam.time, 'monotonic', return_value=11):
            preview.publicar(cv2, frame)
        self.assertEqual(preview.destino.read_bytes(), b'jpeg')
        self.assertTrue(preview.pronto.is_file())
        self.assertGreaterEqual(preview.metricas['latencia_publicacao_jpeg_ms'], 0)
        preview.limpar()
        self.assertFalse(preview.destino.exists())

    def test_rotas_e_pagina_em_flask(self):
        from supervisorio.app import create_app
        with patch.object(cfg,'USE_SERIAL',False), patch.object(cfg,'INSPECTION_MODE','manual'):
            db_path = Path(self.temp.name) / 'teste.db'
            image_dir = Path(self.temp.name) / 'imagens-do-app'
            app = create_app(db_path=db_path, image_dir=image_dir)
            client=app.test_client()
            resposta=client.get('/')
            self.assertEqual(resposta.status_code,200)
            self.assertIn(b'estacao3-camera-supervisorio',resposta.data)
            self.assertEqual(client.post('/api/video/controle/inspecionar').status_code,403)
            self.assertEqual(client.get('/api/video/controle/estado').status_code,200)
            self.assertEqual(client.get('/api/video/frame').status_code,503)

            publicar_estado(uuid4().hex, {
                'ativo': True, 'origem': 'real', 'estado': 'AGUARDANDO',
                'camera': True, 'modelo': True,
            }, db_path=db_path)
            cam.pasta_preview(image_dir).mkdir(parents=True)
            cam.caminho_pronto(image_dir).write_text('sessao', encoding='ascii')
            cam.caminho_preview(image_dir).write_bytes(b'frame-de-teste')

            self.assertTrue(client.get('/api/video/controle/estado').json['pronto'])
            frame = client.get('/api/video/frame')
            self.assertEqual(frame.status_code, 200)
            self.assertEqual(frame.data, b'frame-de-teste')
            self.assertEqual(frame.mimetype, 'image/jpeg')
            jpg = cam.caminho_preview(image_dir)
            passado = time.time() - cam.TEMPO_MAXIMO_FRAME - 1
            os.utime(jpg, (passado, passado))
            self.assertEqual(client.get('/api/video/frame').status_code, 503)
            self.assertFalse(client.get('/api/video/controle/estado').json['pronto'])
            os.utime(jpg)
            token = re.search(rb'data-token="([a-f0-9]{64})"', resposta.data)[1].decode()
            comando = client.post('/api/video/controle/inspecionar',
                                  headers={'X-Estacao3-Token': token})
            self.assertEqual(comando.status_code, 202)
            self.assertTrue(cam.caminho_comando(image_dir).is_file())
            self.assertFalse(cam.caminho_comando().exists())
            with patch.object(cfg, 'IMAGE_DIR', image_dir):
                self.assertTrue(cam.consumir_comando(lambda: True))
            ident = comando.json['solicitacao_id']
            self.assertEqual(client.get(f'/api/video/controle/comando/{ident}').json,
                             {'entregue': True, 'aceito': True})

            recusado = 'c' * 32
            cam.gravar_json_atomico(cam.caminho_comando(image_dir),
                {'id': recusado, 'acao': 'inspecionar', 'emitido_em': time.time()})
            with patch.object(cfg, 'IMAGE_DIR', image_dir):
                self.assertFalse(cam.consumir_comando(lambda: False))
            self.assertEqual(client.get(f'/api/video/controle/comando/{recusado}').json,
                             {'entregue': True, 'aceito': False})

            with patch.object(cfg, 'USE_SERIAL', True):
                self.assertEqual(client.post('/api/video/controle/inspecionar',
                                             headers={'X-Estacao3-Token': token}).status_code, 409)

if __name__=='__main__':
    unittest.main()
