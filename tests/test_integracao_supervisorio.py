"""Validação da consolidação sem câmera, pesos ou Arduino."""
import tempfile
import unittest
from pathlib import Path
from supervisorio.app import create_app
from supervisorio.database import registrar_inspecao

class IntegracaoTestes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "inspecoes.db"
        self.app = create_app(db_path=self.db, image_dir=Path(self.tmp.name))
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_sem_camera_e_com_painel(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/analises").status_code, 200)
        self.assertEqual(self.client.get("/api/video/frame").status_code, 503)
        self.assertEqual(self.client.get("/api/video/controle/estado").status_code, 200)
        self.assertEqual(self.client.post("/api/video/controle/inspecionar").status_code, 403)

    def test_relatorios(self):
        registrar_inspecao("OK", "tampa_ok", 0.95, db_path=self.db,
                           motivo="DETECCAO_ESTAVEL", modelo_versao="teste")
        registrar_inspecao("INCONCLUSIVO", db_path=self.db, motivo="SEM_DETECCAO")
        dados = self.client.get("/api/analises/dados").get_json()
        self.assertEqual(dados["resumo"]["total"], 2)
        self.assertEqual(dados["resumo"]["ok"], 1)
        self.assertEqual(dados["resumo"]["inconclusivos"], 1)
        filtrado = self.client.get("/api/analises/dados?resultado=OK").get_json()
        self.assertEqual(filtrado["resumo"]["total"], 1)
        csv = self.client.get("/api/analises/exportar.csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn(b"tampa_ok", csv.data)
        pdf = self.client.get("/api/analises/relatorio.pdf")
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.data.startswith(b"%PDF-"))

    def test_filtros_invalidos(self):
        self.assertEqual(self.client.get("/api/analises/dados?resultado=INVALIDO").status_code, 400)
        self.assertEqual(self.client.get("/api/analises/dados?inicio=2026-19-99").status_code, 400)
        self.assertEqual(self.client.get("/api/analises/dados?pagina=texto").status_code, 400)

if __name__ == "__main__":
    unittest.main()
