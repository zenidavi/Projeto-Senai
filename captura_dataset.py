"""
Captura de imagens para dataset YOLO - Estacao de inspecao de tampa
Projeto SENAI/VW - mesa giratoria

Como usar:
    python captura_dataset.py

Teclas:
    1       -> salva o frame atual na pasta dataset/tampa_ok
    2       -> salva o frame atual na pasta dataset/tampa_nok
    q       -> encerra o programa

O contador de cada classe aparece na tela e tambem no terminal a cada captura.
"""

import cv2
import os
from datetime import datetime

# ---------- Configuracoes ----------
CAM_INDEX = 0                # indice da webcam (ajuste se necessario)
OUTPUT_DIR = "dataset"       # pasta raiz onde as imagens serao salvas
CLASSES = {
    ord('1'): "tampa_ok",
    ord('2'): "tampa_nok",
}
# ------------------------------------


def criar_pastas():
    for classe in CLASSES.values():
        caminho = os.path.join(OUTPUT_DIR, classe)
        os.makedirs(caminho, exist_ok=True)
    return {classe: len(os.listdir(os.path.join(OUTPUT_DIR, classe)))
            for classe in CLASSES.values()}


def salvar_frame(frame, classe, contador):
    contador[classe] += 1
    nome_arquivo = f"{classe}_{contador[classe]:04d}.jpg"
    caminho = os.path.join(OUTPUT_DIR, classe, nome_arquivo)
    cv2.imwrite(caminho, frame)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Salvo: {caminho}")
    return contador


def main():
    contador = criar_pastas()

    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_MSMF)
    if not cap.isOpened():
        print("ERRO: nao foi possivel abrir a webcam. Verifique o indice CAM_INDEX.")
        return

    print("=" * 50)
    print("Captura de dataset iniciada")
    print("Tecla 1 = salvar como TAMPA OK")
    print("Tecla 2 = salvar como TAMPA NOK")
    print("Tecla Q = sair")
    print("=" * 50)
    print(f"Contagem atual -> OK: {contador['tampa_ok']} | NOK: {contador['tampa_nok']}")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("ERRO: falha ao ler frame da webcam.")
            break

        # Overlay com instrucoes e contadores na tela
        overlay = frame.copy()
        texto1 = f"[1] OK: {contador['tampa_ok']}"
        texto2 = f"[2] NOK: {contador['tampa_nok']}"
        texto3 = "[Q] Sair"

        cv2.rectangle(overlay, (0, 0), (300, 90), (0, 0, 0), -1)
        frame = cv2.addWeighted(overlay, 0.5, frame, 0.5, 0)

        cv2.putText(frame, texto1, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, texto2, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.putText(frame, texto3, (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        cv2.imshow("Captura de Dataset - Tampa", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            print("Encerrando captura.")
            break
        elif key in CLASSES:
            classe = CLASSES[key]
            # salva o frame SEM o overlay (imagem limpa)
            ret2, frame_limpo = cap.read()
            if ret2:
                contador = salvar_frame(frame_limpo, classe, contador)

    cap.release()
    cv2.destroyAllWindows()

    print("=" * 50)
    print("Resumo final:")
    for classe in CLASSES.values():
        print(f"  {classe}: {contador[classe]} imagens")
    print("=" * 50)


if __name__ == "__main__":
    main()
