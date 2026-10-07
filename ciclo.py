"""Ciclo de uma peça, independente de webcam, Flask e protocolo da mesa."""
from datetime import datetime
import time
from uuid import uuid4
import config as cfg


class CicloInspecao:
    def __init__(self, frames=cfg.STABLE_FRAMES,
                 timeout=cfg.INSPECTION_TIMEOUT_SECONDS,
                 cooldown=cfg.COOLDOWN_SECONDS):
        if frames < 1 or timeout <= 0 or cooldown < 0:
            raise ValueError("Frames >= 1, timeout > 0 e cooldown >= 0.")
        self.frames, self.timeout, self.cooldown = frames, timeout, cooldown
        self.estado = "AGUARDANDO"
        self.ciclo_id = None
        self.seguidos = 0
        self.chave = None
        self.ultimo_fim = float("-inf")
        self.inicio = None
        self.inicio_timestamp = None

    def iniciar(self, agora=None):
        agora = time.monotonic() if agora is None else agora
        if self.estado == "INSPECIONANDO":
            return False
        if agora - self.ultimo_fim < self.cooldown:
            return False
        self.ciclo_id = uuid4().hex
        self.inicio = agora
        self.inicio_timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        self.estado = "INSPECIONANDO"
        self.seguidos, self.chave = 0, None
        return True

    def _terminar(self, resultado, motivo, agora, decisao=None, falha=False):
        self.estado = "FALHA" if falha else "CONCLUIDO"
        self.ultimo_fim = agora
        return {"ciclo_id": self.ciclo_id, "inicio_timestamp": self.inicio_timestamp,
                "duracao_ms": round(max(0, agora - self.inicio) * 1000),
                "resultado": resultado, "motivo": motivo,
                "classe_detectada": decisao["classe_detectada"] if decisao else None,
                "confianca": decisao["confianca"] if decisao else None}

    def atualizar(self, decisao, motivo="SEM_DETECCAO", agora=None):
        if self.estado != "INSPECIONANDO":
            return None
        agora = time.monotonic() if agora is None else agora
        # O prazo prevalece mesmo que a detecção fique estável no frame tardio.
        if agora - self.inicio >= self.timeout:
            return self._terminar("INCONCLUSIVO", "TEMPO_LIMITE: " + motivo, agora)
        if decisao is None:
            self.seguidos, self.chave = 0, None
            return None
        chave = (decisao["resultado"], decisao["classe_detectada"])
        self.seguidos = self.seguidos + 1 if chave == self.chave else 1
        self.chave = chave
        if self.seguidos >= self.frames:
            return self._terminar(decisao["resultado"], "DETECCAO_ESTAVEL", agora, decisao)
        return None

    def falhar(self, motivo, agora=None):
        if self.estado != "INSPECIONANDO":
            self.estado = "FALHA"
            return None
        agora = time.monotonic() if agora is None else agora
        return self._terminar("INCONCLUSIVO", motivo, agora, falha=True)
