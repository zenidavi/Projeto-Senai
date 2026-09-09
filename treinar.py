"""
Treinamento do modelo YOLO - Inspecao de tampa
Projeto SENAI/VW - mesa giratoria

Antes de rodar:
    1. Baixe e extraia o dataset rotulado no Roboflow (formato YOLOv8)
    2. Ajuste o caminho DATA_YAML abaixo para apontar para o arquivo data.yaml extraido

Como usar:
    python treinar.py
"""

from ultralytics import YOLO

# ---------- Configuracoes ----------
DATA_YAML = "dataset_roboflow/data.yaml"   # caminho para o data.yaml do Roboflow
MODELO_BASE = "yolov8n.pt"                 # nano: leve e rapido, ideal para 2 classes
EPOCHS = 100
IMG_SIZE = 640
BATCH = 16
# ------------------------------------


def main():
    print("Carregando modelo base...")
    model = YOLO(MODELO_BASE)

    print("Iniciando treinamento (isso pode levar de minutos a algumas horas na CPU)...")
    model.train(
        data=DATA_YAML,
        epochs=EPOCHS,
        imgsz=IMG_SIZE,
        batch=BATCH,
        patience=20,   # para o treino antes se nao houver melhora em 20 epocas
    )

    print("\nTreinamento concluido!")
    print("Pesos finais salvos em: runs/detect/train/weights/best.pt")


if __name__ == "__main__":
    main()
