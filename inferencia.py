"""Webcam → YOLOv8 → estabilidade → SQLite → Serial USB opcional."""
import time
from pathlib import Path
import config as cfg
from supervisorio.database import (inicializar_banco, registrar_inspecao,
                                   publicar_estado, atualizar_serial)
from ciclo import CicloInspecao
from uuid import uuid4
import hashlib
import re


def carregar_modelo(caminho=cfg.MODEL_PATH):
    if not Path(caminho).is_file():
        raise FileNotFoundError(f"best.pt não encontrado: {caminho}. Treine e configure MODEL_PATH.")
    from ultralytics import YOLO
    model = YOLO(str(caminho), task="detect")
    if model.task != "detect":
        raise ValueError("Use pesos de Object Detection, não classificação -cls.")
    nomes = set(model.names.values())
    if not nomes.intersection(cfg.CLASS_RESULTS):
        raise ValueError(f"Classes do modelo {nomes} não estão em CLASS_RESULTS.")
    return model


def abrir_camera(indice=cfg.CAM_INDEX):
    import cv2
    cap = cv2.VideoCapture(indice, cv2.CAP_MSMF)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Não foi possível abrir webcam {indice}. Execute listar_cameras.py.")
    return cap


def processar_frame(model, frame):
    resultado = model.predict(frame, conf=cfg.CONF_THRESHOLD,
                              imgsz=cfg.IMG_SIZE, verbose=False)[0]
    deteccoes = []
    for box in resultado.boxes:
        deteccoes.append({"classe": resultado.names[int(box.cls.item())],
                          "confianca": float(box.conf.item())})
    return resultado.plot(), deteccoes


def determinar_resultado(deteccoes, limiar=cfg.CONF_THRESHOLD):
    """Uma peça: múltiplas caixas ou classe desconhecida aguardam avaliação."""
    validas = [d for d in deteccoes if d["confianca"] >= limiar]
    if len(validas) != 1:
        return None
    deteccao = validas[0]
    resultado = cfg.CLASS_RESULTS.get(deteccao["classe"])
    if resultado is None:
        return None
    return {"resultado": resultado, "classe_detectada": deteccao["classe"],
            "confianca": deteccao["confianca"]}


class Estabilidade:
    """Confirma uma vez por peça; rearma após retirada e respeita cooldown."""
    def __init__(self, frames=cfg.STABLE_FRAMES, cooldown=cfg.COOLDOWN_SECONDS,
                 rearm_frames=cfg.REARM_FRAMES):
        if frames < 1 or rearm_frames < 1 or cooldown < 0:
            raise ValueError("Frames devem ser >= 1 e cooldown >= 0.")
        self.frames = frames
        self.cooldown = cooldown
        self.rearm_frames = rearm_frames
        self.chave = None
        self.seguidos = 0
        self.ausentes = 0
        self.bloqueado = False
        self.ultima_confirmacao = float("-inf")

    def atualizar(self, decisao, presente, agora=None):
        agora = time.monotonic() if agora is None else agora
        self.ausentes = 0 if presente else self.ausentes + 1
        if self.ausentes >= self.rearm_frames:
            self.bloqueado = False
        if decisao is None or self.bloqueado:
            self.chave, self.seguidos = None, 0
            return None
        chave = (decisao["resultado"], decisao["classe_detectada"])
        self.seguidos = self.seguidos + 1 if chave == self.chave else 1
        self.chave = chave
        if self.seguidos >= self.frames and agora - self.ultima_confirmacao >= self.cooldown:
            self.bloqueado = True
            self.ultima_confirmacao = agora
            return decisao.copy()
        return None


def conectar_serial():
    if not cfg.USE_SERIAL:
        print("Serial desabilitada: teste local sem Arduino.")
        return None
    try:
        import serial
        porta = serial.Serial(cfg.SERIAL_PORT, cfg.BAUD_RATE,
                              timeout=1, write_timeout=1)
    except (ImportError, OSError, ValueError) as exc:
        print(f"AVISO: Serial indisponível ({exc}). Continuando sem Arduino.")
        return None
    time.sleep(cfg.SERIAL_RESET_SECONDS)
    print(f"Serial conectada: {cfg.SERIAL_PORT} / {cfg.BAUD_RATE} baud")
    return porta


def enviar_serial(porta, resultado):
    if porta is None:
        return False
    if resultado not in ("OK", "NOK"):
        raise ValueError("Comando Serial inválido.")
    try:
        mensagem = (resultado + "\n").encode("ascii")
        if porta.write(mensagem) != len(mensagem):
            raise OSError("Escrita Serial incompleta")
        porta.flush()
        return True  # Escrito no PC; sem ACK não comprova recepção no Uno.
    except (OSError, TimeoutError) as exc:
        print(f"AVISO: envio Serial falhou ({exc}). Inspeção preservada no banco.")
        return False


def confirmar_inspecao(decisao, porta=None, db_path=cfg.DATABASE_PATH):
    identificador = registrar_inspecao(**decisao, db_path=db_path)
    enviado = enviar_serial(porta, decisao["resultado"])
    print(f"Inspeção #{identificador}: {decisao['resultado']} / "
          f"{decisao['classe_detectada']} / {decisao['confianca']:.1%} "
          f"| Serial: {'escrito' if enviado else 'não enviado'}")
    return identificador


def motivo_deteccao(deteccoes):
    if not deteccoes:
        return "SEM_DETECCAO"
    if len(deteccoes) != 1:
        return "MULTIPLAS_DETECCOES"
    if deteccoes[0]['classe'] not in cfg.CLASS_RESULTS:
        return "CLASSE_DESCONHECIDA"
    if deteccoes[0]['confianca'] < cfg.CONF_THRESHOLD:
        return "BAIXA_CONFIANCA"
    return "SEM_ESTABILIDADE"


def versao_modelo():
    digest = hashlib.sha256()
    with Path(cfg.MODEL_PATH).open('rb') as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b''):
            digest.update(bloco)
    return cfg.MODEL_VERSION + ':' + digest.hexdigest()[:12]


def salvar_imagem(frame, ciclo_id, resultado):
    if not cfg.SAVE_IMAGES or resultado not in cfg.SAVE_IMAGE_RESULTS or frame is None:
        return None, ''
    try:
        if not re.fullmatch(r'[a-f0-9]{32}', ciclo_id):
            raise ValueError('Identificador de imagem inválido')
        import cv2
        cfg.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        caminho = cfg.IMAGE_DIR / (ciclo_id + '.jpg')
        if caminho.exists():
            raise ValueError('Imagem deste ciclo já existe')
        if not cv2.imwrite(str(caminho), frame):
            raise OSError('Falha ao salvar imagem')
        return caminho.name, ''
    except Exception as exc:
        print(f'AVISO: imagem não salva: {exc}')
        return None, 'IMAGEM_NAO_SALVA'


def transmitir_resultado(porta, resultado, ciclo_id):
    # Nunca inventar OK/NOK para inspeção inconclusiva.
    if resultado not in ('OK', 'NOK'):
        return 'nao_aplicavel'
    if not cfg.USE_SERIAL:
        return 'desabilitada'
    if porta is None:
        return 'indisponivel'
    if not cfg.SERIAL_REQUIRE_ACK:
        return 'escrito_sem_ack' if enviar_serial(porta, resultado) else 'erro'
    try:
        if not re.fullmatch(r'[a-f0-9]{32}', ciclo_id):
            raise ValueError('ID de ciclo inválido para Serial')
        porta.reset_input_buffer()
        mensagem = f'RESULTADO;{ciclo_id};{resultado}\n'.encode('ascii')
        if porta.write(mensagem) != len(mensagem):
            raise OSError('Escrita incompleta')
        porta.flush()
        esperado = f'ACK;{ciclo_id};{resultado}'
        prazo = time.monotonic() + cfg.SERIAL_ACK_TIMEOUT
        timeout_anterior = porta.timeout
        try:
            while time.monotonic() < prazo:
                porta.timeout = max(.001, prazo - time.monotonic())
                resposta = porta.readline().decode('ascii', errors='replace').strip()
                if resposta == esperado:
                    return 'confirmado'
            print(f'AVISO: sem ACK para ciclo {ciclo_id}. Resultado continua no banco.')
            return 'sem_confirmacao'
        finally:
            porta.timeout = timeout_anterior
    except (OSError, ValueError) as exc:
        print(f'AVISO: Serial falhou: {exc}')
        return 'erro'


def registrar_ciclo(evento, porta=None, frame=None, modelo_versao='não informado',
                    db_path=cfg.DATABASE_PATH, origem='real'):
    imagem, aviso = salvar_imagem(frame, evento['ciclo_id'], evento['resultado'])
    registro = dict(evento)
    if aviso:
        registro['motivo'] += '; ' + aviso
    # Primeiro persiste, depois transmite. Não repetir envio automaticamente.
    identificador = registrar_inspecao(**registro, imagem_path=imagem,
                                       modelo_versao=modelo_versao, origem=origem,
                                       serial_status='pendente', db_path=db_path)
    status_serial = transmitir_resultado(porta, evento['resultado'], evento['ciclo_id'])
    atualizar_serial(identificador, status_serial, db_path)
    print(f"Ciclo {evento['ciclo_id'][:8]}: {evento['resultado']} / "
          f"{evento['duracao_ms']} ms / {evento['motivo']} / Serial: {status_serial}")
    return {'id': identificador, 'serial_status': status_serial, 'imagem_path': imagem}


def main():
    cap = porta = cv2 = ultimo_frame = None
    sessao = uuid4().hex
    adquirido = False
    ciclo = None
    etapa = 'configuração'
    ultima = None
    estado = {'ativo': True, 'estado': 'INICIALIZANDO', 'origem': 'real',
              'camera': None, 'modelo': None,
              'serial': 'aguardando' if cfg.USE_SERIAL else 'desabilitada',
              'motivo': '', 'ciclo_id': None}
    ultima_publicacao = float('-inf')

    def publicar(forcar=False):
        nonlocal ultima_publicacao
        agora = time.monotonic()
        if forcar or agora - ultima_publicacao >= cfg.HEARTBEAT_SECONDS:
            publicar_estado(sessao, estado)
            ultima_publicacao = agora

    def concluir(evento):
        nonlocal ultima
        info = registrar_ciclo(evento, porta, ultimo_frame, estado.get('modelo_versao', 'não informado'))
        ultima = evento
        estado.update(estado=ciclo.estado, ciclo_id=evento['ciclo_id'],
                      motivo=evento['motivo'], ultima_transmissao=info['serial_status'])
        if info['serial_status'] in ('erro', 'sem_confirmacao', 'indisponivel'):
            estado['serial'] = info['serial_status']
        elif info['serial_status'] == 'confirmado':
            estado['serial'] = 'conectada'
        publicar(True)

    try:
        if not 0 <= cfg.CONF_THRESHOLD <= 1 or cfg.INSPECTION_MODE not in ('manual', 'automatico'):
            raise ValueError('Confira CONF_THRESHOLD e INSPECTION_MODE em config.py.')
        if cfg.SERIAL_ACK_TIMEOUT <= 0 or cfg.HEARTBEAT_SECONDS <= 0:
            raise ValueError('Timeout Serial e heartbeat devem ser positivos.')
        ciclo = CicloInspecao()
        inicializar_banco()
        publicar(True)
        adquirido = True
        etapa = 'modelo'
        model = carregar_modelo()
        estado.update(modelo=True, modelo_versao=versao_modelo())
        publicar(True)
        import cv2
        etapa = 'camera'
        cap = abrir_camera()
        estado['camera'] = True
        porta = conectar_serial()
        estado['serial'] = ('conectada' if porta is not None else 'indisponivel') if cfg.USE_SERIAL else 'desabilitada'
        estado['estado'] = 'AGUARDANDO'
        publicar(True)
        bloqueio_auto = False
        ausentes = 0
        print('Estação pronta. I: iniciar inspeção | Q: sair.')
        while True:
            etapa = 'camera'
            ret, frame = cap.read()
            if not ret:
                ultimo_frame = None  # Não usar foto antiga como evidência desta falha.
                raise RuntimeError('CAMERA_SEM_FRAME: verifique a conexão da webcam.')
            ultimo_frame = frame.copy()
            etapa = 'modelo'
            preview, deteccoes = processar_frame(model, frame)
            etapa = 'operacao'
            decisao = determinar_resultado(deteccoes)
            motivo = motivo_deteccao(deteccoes)
            ausentes = 0 if deteccoes else ausentes + 1
            if cfg.INSPECTION_MODE == 'automatico':
                if ausentes >= cfg.REARM_FRAMES:
                    bloqueio_auto = False
                if deteccoes and not bloqueio_auto and ciclo.estado != 'INSPECIONANDO':
                    if ciclo.iniciar():
                        bloqueio_auto = True
                        estado.update(estado=ciclo.estado, ciclo_id=ciclo.ciclo_id, motivo='')
                        publicar(True)
            evento = ciclo.atualizar(decisao, motivo)
            if evento:
                etapa = 'persistencia'
                concluir(evento)
            if ciclo.estado == 'INSPECIONANDO':
                texto = f'INSPECIONANDO {ciclo.seguidos}/{cfg.STABLE_FRAMES}'
                cor = (0, 210, 255)
            elif ultima:
                texto = f"{ultima['resultado']} | I: novo ciclo"
                cor = {'OK': (80,220,80), 'NOK': (60,60,240)}.get(ultima['resultado'], (0,210,255))
            else:
                texto, cor = 'AGUARDANDO | I: iniciar', (200,200,200)
            cv2.rectangle(preview, (0,0), (preview.shape[1],75), (25,25,25), -1)
            cv2.putText(preview, texto, (10,28), cv2.FONT_HERSHEY_SIMPLEX, .6, cor, 2)
            classe = f"{decisao['classe_detectada']} {decisao['confianca']:.1%}" if decisao else motivo
            cv2.putText(preview, classe + ' | Q: sair', (10,58), cv2.FONT_HERSHEY_SIMPLEX, .55, (230,230,230), 1)
            cv2.imshow('Estacao 3 - Inspecao', preview)
            publicar()
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('i'), ord('I')) and cfg.INSPECTION_MODE == 'manual':
                if ciclo.iniciar():
                    estado.update(estado=ciclo.estado, ciclo_id=ciclo.ciclo_id, motivo='')
                    publicar(True)
                else:
                    print('Ciclo em andamento ou cooldown ativo; comando ignorado.')
            if key in (ord('q'), ord('Q')):
                if ciclo.estado == 'INSPECIONANDO':
                    concluir(ciclo.falhar('CANCELADO_OPERADOR'))
                break
        return 0
    except KeyboardInterrupt:
        if adquirido and ciclo and ciclo.estado == 'INSPECIONANDO':
            concluir(ciclo.falhar('CANCELADO_OPERADOR'))
        return 0
    except Exception as exc:
        print(f'ERRO: {exc}')
        if adquirido:
            if etapa in ('camera', 'modelo'):
                estado[etapa] = False
            estado.update(estado='FALHA', motivo=str(exc))
            try:
                if ciclo and ciclo.estado == 'INSPECIONANDO':
                    concluir(ciclo.falhar(str(exc)))
                publicar(True)
            except Exception as erro_registro:
                print(f'ERRO ao registrar falha: {erro_registro}')
        return 1
    finally:
        if cap is not None:
            cap.release()
        if porta is not None:
            porta.close()
        if cv2 is not None:
            cv2.destroyAllWindows()
        if adquirido:
            estado['ativo'] = False
            try:
                publicar(True)
            except Exception as exc:
                print(f'AVISO: não foi possível publicar encerramento: {exc}')


if __name__ == '__main__':
    raise SystemExit(main())
