"""Webcam → YOLOv8 → estabilidade → SQLite → Serial USB opcional."""

import time
from pathlib import Path
import config as cfg

from supervisorio.database import (
    inicializar_banco,
    mesmo_banco,
    registrar_inspecao,
    publicar_estado,
    atualizar_serial
)

from ciclo import CicloInspecao
from uuid import uuid4

import hashlib
import re


# ==========================================================
# MODELO YOLO
# ==========================================================

def carregar_modelo(caminho=cfg.MODEL_PATH):
    if not Path(caminho).is_file():
        raise FileNotFoundError(
            f"best.pt não encontrado: {caminho}. "
            f"Treine e configure MODEL_PATH."
        )

    from ultralytics import YOLO

    model = YOLO(str(caminho), task="detect")

    if model.task != "detect":
        raise ValueError(
            "Use pesos de Object Detection, não classificação -cls."
        )

    nomes = set(model.names.values())

    if not nomes.intersection(cfg.CLASS_RESULTS):
        raise ValueError(
            f"Classes do modelo {nomes} não estão em CLASS_RESULTS."
        )

    return model


# ==========================================================
# CÂMERA
# ==========================================================

def abrir_camera(indice=cfg.CAM_INDEX):
    import cv2

    cap = cv2.VideoCapture(indice, cv2.CAP_MSMF)

    if not cap.isOpened():
        cap.release()

        raise RuntimeError(
            f"Não foi possível abrir webcam {indice}. "
            f"Execute listar_cameras.py."
        )

    return cap


# ==========================================================
# PROCESSAMENTO YOLO
# ==========================================================

def processar_frame(model, frame):
    resultado = model.predict(
        frame,
        conf=cfg.CONF_THRESHOLD,
        imgsz=cfg.IMG_SIZE,
        verbose=False
    )[0]

    deteccoes = []

    for box in resultado.boxes:
        deteccoes.append({
            "classe": resultado.names[int(box.cls.item())],
            "confianca": float(box.conf.item())
        })

    return resultado.plot(), deteccoes


def determinar_resultado(deteccoes, limiar=cfg.CONF_THRESHOLD):
    """
    Espera exatamente uma detecção válida.
    """

    validas = [
        d for d in deteccoes
        if d["confianca"] >= limiar
    ]

    if len(validas) != 1:
        return None

    deteccao = validas[0]

    resultado = cfg.CLASS_RESULTS.get(
        deteccao["classe"]
    )

    if resultado is None:
        return None

    return {
        "resultado": resultado,
        "classe_detectada": deteccao["classe"],
        "confianca": deteccao["confianca"]
    }


# ==========================================================
# ESTABILIDADE
# ==========================================================

class Estabilidade:

    def __init__(
        self,
        frames=cfg.STABLE_FRAMES,
        cooldown=cfg.COOLDOWN_SECONDS,
        rearm_frames=cfg.REARM_FRAMES
    ):

        if frames < 1 or rearm_frames < 1 or cooldown < 0:
            raise ValueError(
                "Frames devem ser >= 1 e cooldown >= 0."
            )

        self.frames = frames
        self.cooldown = cooldown
        self.rearm_frames = rearm_frames

        self.chave = None
        self.seguidos = 0
        self.ausentes = 0

        self.bloqueado = False

        self.ultima_confirmacao = float("-inf")


    def atualizar(
        self,
        decisao,
        presente,
        agora=None
    ):

        agora = (
            time.monotonic()
            if agora is None
            else agora
        )

        self.ausentes = (
            0
            if presente
            else self.ausentes + 1
        )

        if self.ausentes >= self.rearm_frames:
            self.bloqueado = False

        if decisao is None or self.bloqueado:
            self.chave = None
            self.seguidos = 0

            return None

        chave = (
            decisao["resultado"],
            decisao["classe_detectada"]
        )

        if chave == self.chave:
            self.seguidos += 1
        else:
            self.seguidos = 1

        self.chave = chave

        if (
            self.seguidos >= self.frames
            and
            agora - self.ultima_confirmacao
            >= self.cooldown
        ):

            self.bloqueado = True
            self.ultima_confirmacao = agora

            return decisao.copy()

        return None


# ==========================================================
# SERIAL
# ==========================================================

def conectar_serial():

    if not cfg.USE_SERIAL:

        print(
            "Serial desabilitada: teste local sem Arduino."
        )

        return None

    try:

        import serial

        porta = serial.Serial(
            cfg.SERIAL_PORT,
            cfg.BAUD_RATE,
            timeout=1,
            write_timeout=1
        )

    except (
        ImportError,
        OSError,
        ValueError
    ) as exc:

        print(
            f"AVISO: Serial indisponível ({exc}). "
            f"Continuando sem Arduino."
        )

        return None

    # Arduino Uno reinicia ao abrir a porta
    time.sleep(
        cfg.SERIAL_RESET_SECONDS
    )

    print(
        f"Serial conectada: "
        f"{cfg.SERIAL_PORT} / "
        f"{cfg.BAUD_RATE} baud"
    )

    return porta


# ==========================================================
# LER COMANDOS DO ARDUINO
# ==========================================================

def ler_comando_arduino(porta):

    if porta is None:
        return None

    comando = None

    try:

        while porta.in_waiting:

            mensagem = (
                porta.readline()
                .decode(
                    "utf-8",
                    errors="ignore"
                )
                .strip()
            )

            if mensagem:

                print(
                    "Arduino:",
                    mensagem
                )

            if mensagem == "START":

                comando = "START"

    except OSError as exc:

        print(
            f"AVISO: erro lendo Serial: {exc}"
        )

    return comando


# ==========================================================
# ENVIAR RESULTADO SIMPLES
# ==========================================================

def enviar_serial(
    porta,
    resultado
):

    if porta is None:
        return False

    if resultado not in (
        "OK",
        "NOK"
    ):

        raise ValueError(
            "Comando Serial inválido."
        )

    try:

        mensagem = (
            resultado + "\n"
        ).encode("ascii")

        if porta.write(
            mensagem
        ) != len(mensagem):

            raise OSError(
                "Escrita Serial incompleta"
            )

        porta.flush()

        return True

    except (
        OSError,
        TimeoutError
    ) as exc:

        print(
            f"AVISO: envio Serial falhou "
            f"({exc}). "
            f"Inspeção preservada no banco."
        )

        return False


# ==========================================================
# CONFIRMAR INSPEÇÃO
# ==========================================================

def confirmar_inspecao(
    decisao,
    porta=None,
    db_path=cfg.DATABASE_PATH
):

    identificador = registrar_inspecao(
        **decisao,
        db_path=db_path
    )

    enviado = enviar_serial(
        porta,
        decisao["resultado"]
    )

    print(
        f"Inspeção #{identificador}: "
        f"{decisao['resultado']} / "
        f"{decisao['classe_detectada']} / "
        f"{decisao['confianca']:.1%} "
        f"| Serial: "
        f"{'escrito' if enviado else 'não enviado'}"
    )

    return identificador


# ==========================================================
# MOTIVO DA NÃO DECISÃO
# ==========================================================

def motivo_deteccao(
    deteccoes
):

    if not deteccoes:
        return "SEM_DETECCAO"

    if len(deteccoes) != 1:
        return "MULTIPLAS_DETECCOES"

    if (
        deteccoes[0]["classe"]
        not in cfg.CLASS_RESULTS
    ):
        return "CLASSE_DESCONHECIDA"

    if (
        deteccoes[0]["confianca"]
        < cfg.CONF_THRESHOLD
    ):
        return "BAIXA_CONFIANCA"

    return "SEM_ESTABILIDADE"


# ==========================================================
# VERSÃO DO MODELO
# ==========================================================

def versao_modelo():

    digest = hashlib.sha256()

    with Path(
        cfg.MODEL_PATH
    ).open(
        "rb"
    ) as arquivo:

        for bloco in iter(
            lambda:
            arquivo.read(
                1024 * 1024
            ),
            b""
        ):

            digest.update(
                bloco
            )

    return (
        cfg.MODEL_VERSION
        + ":"
        + digest.hexdigest()[:12]
    )


# ==========================================================
# SALVAR IMAGEM DA INSPEÇÃO
# ==========================================================

def salvar_imagem(
    frame,
    ciclo_id,
    resultado
):

    if (
        not cfg.SAVE_IMAGES
        or
        resultado
        not in cfg.SAVE_IMAGE_RESULTS
        or
        frame is None
    ):

        return None, ""

    try:

        if not re.fullmatch(
            r"[a-f0-9]{32}",
            ciclo_id
        ):

            raise ValueError(
                "Identificador de imagem inválido"
            )

        import cv2

        cfg.IMAGE_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        caminho = (
            cfg.IMAGE_DIR
            /
            (ciclo_id + ".jpg")
        )

        if caminho.exists():

            raise ValueError(
                "Imagem deste ciclo já existe"
            )

        if not cv2.imwrite(
            str(caminho),
            frame
        ):

            raise OSError(
                "Falha ao salvar imagem"
            )

        return (
            caminho.name,
            ""
        )

    except Exception as exc:

        print(
            f"AVISO: imagem não salva: "
            f"{exc}"
        )

        return (
            None,
            "IMAGEM_NAO_SALVA"
        )


# ==========================================================
# TRANSMITIR RESULTADO AO ARDUINO
# ==========================================================

def transmitir_resultado(
    porta,
    resultado,
    ciclo_id
):

    # Não manda OK/NOK falso
    if resultado not in (
        "OK",
        "NOK"
    ):

        return "nao_aplicavel"

    if not cfg.USE_SERIAL:

        return "desabilitada"

    if porta is None:

        return "indisponivel"

    # MODO SIMPLES ATUAL
    if not cfg.SERIAL_REQUIRE_ACK:

        if enviar_serial(
            porta,
            resultado
        ):

            return "escrito_sem_ack"

        return "erro"

    # MODO COMPLETO COM ACK
    try:

        if not re.fullmatch(
            r"[a-f0-9]{32}",
            ciclo_id
        ):

            raise ValueError(
                "ID de ciclo inválido para Serial"
            )

        porta.reset_input_buffer()

        mensagem = (
            f"RESULTADO;"
            f"{ciclo_id};"
            f"{resultado}\n"
        ).encode(
            "ascii"
        )

        if porta.write(
            mensagem
        ) != len(mensagem):

            raise OSError(
                "Escrita incompleta"
            )

        porta.flush()

        esperado = (
            f"ACK;"
            f"{ciclo_id};"
            f"{resultado}"
        )

        prazo = (
            time.monotonic()
            +
            cfg.SERIAL_ACK_TIMEOUT
        )

        timeout_anterior = (
            porta.timeout
        )

        try:

            while (
                time.monotonic()
                <
                prazo
            ):

                porta.timeout = max(
                    0.001,
                    prazo
                    -
                    time.monotonic()
                )

                resposta = (
                    porta.readline()
                    .decode(
                        "ascii",
                        errors="replace"
                    )
                    .strip()
                )

                if resposta == esperado:

                    return "confirmado"

            print(
                f"AVISO: sem ACK para ciclo "
                f"{ciclo_id}. "
                f"Resultado continua no banco."
            )

            return "sem_confirmacao"

        finally:

            porta.timeout = (
                timeout_anterior
            )

    except (
        OSError,
        ValueError
    ) as exc:

        print(
            f"AVISO: Serial falhou: {exc}"
        )

        return "erro"


# ==========================================================
# REGISTRAR CICLO
# ==========================================================

def registrar_ciclo(
    evento,
    porta=None,
    frame=None,
    modelo_versao="não informado",
    db_path=cfg.DATABASE_PATH,
    origem="real"
):

    imagem, aviso = salvar_imagem(
        frame,
        evento["ciclo_id"],
        evento["resultado"]
    )

    registro = dict(
        evento
    )

    if aviso:

        registro["motivo"] += (
            "; "
            +
            aviso
        )

    identificador = registrar_inspecao(
        **registro,
        imagem_path=imagem,
        modelo_versao=modelo_versao,
        origem=origem,
        serial_status="pendente",
        db_path=db_path
    )

    status_serial = transmitir_resultado(
        porta,
        evento["resultado"],
        evento["ciclo_id"]
    )

    atualizar_serial(
        identificador,
        status_serial,
        db_path
    )

    print(
        f"Ciclo "
        f"{evento['ciclo_id'][:8]}: "
        f"{evento['resultado']} / "
        f"{evento['duracao_ms']} ms / "
        f"{evento['motivo']} / "
        f"Serial: {status_serial}"
    )

    return {
        "id": identificador,
        "serial_status": status_serial,
        "imagem_path": imagem
    }


# ==========================================================
# MAIN
# ==========================================================

def main(*, preview_web=False):
    if mesmo_banco(cfg.DATABASE_PATH, cfg.SIMULATION_DATABASE_PATH):
        print("ERRO: selecione um banco de operação real antes de iniciar a inferência.")
        return 1
    if preview_web:
        from supervisorio.camera_web import PreviewWeb, consumir_comando
        return executar_inferencia(PreviewWeb(), consumir_comando)
    return executar_inferencia()


def executar_inferencia(preview_web=None, ler_comando_web=None):

    cap = None
    porta = None
    cv2 = None
    ultimo_frame = None

    sessao = uuid4().hex

    adquirido = False

    ciclo = None

    etapa = "configuração"

    ultima = None

    estado = {

        "ativo": True,

        "estado": "INICIALIZANDO",

        "origem": "real",

        "camera": None,

        "modelo": None,

        "serial": (
            "aguardando"
            if cfg.USE_SERIAL
            else "desabilitada"
        ),

        "motivo": "",

        "ciclo_id": None
    }

    ultima_publicacao = float(
        "-inf"
    )


    # ------------------------------------------------------
    # PUBLICAR ESTADO
    # ------------------------------------------------------

    def publicar(
        forcar=False
    ):

        nonlocal ultima_publicacao

        agora = time.monotonic()

        if (
            forcar
            or
            agora
            -
            ultima_publicacao
            >=
            cfg.HEARTBEAT_SECONDS
        ):

            if preview_web is not None:
                estado.update(preview_web.metricas)

            publicar_estado(
                sessao,
                estado
            )

            ultima_publicacao = agora


    # ------------------------------------------------------
    # CONCLUIR CICLO
    # ------------------------------------------------------

    def concluir(
        evento
    ):

        nonlocal ultima

        info = registrar_ciclo(
            evento,
            porta,
            ultimo_frame,
            estado.get(
                "modelo_versao",
                "não informado"
            )
        )

        ultima = evento

        estado.update(

            estado=ciclo.estado,

            ciclo_id=evento[
                "ciclo_id"
            ],

            motivo=evento[
                "motivo"
            ],

            ultima_transmissao=
            info[
                "serial_status"
            ]
        )

        if info[
            "serial_status"
        ] in (
            "erro",
            "sem_confirmacao",
            "indisponivel"
        ):

            estado[
                "serial"
            ] = info[
                "serial_status"
            ]

        elif (
            info[
                "serial_status"
            ]
            ==
            "confirmado"
        ):

            estado[
                "serial"
            ] = "conectada"

        publicar(
            True
        )


    # ======================================================
    # EXECUÇÃO PRINCIPAL
    # ======================================================

    try:

        if (
            not
            0
            <=
            cfg.CONF_THRESHOLD
            <=
            1
            or
            cfg.INSPECTION_MODE
            not in (
                "manual",
                "automatico"
            )
        ):

            raise ValueError(
                "Confira CONF_THRESHOLD "
                "e INSPECTION_MODE "
                "em config.py."
            )

        if (
            cfg.SERIAL_ACK_TIMEOUT
            <=
            0
            or
            cfg.HEARTBEAT_SECONDS
            <=
            0
        ):

            raise ValueError(
                "Timeout Serial e heartbeat "
                "devem ser positivos."
            )


        # --------------------------------------------------
        # CICLO
        # --------------------------------------------------

        ciclo = CicloInspecao()


        # --------------------------------------------------
        # BANCO
        # --------------------------------------------------

        inicializar_banco()

        publicar(
            True
        )

        adquirido = True
        if preview_web is not None:
            preview_web.limpar()


        # --------------------------------------------------
        # MODELO
        # --------------------------------------------------

        etapa = "modelo"

        model = carregar_modelo()

        estado.update(

            modelo=True,

            modelo_versao=
            versao_modelo()
        )

        publicar(
            True
        )


        # --------------------------------------------------
        # OPENCV
        # --------------------------------------------------

        import cv2


        # --------------------------------------------------
        # CÂMERA
        # --------------------------------------------------

        etapa = "camera"

        cap = abrir_camera()

        estado[
            "camera"
        ] = True


        # --------------------------------------------------
        # SERIAL COM ARDUINO ESCRAVO
        # --------------------------------------------------

        porta = conectar_serial()

        if cfg.USE_SERIAL:

            if porta is not None:

                estado[
                    "serial"
                ] = "conectada"

            else:

                estado[
                    "serial"
                ] = "indisponivel"

        else:

            estado[
                "serial"
            ] = "desabilitada"


        estado[
            "estado"
        ] = "AGUARDANDO"

        publicar(
            True
        )


        bloqueio_auto = False

        ausentes = 0


        print(
            "Estação pronta."
        )

        print(
            "START do mestre "
            "ou tecla I = iniciar."
        )

        print(
            "Q = sair."
        )


        # ==================================================
        # LOOP PRINCIPAL
        # ==================================================

        while True:


            # ----------------------------------------------
            # LER COMANDO DO ARDUINO
            # ----------------------------------------------

            comando_arduino = (
                ler_comando_arduino(
                    porta
                )
            )


            # ----------------------------------------------
            # START RECEBIDO DO MESTRE
            # ----------------------------------------------

            if (
                comando_arduino
                ==
                "START"
            ):

                if ciclo.iniciar():

                    print(
                        "START recebido "
                        "do Arduino mestre."
                    )

                    estado.update(

                        estado=
                        ciclo.estado,

                        ciclo_id=
                        ciclo.ciclo_id,

                        motivo=""
                    )

                    publicar(
                        True
                    )

                else:

                    print(
                        "START ignorado: "
                        "ciclo em andamento "
                        "ou cooldown ativo."
                    )


            # ----------------------------------------------
            # CAMERA
            # ----------------------------------------------

            etapa = "camera"

            if preview_web is not None:
                inicio_captura = time.perf_counter()
            ret, frame = (
                cap.read()
            )
            if preview_web is not None:
                preview_web.metricas['latencia_captura_ms'] = round(1000 * (time.perf_counter() - inicio_captura), 2)

            if not ret:

                ultimo_frame = None

                raise RuntimeError(
                    "CAMERA_SEM_FRAME: "
                    "verifique a conexão "
                    "da webcam."
                )

            ultimo_frame = (
                frame.copy()
            )


            # ----------------------------------------------
            # YOLO
            # ----------------------------------------------

            etapa = "modelo"

            if preview_web is not None:
                inicio_inferencia = time.perf_counter()
            preview, deteccoes = (
                processar_frame(
                    model,
                    frame
                )
            )
            if preview_web is not None:
                preview_web.metricas['latencia_inferencia_ms'] = round(1000 * (time.perf_counter() - inicio_inferencia), 2)


            # ----------------------------------------------
            # DECISÃO
            # ----------------------------------------------

            etapa = "operacao"

            decisao = (
                determinar_resultado(
                    deteccoes
                )
            )

            motivo = (
                motivo_deteccao(
                    deteccoes
                )
            )


            if deteccoes:

                ausentes = 0

            else:

                ausentes += 1


            # ----------------------------------------------
            # MODO AUTOMÁTICO
            # ----------------------------------------------

            if (
                cfg.INSPECTION_MODE
                ==
                "automatico"
            ):

                if (
                    ausentes
                    >=
                    cfg.REARM_FRAMES
                ):

                    bloqueio_auto = False

                if (
                    deteccoes
                    and
                    not bloqueio_auto
                    and
                    ciclo.estado
                    !=
                    "INSPECIONANDO"
                ):

                    if ciclo.iniciar():

                        bloqueio_auto = True

                        estado.update(

                            estado=
                            ciclo.estado,

                            ciclo_id=
                            ciclo.ciclo_id,

                            motivo=""
                        )

                        publicar(
                            True
                        )


            # ----------------------------------------------
            # ATUALIZAR CICLO
            # ----------------------------------------------

            evento = (
                ciclo.atualizar(
                    decisao,
                    motivo
                )
            )


            # ----------------------------------------------
            # CICLO FINALIZADO
            # ----------------------------------------------

            if evento:

                etapa = "persistencia"

                concluir(
                    evento
                )


            # ----------------------------------------------
            # TEXTO NA TELA
            # ----------------------------------------------

            if (
                ciclo.estado
                ==
                "INSPECIONANDO"
            ):

                texto = (
                    f"INSPECIONANDO "
                    f"{ciclo.seguidos}/"
                    f"{cfg.STABLE_FRAMES}"
                )

                cor = (
                    0,
                    210,
                    255
                )


            elif ultima:

                texto = (
                    f"{ultima['resultado']} "
                    f"| I: novo ciclo"
                )

                cor = {

                    "OK":
                    (
                        80,
                        220,
                        80
                    ),

                    "NOK":
                    (
                        60,
                        60,
                        240
                    )

                }.get(
                    ultima["resultado"],
                    (
                        0,
                        210,
                        255
                    )
                )


            else:

                texto = (
                    "AGUARDANDO "
                    "| I: iniciar"
                )

                cor = (
                    200,
                    200,
                    200
                )


            # ----------------------------------------------
            # DESENHAR INTERFACE
            # ----------------------------------------------

            cv2.rectangle(

                preview,

                (
                    0,
                    0
                ),

                (
                    preview.shape[1],
                    75
                ),

                (
                    25,
                    25,
                    25
                ),

                -1
            )


            cv2.putText(

                preview,

                texto,

                (
                    10,
                    28
                ),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.6,

                cor,

                2
            )


            if decisao:

                classe = (

                    f"{decisao['classe_detectada']} "
                    f"{decisao['confianca']:.1%}"
                )

            else:

                classe = motivo


            cv2.putText(

                preview,

                classe
                +
                " | Q: sair",

                (
                    10,
                    58
                ),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.55,

                (
                    230,
                    230,
                    230
                ),

                1
            )


            cv2.imshow(

                "Estacao 3 - Inspecao",

                preview
            )

            if preview_web is not None:
                preview_web.publicar(cv2, preview)

            publicar()


            # ----------------------------------------------
            # TECLADO
            # ----------------------------------------------

            key = (
                cv2.waitKey(1)
                &
                0xFF
            )


            # ----------------------------------------------
            # TECLA I - TESTE MANUAL
            # ----------------------------------------------

            iniciou_ciclo = False
            if key in (ord("i"), ord("I")):
                if cfg.INSPECTION_MODE == "manual":
                    iniciou_ciclo = ciclo.iniciar()
                    if not iniciou_ciclo:
                        print("Ciclo em andamento ou cooldown ativo; comando ignorado.")
            elif key not in (ord("q"), ord("Q")) and ler_comando_web is not None:
                iniciou_ciclo = ler_comando_web(ciclo.iniciar)

            if iniciou_ciclo:
                estado.update(estado=ciclo.estado, ciclo_id=ciclo.ciclo_id, motivo="")
                publicar(True)


            # ----------------------------------------------
            # TECLA Q - SAIR
            # ----------------------------------------------

            if key in (
                ord("q"),
                ord("Q")
            ):

                if (
                    ciclo.estado
                    ==
                    "INSPECIONANDO"
                ):

                    concluir(

                        ciclo.falhar(
                            "CANCELADO_OPERADOR"
                        )

                    )

                break


        return 0


    # ======================================================
    # CTRL+C
    # ======================================================

    except KeyboardInterrupt:

        if (
            adquirido
            and
            ciclo
            and
            ciclo.estado
            ==
            "INSPECIONANDO"
        ):

            concluir(

                ciclo.falhar(
                    "CANCELADO_OPERADOR"
                )

            )

        return 0


    # ======================================================
    # ERROS
    # ======================================================

    except Exception as exc:

        print(
            f"ERRO: {exc}"
        )

        if adquirido:

            if etapa in (
                "camera",
                "modelo"
            ):

                estado[
                    etapa
                ] = False


            estado.update(

                estado="FALHA",

                motivo=str(
                    exc
                )
            )


            try:

                if (
                    ciclo
                    and
                    ciclo.estado
                    ==
                    "INSPECIONANDO"
                ):

                    concluir(

                        ciclo.falhar(
                            str(exc)
                        )

                    )

                publicar(
                    True
                )

            except Exception as erro_registro:

                print(
                    f"ERRO ao registrar falha: "
                    f"{erro_registro}"
                )

        return 1


    # ======================================================
    # ENCERRAMENTO
    # ======================================================

    finally:

        if adquirido and preview_web is not None:
            preview_web.limpar()

        if cap is not None:

            cap.release()


        if porta is not None:

            porta.close()


        if cv2 is not None:

            cv2.destroyAllWindows()


        if adquirido:

            estado[
                "ativo"
            ] = False

            try:

                publicar(
                    True
                )

            except Exception as exc:

                print(
                    f"AVISO: não foi possível "
                    f"publicar encerramento: "
                    f"{exc}"
                )


# ==========================================================
# EXECUTAR
# ==========================================================

if __name__ == '__main__':
    raise SystemExit(main(preview_web=True))
