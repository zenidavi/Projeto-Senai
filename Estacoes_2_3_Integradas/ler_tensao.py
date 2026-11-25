"""Monitor Serial de bancada da Estacao 2 (Arduino Uno compartilhado).

Uso:
  python ler_tensao.py COM3
  python ler_tensao.py COM3 --gravar

AVISO: nao executar ao mesmo tempo que inferencia.py com USE_SERIAL=True
ou Monitor Serial da Arduino IDE. Nao envia comandos de movimento.
"""
import argparse
from datetime import datetime
from pathlib import Path
import sqlite3
import time


def interpretar(linha):
    """Retorna (volts, status) ou None quando a linha nao e uma medicao valida."""
    partes = linha.strip().split(";")
    if len(partes) != 3 or partes[0] != "TENSAO":
        return None
    if partes[2] not in ("APROVADO", "REPROVADO"):
        return None
    try:
        valor = float(partes[1])
    except ValueError:
        return None
    if not (0 <= valor <= 2.5):
        return None
    return valor, partes[2]


def preparar_banco(destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(destino) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS medicoes_tensao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            horario_local TEXT NOT NULL,
            tensao_v REAL NOT NULL,
            resultado TEXT NOT NULL,
            porta TEXT NOT NULL
        )""")


def registrar(destino, porta, tensao_v, resultado):
    with sqlite3.connect(destino) as con:
        con.execute("""INSERT INTO medicoes_tensao
            (horario_local, tensao_v, resultado, porta) VALUES (?, ?, ?, ?)""",
            (datetime.now().astimezone().isoformat(timespec="seconds"),
             tensao_v, resultado, porta))


def main():
    parser = argparse.ArgumentParser(description="Ler tensao do Arduino Uno")
    parser.add_argument("porta", help="Ex.: COM3")
    parser.add_argument("--gravar", action="store_true", help="Registra leituras em SQLite")
    parser.add_argument("--db", type=Path,
                        default=Path(__file__).resolve().parent / "tensao_estacao2.db")
    args = parser.parse_args()

    try:
        import serial
    except ImportError as exc:
        raise SystemExit("PySerial ausente: instale requirements.txt") from exc

    if args.gravar:
        preparar_banco(args.db)
        print(f"Gravando medições em: {args.db}")
    else:
        print("Apenas monitorando; sem gravar no banco. Use --gravar depois de calibrar.")

    print("Porta:", args.porta, "| 9600 baud | Ctrl+C para encerrar")
    print("Feche o Monitor Serial da Arduino IDE antes de continuar.")
    try:
        with serial.Serial(args.porta, 9600, timeout=1.0, write_timeout=1.0) as porta:
            time.sleep(2.0)  # Um Uno normalmente reinicia ao abrir a Serial
            while True:
                linha = porta.readline().decode("utf-8", errors="replace").strip()
                if not linha:
                    continue
                medicao = interpretar(linha)
                if medicao is None:
                    print("Arduino:", linha)
                    continue
                tensao, resultado = medicao
                print(f"Tensão: {tensao:.2f} V | {resultado}")
                if args.gravar:
                    registrar(args.db, args.porta, tensao, resultado)
    except KeyboardInterrupt:
        print("\nMonitor encerrado.")
    except (OSError, sqlite3.Error) as exc:
        raise SystemExit(f"Falha de comunicação/gravação: {exc}") from exc


if __name__ == "__main__":
    main()
