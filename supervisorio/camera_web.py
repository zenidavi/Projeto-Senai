"""Integração LOCAL Estação 3: prévia YOLO + botão do supervisorio.

O processo de inferência CONTINUA sendo o único dono da webcam e da decisão.
A imagem JPEG e o comando de demonstração atravessam arquivos locais atômicos.
Este módulo não altera o protocolo serial ou a lógica do ciclo.

PENDENTE: medir FPS/latências por etapa e otimizar a transmissão (teto atual 12 FPS).
"""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from uuid import uuid4

# Atenção: nunca encaminhar pedidos de demonstração para o controlador real.
FPS_ALVO = 12.0
LARGURA_MAXIMA_PREVIEW = 960
QUALIDADE_JPEG = 62
TEMPO_MAXIMO_FRAME = 3.0
IDADE_MAXIMA_COMANDO = 3.0
INTERVALO_COMANDO = 2.2
INTERVALO_FALHA_JPEG = 0.2


def pasta_preview(image_dir=None):
    import config as cfg
    return Path(cfg.IMAGE_DIR if image_dir is None else image_dir) / '_camera_ao_vivo'


def caminho_preview(image_dir=None):
    return pasta_preview(image_dir) / 'ultimo_frame.jpg'


def caminho_comando(image_dir=None):
    return pasta_preview(image_dir) / 'comando_inspecao.json'


def caminho_pronto(image_dir=None):
    return pasta_preview(image_dir) / 'ia_pronta.txt'


def caminho_ack(image_dir=None):
    return pasta_preview(image_dir) / 'ultimo_comando_recebido.json'


def idade_arquivo(path: Path):
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None


def arquivo_recente(path: Path, idade_max=3.0) -> bool:
    idade = idade_arquivo(path)
    return idade is not None and -2 <= idade <= idade_max


def diagnosticar_preview(image_dir):
    idade = idade_arquivo(caminho_preview(image_dir))
    if idade is None:
        return {'estado': 'indisponivel', 'idade_segundos': None}
    if idade < -2:
        return {'estado': 'horario_invalido', 'idade_segundos': None}
    return {
        'estado': 'recente' if idade <= TEMPO_MAXIMO_FRAME else 'expirado',
        'idade_segundos': round(max(0, idade), 1),
    }


def gravar_json_atomico(destino: Path, objeto: dict):
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(f'.{destino.name}.{uuid4().hex}.tmp')
    try:
        temporario.write_text(json.dumps(objeto, ensure_ascii=False), encoding='utf-8')
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def configuracao_segura_controle():
    """Painel de teste não controla hardware real nem contorna controlador central."""
    import config as cfg
    if cfg.USE_SERIAL:
        return False, 'Controle web bloqueado: USE_SERIAL=True (hardware).'
    if cfg.INSPECTION_MODE != 'manual':
        return False, 'Controle web disponível apenas no modo manual.'
    return True, ''


def situacao_controle(ler_estacao, image_dir=None):
    permitido, aviso = configuracao_segura_controle()
    if not permitido:
        return {'pronto': False, 'motivo': aviso, 'estado': 'BLOQUEADO'}
    try:
        estacao = ler_estacao()
    except Exception:
        return {'pronto': False, 'motivo': 'Estado da estação indisponível.', 'estado': 'DESCONHECIDO'}
    estado = estacao.get('estado', 'DESCONHECIDO')
    if not estacao.get('online') or estacao.get('origem') != 'real':
        return {'pronto': False, 'motivo': 'IA desconectada.', 'estado': estado}
    if estacao.get('camera') is not True or estacao.get('modelo') is not True:
        return {'pronto': False, 'motivo': 'Câmera ou modelo indisponível.', 'estado': estado}
    if not arquivo_recente(caminho_pronto(image_dir), TEMPO_MAXIMO_FRAME):
        return {'pronto': False, 'motivo': 'Execute python inferencia.py para habilitar o botão.', 'estado': estado}
    if estado == 'INSPECIONANDO':
        return {'pronto': False, 'motivo': 'Inspeção em andamento.', 'estado': estado}
    if estado not in ('AGUARDANDO', 'CONCLUIDO'):
        return {'pronto': False, 'motivo': f'Estação em estado {estado}.', 'estado': estado}
    if not arquivo_recente(caminho_preview(image_dir), TEMPO_MAXIMO_FRAME):
        return {'pronto': False, 'motivo': 'Aguardando imagem atualizada.', 'estado': estado}
    return {'pronto': True, 'motivo': 'Pronto para inspeção manual.', 'estado': estado}


def registrar_rotas(app, *, db_path=None, image_dir=None, permitir_comandos=True):
    """Adiciona endpoints e contexto Jinja ao Flask original, sem segunda webcam."""
    from flask import abort, jsonify, request, Response
    from config import DATABASE_PATH
    from supervisorio.database import conexao_leitura, ler_estado_estacao

    banco = DATABASE_PATH if db_path is None else db_path

    def ler_estacao():
        with conexao_leitura(banco) as conn:
            return ler_estado_estacao(conn)

    token = secrets.token_hex(32)
    trava = threading.Lock()
    ultimo_pedido = float('-inf')

    @app.context_processor
    def dados_camera_web():
        return {'camera_token': token}

    @app.get('/api/video/frame')
    def rota_camera():
        try:
            estacao = ler_estacao()
            if not (estacao.get('online') and estacao.get('origem') == 'real'
                    and estacao.get('camera') is True):
                abort(503)
            caminho = caminho_preview(image_dir)
            with caminho.open('rb') as arquivo:
                idade = time.time() - os.fstat(arquivo.fileno()).st_mtime
                if not -2 <= idade <= TEMPO_MAXIMO_FRAME:
                    abort(503)
                jpg = arquivo.read()
            return Response(jpg, mimetype='image/jpeg',
                            headers={'Cache-Control': 'no-store'})
        except OSError:
            abort(503)

    @app.get('/api/video/controle/estado')
    def rota_estado_controle():
        if not permitir_comandos:
            return jsonify(pronto=False, motivo='Supervisório em modo somente leitura.', estado='BLOQUEADO')
        return jsonify(situacao_controle(ler_estacao, image_dir))

    @app.post('/api/video/controle/inspecionar')
    def rota_iniciar_inspecao():
        nonlocal ultimo_pedido
        if not permitir_comandos:
            return jsonify(mensagem='Supervisório em modo somente leitura.'), 403
        # Este token é proteção CSRF para serviço somente localhost, NÃO autenticação.
        if not hmac.compare_digest(request.headers.get('X-Estacao3-Token', ''), token):
            return jsonify(mensagem='Solicitação não autorizada.'), 403
        with trava:
            estado = situacao_controle(ler_estacao, image_dir)
            if not estado['pronto']:
                return jsonify(mensagem=estado['motivo']), 409
            agora = time.monotonic()
            if agora - ultimo_pedido < INTERVALO_COMANDO:
                return jsonify(mensagem='Aguarde o intervalo entre inspeções.'), 429
            cmd = caminho_comando(image_dir)
            if arquivo_recente(cmd, IDADE_MAXIMA_COMANDO):
                return jsonify(mensagem='Existe uma solicitação ainda pendente.'), 409
            identificador = uuid4().hex
            try:
                gravar_json_atomico(cmd, {'id': identificador, 'acao': 'inspecionar',
                                          'emitido_em': time.time()})
            except OSError:
                return jsonify(mensagem='Falha ao registrar comando local.'), 503
            ultimo_pedido = agora
            return jsonify(mensagem='Solicitação registrada.', solicitacao_id=identificador), 202

    @app.get('/api/video/controle/comando/<identificador>')
    def rota_confirmacao_comando(identificador):
        if not re.fullmatch(r'[a-f0-9]{32}', identificador):
            abort(404)
        try:
            dados = json.loads(caminho_ack(image_dir).read_text(encoding='utf-8'))
        except (OSError, ValueError, TypeError):
            dados = {}
        if not isinstance(dados, dict) or dados.get('id') != identificador:
            return jsonify(entregue=False)
        return jsonify(entregue=True, aceito=dados.get('aceito'))


def consumir_comando(iniciar_ciclo):
    """Consome um pedido local e registra se o ciclo aceitou o início."""
    if not configuracao_segura_controle()[0]:
        return False
    entrada = caminho_comando()
    reclamado = entrada.with_name(f'.comando_lido_{os.getpid()}_{uuid4().hex}.tmp')
    try:
        os.replace(entrada, reclamado)
    except OSError:
        return False
    try:
        pedido = json.loads(reclamado.read_text(encoding='utf-8'))
        ident = pedido.get('id', '')
        instante = float(pedido.get('emitido_em', 0))
        idade = time.time() - instante
        if (not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{32}', ident)
                or pedido.get('acao') != 'inspecionar'
                or not (0 <= idade <= IDADE_MAXIMA_COMANDO)):
            return False
        aceito = iniciar_ciclo()
        try:
            gravar_json_atomico(caminho_ack(), {'id': ident, 'entregue_em': time.time(),
                                               'aceito': aceito})
        except OSError as exc:
            print(f'AVISO: não foi possível confirmar o comando web: {exc}')
        return aceito
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
    finally:
        try:
            reclamado.unlink(missing_ok=True)
        except OSError:
            pass


class PreviewWeb:
    """Publica quadros produzidos pelo processo que detém a webcam."""

    def __init__(self):
        self.destino = caminho_preview()
        self.pronto = caminho_pronto()
        self.sessao = uuid4().hex
        self.proxima_tentativa = float('-inf')
        self.ultimo_heartbeat = float('-inf')
        self.avisou = False
        self.metricas = {
            'falhas_publicacao_jpeg': 0,
            'ultimo_erro_publicacao_jpeg': None,
        }

    def limpar(self):
        for arquivo in (self.pronto, self.destino, caminho_comando(), caminho_ack()):
            try:
                arquivo.unlink(missing_ok=True)
            except OSError:
                pass

    def publicar(self, cv2, frame):
        agora = time.monotonic()
        if agora < self.proxima_tentativa:
            return
        self.proxima_tentativa = agora + 1.0 / FPS_ALVO
        temporario = self.destino.with_name(f'.preview_{os.getpid()}.tmp')
        try:
            self.destino.parent.mkdir(parents=True, exist_ok=True)
            inicio = time.perf_counter()
            altura, largura = frame.shape[:2]
            if largura > LARGURA_MAXIMA_PREVIEW:
                nova_altura = max(1, round(altura * LARGURA_MAXIMA_PREVIEW / largura))
                frame = cv2.resize(frame, (LARGURA_MAXIMA_PREVIEW, nova_altura),
                                   interpolation=cv2.INTER_AREA)
            ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, QUALIDADE_JPEG])
            if not ok:
                raise ValueError('Codificação JPEG retornou falha.')
            self.metricas['latencia_codificacao_jpeg_ms'] = round(1000 * (time.perf_counter() - inicio), 2)

            inicio = time.perf_counter()
            temporario.write_bytes(jpg.tobytes())
            os.replace(temporario, self.destino)
            self.metricas['latencia_publicacao_jpeg_ms'] = round(1000 * (time.perf_counter() - inicio), 2)
            self.avisou = False
            if agora - self.ultimo_heartbeat >= 1.0:
                try:
                    self.pronto.write_text(self.sessao, encoding='ascii')
                    self.ultimo_heartbeat = agora
                except OSError:
                    pass
        except (OSError, ValueError, cv2.error) as exc:
            self.proxima_tentativa = time.monotonic() + INTERVALO_FALHA_JPEG
            self.metricas['falhas_publicacao_jpeg'] += 1
            winerror = getattr(exc, 'winerror', None)
            self.metricas['ultimo_erro_publicacao_jpeg'] = (
                f'WinError {winerror}' if winerror is not None else type(exc).__name__
            )
            if not self.avisou:
                print(f'AVISO: prévia web indisponível: {exc}')
                self.avisou = True
        finally:
            try:
                temporario.unlink(missing_ok=True)
            except OSError:
                pass
