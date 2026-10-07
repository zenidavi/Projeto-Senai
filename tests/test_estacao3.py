"""Validação de software, sem câmera, pesos treinados ou Arduino físico."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import importlib
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import serial
import config
import inferencia
import captura_dataset
import treinar
from supervisorio import database
from supervisorio.app import create_app


def decisao(resultado="OK", classe="tampa_ok"):
    return {"resultado": resultado, "classe_detectada": classe, "confianca": 0.91}


class BancoAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "teste.db"
        self.client = create_app(self.db).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_vazio_e_estaticos(self):
        dados = self.client.get("/api/status").get_json()
        self.assertIsNone(dados["ultima"])
        self.assertEqual(dados["contagens"]["total"], 0)
        self.assertEqual(dados["grafico"]["valores"], [0, 0, 0])
        self.assertEqual(self.client.get("/api/historico").get_json(), [])
        for rota in ("/", "/static/style.css", "/static/dashboard.js"):
            response = self.client.get(rota)
            self.assertEqual(response.status_code, 200)
            response.close()

    def test_registros_percentuais_e_grafico(self):
        for resultado, classe in [("OK", "tampa_ok"), ("NOK", "tampa_nok"), ("OK", "tampa_ok")]:
            database.registrar_inspecao(resultado, classe, .91, db_path=self.db)
        dados = self.client.get("/api/status").get_json()
        self.assertEqual(dados["contagens"], {"total": 3, "ok": 2, "nok": 1,
                         "percentual_ok": 66.7, "percentual_nok": 33.3,
                         "inconclusivo": 0, "percentual_inconclusivo": 0})
        self.assertEqual(dados["ultima"]["id"], 3)
        self.assertEqual(dados["ultima"]["origem"], "real")
        self.assertEqual(dados["grafico"]["valores"], [2, 1, 0])
        self.assertEqual([r["id"] for r in dados["historico"]], [3, 2, 1])

    def test_invalidos_nao_gravam(self):
        for resultado, confianca in [("TALVEZ", .9), ("OK", 1.1), ("OK", float("nan"))]:
            with self.assertRaises(ValueError):
                database.registrar_inspecao(resultado, "tampa_ok", confianca, db_path=self.db)
        self.assertEqual(database.buscar_contagem(self.db)["total"], 0)

    def test_acesso_simultaneo(self):
        def operacao(indice):
            if indice % 3 == 0:
                return database.buscar_status(self.db)
            return database.registrar_inspecao("OK", "tampa_ok", .88, db_path=self.db)
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(operacao, range(60)))
        self.assertEqual(database.buscar_contagem(self.db)["total"], 40)
        self.assertEqual(len(database.buscar_inspecoes_recentes(db_path=self.db)), 20)

    def test_confirmacao_sqlite_serial_loopback(self):
        with serial.serial_for_url("loop://", timeout=1) as porta:
            with redirect_stdout(io.StringIO()):
                inferencia.confirmar_inspecao(decisao("NOK", "tampa_nok"), porta, self.db)
            self.assertEqual(porta.readline(), b"NOK\n")
        self.assertEqual(database.buscar_status(self.db)["ultima"]["resultado"], "NOK")

    def test_serial_falha_preserva_banco(self):
        porta = MagicMock()
        porta.write.side_effect = serial.SerialException("desconectado")
        with redirect_stdout(io.StringIO()):
            inferencia.confirmar_inspecao(decisao(), porta, self.db)
        self.assertEqual(database.buscar_contagem(self.db)["total"], 1)


class EstabilidadeTests(unittest.TestCase):
    def test_oscila_nao_confirma(self):
        e = inferencia.Estabilidade(frames=3)
        for i in range(10):
            d = decisao() if i % 2 else decisao("NOK", "tampa_nok")
            self.assertIsNone(e.atualizar(d, True, i))
        self.assertIsNone(e.atualizar(None, False, 11))
        self.assertEqual(e.seguidos, 0)

    def test_confirma_uma_vez_rearma_cooldown(self):
        e = inferencia.Estabilidade(frames=2, cooldown=5, rearm_frames=2)
        self.assertIsNone(e.atualizar(decisao(), True, 0))
        self.assertEqual(e.atualizar(decisao(), True, 1), decisao())
        for i in range(2, 8):
            self.assertIsNone(e.atualizar(decisao("NOK", "tampa_nok"), True, i))
        e.atualizar(None, False, 8)
        self.assertTrue(e.bloqueado)
        e.atualizar(None, False, 9)
        self.assertFalse(e.bloqueado)
        self.assertIsNone(e.atualizar(decisao(), True, 10))
        self.assertEqual(e.atualizar(decisao(), True, 11), decisao())

    def test_cooldown_mesmo_apos_retirada(self):
        e = inferencia.Estabilidade(frames=1, cooldown=5, rearm_frames=1)
        self.assertIsNotNone(e.atualizar(decisao(), True, 0))
        e.atualizar(None, False, 1)
        self.assertIsNone(e.atualizar(decisao(), True, 2))
        self.assertIsNotNone(e.atualizar(decisao(), True, 5))

    def test_decisao_ambiguidades_e_limiar(self):
        ok = {"classe": "tampa_ok", "confianca": .9}
        nok = {"classe": "tampa_nok", "confianca": .9}
        self.assertIsNone(inferencia.determinar_resultado([]))
        self.assertIsNone(inferencia.determinar_resultado([ok, nok]))
        self.assertIsNone(inferencia.determinar_resultado([{"classe": "outra", "confianca": .99}]))
        self.assertIsNone(inferencia.determinar_resultado([{"classe": "tampa_ok", "confianca": .69}]))
        self.assertEqual(inferencia.determinar_resultado([nok])["resultado"], "NOK")


class ScriptsTests(unittest.TestCase):
    def test_processar_boxes_do_detector(self):
        box = types.SimpleNamespace(cls=MagicMock(), conf=MagicMock())
        box.cls.item.return_value = 1
        box.conf.item.return_value = .92
        resultado = types.SimpleNamespace(names={0: "tampa_ok", 1: "tampa_nok"},
                                          boxes=[box], plot=MagicMock(return_value="preview"))
        model = MagicMock()
        model.predict.return_value = [resultado]
        preview, deteccoes = inferencia.processar_frame(model, "frame")
        self.assertEqual(preview, "preview")
        self.assertEqual(deteccoes, [{"classe": "tampa_nok", "confianca": .92}])
        self.assertEqual(model.predict.call_args.kwargs["conf"], config.CONF_THRESHOLD)

    def test_loop_inferencia_sem_hardware(self):
        with tempfile.TemporaryDirectory() as pasta:
            db = Path(pasta) / "fluxo.db"
            frame = np.zeros((120, 400, 3), dtype=np.uint8)
            cap = MagicMock()
            cap.read.return_value = (True, frame)
            deteccoes = [{"classe": "tampa_ok", "confianca": .95}]
            registrar = inferencia.registrar_ciclo
            # Comando I e sete frames da mesma peça produzem uma confirmação.
            with patch.object(inferencia, "carregar_modelo", return_value=MagicMock()), \
                 patch.object(inferencia, "abrir_camera", return_value=cap), \
                 patch.object(inferencia, "conectar_serial", return_value=None), \
                 patch.object(inferencia, "processar_frame", return_value=(frame, deteccoes)), \
                 patch.object(inferencia, "inicializar_banco", side_effect=lambda: database.inicializar_banco(db)), \
                 patch.object(inferencia, "registrar_ciclo", side_effect=lambda e, p, f, v: registrar(e, p, f, v, db_path=db)), \
                 patch.object(inferencia, "publicar_estado", side_effect=lambda s, d: database.publicar_estado(s, d, db)), \
                 patch.object(inferencia, "versao_modelo", return_value="TESTE"), \
                 patch.object(config, "SAVE_IMAGES", False), \
                 patch("cv2.imshow"), patch("cv2.destroyAllWindows"), \
                 patch("cv2.waitKey", side_effect=[ord("i")] + [-1] * 6 + [ord("q")]), \
                 redirect_stdout(io.StringIO()):
                self.assertEqual(inferencia.main(), 0)
            self.assertEqual(database.buscar_contagem(db)["total"], 1)
            cap.release.assert_called_once()

    def test_importar_nao_abre_camera(self):
        with patch("cv2.VideoCapture") as camera:
            importlib.reload(importlib.import_module("listar_cameras"))
            importlib.import_module("supervisorio.simulador")
            camera.assert_not_called()

    def test_preview_salva_mesmo_frame_limpo(self):
        frame = np.full((120, 400, 3), 123, dtype=np.uint8)
        camera = MagicMock()
        camera.isOpened.return_value = True
        camera.read.return_value = (True, frame)
        with tempfile.TemporaryDirectory() as pasta:
            with patch.object(captura_dataset, "OUTPUT_DIR", Path(pasta)), \
                 patch("cv2.VideoCapture", return_value=camera), \
                 patch("cv2.imshow"), patch("cv2.destroyAllWindows"), \
                 patch("cv2.waitKey", side_effect=[ord("1"), ord("q")]), \
                 patch("cv2.imwrite", return_value=True) as salvar, \
                 redirect_stdout(io.StringIO()):
                captura_dataset.main()
                self.assertEqual(camera.read.call_count, 2)
                self.assertTrue(np.array_equal(salvar.call_args.args[1], np.full_like(frame, 123)))
                camera.release.assert_called_once()

    def test_sequencia_com_lacuna(self):
        with tempfile.TemporaryDirectory() as pasta, patch.object(captura_dataset, "OUTPUT_DIR", Path(pasta)):
            captura_dataset.criar_pastas()
            (Path(pasta) / "tampa_ok" / "tampa_ok_0007.jpg").touch()
            contador = captura_dataset.criar_pastas()
            self.assertEqual(contador["tampa_ok"], 7)

    def test_modelo_ausente_e_serial_indisponivel(self):
        with self.assertRaises(FileNotFoundError):
            inferencia.carregar_modelo("arquivo-inexistente.pt")
        with patch.object(config, "USE_SERIAL", True), \
             patch("serial.Serial", side_effect=serial.SerialException("sem Arduino")), \
             redirect_stdout(io.StringIO()):
            self.assertIsNone(inferencia.conectar_serial())

    def test_treino_caminho_efetivo_e_erros(self):
        with tempfile.TemporaryDirectory() as pasta:
            yaml = Path(pasta) / "data.yaml"
            yaml.touch()
            best = Path(pasta) / "tampa3" / "weights" / "best.pt"
            best.parent.mkdir(parents=True)
            best.touch()
            model = MagicMock(task="detect")
            model.trainer.best = best
            yolo = MagicMock(return_value=model)
            check = MagicMock()
            fake = {"ultralytics": types.SimpleNamespace(YOLO=yolo),
                    "ultralytics.data": types.ModuleType("ultralytics.data"),
                    "ultralytics.data.utils": types.SimpleNamespace(check_det_dataset=check)}
            with patch.dict("sys.modules", fake), patch.object(treinar, "DATA_YAML", yaml):
                texto = io.StringIO()
                with redirect_stdout(texto):
                    self.assertEqual(treinar.main(), 0)
                self.assertIn(str(best.resolve()), texto.getvalue())
                self.assertEqual(model.train.call_args.kwargs["name"], "tampa")
                check.assert_called_with(str(yaml), autodownload=False)
                check.side_effect = ValueError("dataset inválido")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(treinar.main(), 1)
                check.side_effect = None
                yolo.side_effect = RuntimeError("modelo inválido")
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(treinar.main(), 1)
            with patch.object(treinar, "DATA_YAML", Path(pasta) / "ausente.yaml"), redirect_stdout(io.StringIO()):
                self.assertEqual(treinar.main(), 1)


if __name__ == "__main__":
    unittest.main()
