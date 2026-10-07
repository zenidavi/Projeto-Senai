"""Configuração central da Estação 3; caminhos relativos à raiz do projeto."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
CAM_INDEX = 0
DATASET_DIR = ROOT_DIR / "dataset"
DATA_YAML = ROOT_DIR / "dataset_roboflow" / "data.yaml"
MODELO_BASE = "yolov8n.pt"  # Object Detection, não -cls.
TRAIN_PROJECT = ROOT_DIR / "runs" / "estacao3"
TRAIN_NAME = "tampa"
EPOCHS = 100
IMG_SIZE = 640
BATCH = 16
PATIENCE = 20
MODEL_PATH = TRAIN_PROJECT / TRAIN_NAME / "weights" / "best.pt"
CONF_THRESHOLD = 0.70
STABLE_FRAMES = 5
COOLDOWN_SECONDS = 2.0
REARM_FRAMES = 10  # Sem nenhuma detecção: retirada da peça.
CLASS_RESULTS = {"tampa_ok": "OK", "tampa_nok": "NOK"}
USE_SERIAL = False
SERIAL_PORT = "COM3"
BAUD_RATE = 9600
SERIAL_RESET_SECONDS = 2.0  # Uno reinicia ao abrir a porta USB.
# Use ESTACAO3_DB nos dois terminais para escolher outro banco.
_db = Path(os.environ.get("ESTACAO3_DB", "supervisorio/inspecoes.db"))
DATABASE_PATH = _db if _db.is_absolute() else ROOT_DIR / _db
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
POLL_INTERVAL_MS = 2000

# Ciclo explícito: I inicia uma inspeção no preview. Automático é demonstração.
INSPECTION_MODE = "manual"  # "manual" ou "automatico"
INSPECTION_TIMEOUT_SECONDS = 5.0
HEARTBEAT_SECONDS = 1.0
STATION_STALE_SECONDS = 8.0
MODEL_VERSION = "tampa-v1"  # A inferência acrescenta o hash dos pesos reais.
SAVE_IMAGES = True
SAVE_IMAGE_RESULTS = ("OK", "NOK", "INCONCLUSIVO")
IMAGE_DIR = ROOT_DIR / "inspecoes_imagens"
SERIAL_REQUIRE_ACK = True
SERIAL_ACK_TIMEOUT = 1.0
