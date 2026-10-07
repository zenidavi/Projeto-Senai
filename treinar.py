"""Treina YOLOv8 Object Detection com o dataset rotulado no Roboflow."""
from pathlib import Path
from config import (DATA_YAML, MODELO_BASE, EPOCHS, IMG_SIZE, BATCH,
                    PATIENCE, TRAIN_PROJECT, TRAIN_NAME, ROOT_DIR)


def main():
    if not DATA_YAML.is_file():
        print(f"ERRO: data.yaml não encontrado: {DATA_YAML}")
        print("Exporte YOLOv8 do Roboflow e configure DATA_YAML em config.py.")
        return 1
    try:
        from ultralytics import YOLO
        from ultralytics.data.utils import check_det_dataset
    except ImportError as exc:
        print(f"ERRO: dependências indisponíveis ({exc}). Instale requirements.txt.")
        return 1
    try:
        check_det_dataset(str(DATA_YAML), autodownload=False)
    except Exception as exc:
        print(f"ERRO: dataset inválido. Confira caminhos, classes e rótulos: {exc}")
        return 1
    try:
        # Ultralytics pode baixar somente o peso base oficial, se ainda ausente.
        model = YOLO(str(ROOT_DIR / MODELO_BASE), task="detect")
        if model.task != "detect":
            raise ValueError("O modelo precisa ser de Object Detection.")
    except Exception as exc:
        print(f"ERRO: não foi possível carregar {MODELO_BASE}: {exc}")
        return 1
    try:
        model.train(data=str(DATA_YAML), epochs=EPOCHS, imgsz=IMG_SIZE,
                    batch=BATCH, patience=PATIENCE,
                    project=str(TRAIN_PROJECT), name=TRAIN_NAME,
                    exist_ok=False, workers=0)
        best = Path(model.trainer.best).resolve()
        if not best.is_file():
            raise FileNotFoundError(f"Treino terminou sem gerar {best}")
        print(f"Treinamento concluído. best.pt: {best}")
        print("Configure MODEL_PATH em config.py com esse caminho antes da inferência.")
        return 0
    except Exception as exc:
        print(f"ERRO no treinamento: {exc}")
        print("Confira o dataset e reduza BATCH se faltar memória.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
