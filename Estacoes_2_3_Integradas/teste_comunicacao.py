"""Teste de bancada sem webcam nem Arduino mestre.

Mostra como o Python devera falar com o Arduino integrado.
Nao execute com o Arduino conectado ao motor da mesa.

Uso: python teste_comunicacao.py COM3
Requer: pip install pyserial
"""
import sys
import time
import uuid
import serial


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python teste_comunicacao.py COM3")
    porta = sys.argv[1]
    resultados = ("OK", "NOK", "INCONCLUSIVO")
    indice = 0
    print(f"Abrindo {porta} a 9600 baud. Desconecte o mestre para este teste.")
    with serial.Serial(porta, 9600, timeout=0.4, write_timeout=1) as conn:
        time.sleep(2.0)  # Uno reinicia quando a porta USB Serial abre
        print("Aproxime a peça do sensor TCRT5000; retire após cada pulso.")
        atual = None
        estado = "AGUARDANDO"
        limite = None
        while True:
            linha = conn.readline().decode("utf-8", errors="replace").strip()
            if not linha:
                if estado == "ESPERA_ACK" and time.monotonic() > limite:
                    print("AVISO: não chegou ACK do resultado enviado")
                    estado = "AGUARDANDO"
                continue
            print("Arduino:", linha)
            campos = linha.split(";")
            if campos[0] == "START" and len(campos) == 2:
                if estado != "AGUARDANDO":
                    print("AVISO: START inesperado; ignorado")
                    continue
                atual = uuid.uuid4().hex
                conn.write(f"INICIO;{campos[1]};{atual}\n".encode("ascii"))
                estado = "INSPECIONANDO"
                print("Python: INICIO enviado; simulando 1 segundo de câmera")
                time.sleep(1)
                resultado = resultados[indice % len(resultados)]
                indice += 1
                conn.write(f"RESULTADO;{atual};{resultado}\n".encode("ascii"))
                print("Python: resultado enviado:", resultado)
                estado = "ESPERA_ACK"
                limite = time.monotonic() + 2.0
            elif campos[0] == "ACK" and len(campos) == 3:
                if estado == "ESPERA_ACK" and campos[1] == atual:
                    print("CONFIRMADO: Arduino aceitou", campos[2])
                    estado = "AGUARDANDO"
            elif campos[0] == "ERRO":
                print("ERRO do Arduino: não considerar a mesa liberada")
                estado = "AGUARDANDO"


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTeste encerrado.")
