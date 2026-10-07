"""Simula ciclos e falhas, somente por execução explícita; banco separado por padrão."""
if __package__ in (None, ''):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import os
import random
import time
from uuid import uuid4
import config as cfg
from ciclo import CicloInspecao
from supervisorio.database import registrar_inspecao, publicar_estado


def simular_ciclo(cenario, rng=None):
    rng = rng or random.Random()
    ciclo = CicloInspecao(frames=cfg.STABLE_FRAMES, cooldown=0)
    ciclo.iniciar(agora=0)
    if cenario == 'camera-falha':
        return ciclo.falhar('CAMERA_DESCONECTADA_SIMULADA', agora=.2), 'FALHA', 'nao_aplicavel'
    if cenario == 'sem-deteccao':
        return ciclo.atualizar(None, 'SEM_DETECCAO', agora=cfg.INSPECTION_TIMEOUT_SECONDS), 'CONCLUIDO', 'nao_aplicavel'
    resultado = rng.choice(['OK', 'OK', 'NOK'])
    decisao = {'resultado': resultado,
               'classe_detectada': 'tampa_ok' if resultado == 'OK' else 'tampa_nok',
               'confianca': round(rng.uniform(.75, .99), 3)}
    evento = None
    for indice in range(cfg.STABLE_FRAMES):
        evento = ciclo.atualizar(decisao, agora=.05 * (indice + 1))
    if evento is None:
        evento = ciclo.atualizar(None, 'SEM_ESTABILIDADE', agora=cfg.INSPECTION_TIMEOUT_SECONDS)
    status = 'simulado_erro' if cenario == 'serial-falha' else 'simulado_confirmado'
    if evento['resultado'] == 'INCONCLUSIVO':
        status = 'nao_aplicavel'
    return evento, ciclo.estado, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quantidade', type=int, default=20)
    parser.add_argument('--intervalo', type=float, default=2.0, help='Segundos entre fases do ciclo')
    parser.add_argument('--seed', type=int, default=None)
    parser.add_argument('--cenario', choices=['normal','misto','sem-deteccao','camera-falha','serial-falha'], default='normal')
    args = parser.parse_args()
    if args.quantidade < 1 or args.intervalo < 0:
        parser.error('Use quantidade >= 1 e intervalo >= 0.')
    db_path = cfg.DATABASE_PATH if os.environ.get('ESTACAO3_DB') else cfg.ROOT_DIR / 'supervisorio/simulacao.db'
    rng, sessao = random.Random(args.seed), uuid4().hex
    adquirido = False
    estado = {'ativo': True, 'origem': 'simulador', 'estado': 'AGUARDANDO',
              'camera': True, 'modelo': True, 'serial': 'simulada',
              'modelo_versao': 'SIMULADO', 'motivo': '', 'ciclo_id': None}

    def publicar():
        publicar_estado(sessao, estado, db_path)

    def esperar():
        prazo = time.monotonic() + args.intervalo
        while time.monotonic() < prazo:
            time.sleep(min(cfg.HEARTBEAT_SECONDS, max(0, prazo - time.monotonic())))
            publicar()

    print(f'SIMULAÇÃO EXPLÍCITA — banco: {db_path}')
    try:
        publicar()
        adquirido = True
        for indice in range(args.quantidade):
            cenario = (['normal','sem-deteccao','camera-falha','serial-falha'][indice % 4]
                       if args.cenario == 'misto' else args.cenario)
            evento, estado_final, serial_status = simular_ciclo(cenario, rng)
            estado.update(estado='AGUARDANDO', camera=True, serial='simulada', motivo='')
            publicar()
            esperar()
            estado.update(estado='INSPECIONANDO', ciclo_id=evento['ciclo_id'])
            publicar()
            esperar()
            identificador = registrar_inspecao(**evento, origem='simulador',
                modelo_versao='SIMULADO', serial_status=serial_status, db_path=db_path)
            estado.update(estado=estado_final, motivo=evento['motivo'],
                          camera=cenario != 'camera-falha', ultima_transmissao=serial_status,
                          serial='simulada_erro' if cenario == 'serial-falha' else 'simulada')
            publicar()
            print(f"#{identificador} / {cenario}: {evento['resultado']} / {evento['motivo']}")
            esperar()
    except KeyboardInterrupt:
        print('Simulação encerrada.')
    except Exception as exc:
        print(f'ERRO: {exc}')
        return 1
    finally:
        if adquirido:
            estado['ativo'] = False
            publicar()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
