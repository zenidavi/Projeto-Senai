"""Prévia web: o processo de inferência é o único dono da webcam."""
from pathlib import Path
import hmac
import json
import os
import secrets
import threading
import time
import uuid

FPS_PREVIA = 12  # Apenas teto da transmissão; NÃO é FPS de inferência.
_ULTIMO_COMANDO = 0.0


def pasta():
    from config import IMAGE_DIR
    return Path(IMAGE_DIR) / "_camera_ao_vivo"


def recente(arquivo, segundos=3.0):
    try:
        return 0 <= time.time() - arquivo.stat().st_mtime <= segundos
    except OSError:
        return False


def ultimo_frame():
    try:
        return max(pasta().glob("frame_*.jpg"), key=lambda f: f.name)
    except (ValueError, OSError):
        return None


def situacao(db_path=None):
    import config
    from supervisorio.database import buscar_status
    if config.USE_SERIAL or config.INSPECTION_MODE != "manual":
        return {"pronto": False, "motivo": "Botão disponível somente no modo manual sem Serial."}
    opcoes = {"db_path": db_path} if db_path is not None else {}
    estado = buscar_status(**opcoes)["estacao"]
    if not (estado.get("online") and estado.get("origem") == "real"
            and estado.get("camera") is True and estado.get("modelo") is True):
        return {"pronto": False, "motivo": "IA/câmera desconectada."}
    if estado.get("estado") not in ("AGUARDANDO", "CONCLUIDO"):
        return {"pronto": False, "motivo": "A estação não está pronta."}
    if not recente(pasta() / "ia_pronta.txt") or not recente(ultimo_frame() or pasta() / "sem_frame"):
        return {"pronto": False, "motivo": "Aguardando prévia ativa."}
    return {"pronto": True, "motivo": "Pronto para inspeção manual."}


def escrever_json(destino, dados):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name("." + uuid.uuid4().hex + ".tmp")
    try:
        temporario.write_text(json.dumps(dados), encoding="utf-8")
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def registrar_rotas(app, db_path=None):
    from flask import Response, abort, jsonify, request
    from supervisorio.database import buscar_status
    token = secrets.token_hex(32)
    trava = threading.Lock()
    ultimo = [0.0]

    @app.context_processor
    def contexto_camera():
        return {"camera_token": token}

    @app.get("/api/video/frame")
    def video_frame():
        opcoes = {"db_path": db_path} if db_path is not None else {}
        estado = buscar_status(**opcoes)["estacao"]
        if not (estado.get("online") and estado.get("origem") == "real"
                and estado.get("camera") is True):
            abort(503)
        arquivo = ultimo_frame()
        if arquivo is None or not recente(arquivo):
            abort(503)
        try:
            return Response(arquivo.read_bytes(), mimetype="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        except OSError:
            abort(503)

    @app.get("/api/video/controle/estado")
    def video_controle_estado():
        return jsonify(situacao(db_path))

    @app.post("/api/video/controle/inspecionar")
    def video_controle_inspecionar():
        if not hmac.compare_digest(request.headers.get("X-Estacao3-Token", ""), token):
            return jsonify(erro="Token de controle inválido."), 403
        with trava:
            s = situacao(db_path)
            if not s["pronto"]:
                return jsonify(erro=s["motivo"]), 409
            agora = time.monotonic()
            if agora - ultimo[0] < 2.2:
                return jsonify(erro="Aguarde o intervalo de inspeções."), 429
            comando = pasta() / "comando_inspecao.json"
            if recente(comando):
                return jsonify(erro="Já existe uma solicitação pendente."), 409
            identificador = uuid.uuid4().hex
            try:
                escrever_json(comando, {"id": identificador, "acao": "inspecionar",
                                        "emitido_em": time.time()})
            except OSError:
                return jsonify(erro="Não foi possível registrar o comando."), 503
            ultimo[0] = agora
        return jsonify(solicitacao_id=identificador, mensagem="Comando enviado à IA."), 202


def _consumir_comando():
    import config
    if config.USE_SERIAL or config.INSPECTION_MODE != "manual":
        return False
    comando = pasta() / "comando_inspecao.json"
    temporario = pasta() / ("comando_lido_" + uuid.uuid4().hex + ".tmp")
    try:
        os.replace(comando, temporario)
    except OSError:
        return False
    try:
        dado = json.loads(temporario.read_text(encoding="utf-8"))
        idade = time.time() - float(dado.get("emitido_em", 0))
        return dado.get("acao") == "inspecionar" and 0 <= idade <= 3.0
    except (OSError, ValueError, TypeError):
        return False
    finally:
        temporario.unlink(missing_ok=True)


def iniciar_ia(main_original):
    """Intercepta somente a exibição da IA, não a captura/modelo/Serial."""
    import cv2
    raiz = pasta()
    raiz.mkdir(parents=True, exist_ok=True)
    original_imshow, original_waitkey = cv2.imshow, cv2.waitKey
    ultimo_envio = [float("-inf")]
    ultimo_heartbeat = [float("-inf")]
    erros = [False]
    contador = [0]

    def publicar_imagem(*args, **kwargs):
        frame = args[1] if len(args) > 1 else kwargs.get("mat")
        agora = time.monotonic()
        if frame is not None:
            if agora - ultimo_heartbeat[0] > 1:
                try:
                    (raiz / "ia_pronta.txt").write_text(str(os.getpid()), encoding="utf-8")
                    ultimo_heartbeat[0] = agora
                except OSError:
                    pass
            if agora - ultimo_envio[0] >= 1.0 / FPS_PREVIA:
                try:
                    h, w = frame.shape[:2]
                    preview = cv2.resize(frame, (960, max(1, round(h * 960 / w)))) if w > 960 else frame
                    sucesso, codificado = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 62])
                    if sucesso:
                        # Frame imutável: evita WinError 5 de substituição enquanto Flask lê.
                        nome = raiz / f"frame_{time.time_ns():020d}_{uuid.uuid4().hex[:6]}.jpg"
                        nome.write_bytes(codificado.tobytes())
                        ultimo_envio[0] = agora
                        contador[0] += 1
                        if contador[0] % 12 == 0:
                            for antigo in sorted(raiz.glob("frame_*.jpg"))[:-12]:
                                try:
                                    antigo.unlink()
                                except OSError:
                                    pass
                except (OSError, ValueError, cv2.error) as exc:
                    if not erros[0]:
                        print(f"AVISO: prévia web indisponível: {exc}")
                        erros[0] = True
        return original_imshow(*args, **kwargs)

    def entrada(*args, **kwargs):
        tecla = original_waitkey(*args, **kwargs)
        if tecla & 255 in (ord("i"), ord("I"), ord("q"), ord("Q")):
            return tecla
        return ord("i") if _consumir_comando() else tecla

    for velho in raiz.glob("frame_*.jpg"):
        try:
            velho.unlink()
        except OSError:
            pass
    for nome in ("comando_inspecao.json", "ia_pronta.txt"):
        (raiz / nome).unlink(missing_ok=True)
    cv2.imshow, cv2.waitKey = publicar_imagem, entrada
    print("Prévia web: até 12 FPS (otimização pendente).")
    try:
        return main_original()
    finally:
        cv2.imshow, cv2.waitKey = original_imshow, original_waitkey
        for nome in ("comando_inspecao.json", "ia_pronta.txt"):
            (raiz / nome).unlink(missing_ok=True)
