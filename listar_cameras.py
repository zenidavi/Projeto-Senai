"""
Testa os indices de camera disponiveis no sistema.
Abre cada camera encontrada por alguns segundos para voce identificar qual e qual.

Como usar:
    python listar_cameras.py

Pressione qualquer tecla para passar para o proximo indice testado.
"""

import cv2

MAX_INDICES_TESTADOS = 5

print("Procurando cameras disponiveis...\n")

for indice in range(MAX_INDICES_TESTADOS):
    cap = cv2.VideoCapture(indice, cv2.CAP_MSMF)

    if not cap.isOpened():
        print(f"Indice {indice}: nao disponivel")
        cap.release()
        continue

    ret, frame = cap.read()
    if not ret:
        print(f"Indice {indice}: abriu mas nao conseguiu ler frame")
        cap.release()
        continue

    print(f"Indice {indice}: OK - resolucao {frame.shape[1]}x{frame.shape[0]}")
    print("  -> Mostrando preview. Pressione qualquer tecla na janela para continuar...")

    cv2.putText(frame, f"INDICE {indice}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
    cv2.imshow(f"Camera - indice {indice}", frame)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    cap.release()

print("\nTeste concluido. Anote o indice da camera USB que voce quer usar.")
