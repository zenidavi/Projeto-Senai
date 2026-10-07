"""SQLite compartilhado: migração transacional, WAL e conexões curtas."""
from contextlib import contextmanager
from datetime import datetime
import json
import math
from pathlib import Path
import sqlite3
from uuid import uuid4
from config import DATABASE_PATH, STATION_STALE_SECONDS


@contextmanager
def conexao(db_path=DATABASE_PATH):
    caminho = Path(db_path)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(caminho), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 10000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """CREATE TABLE IF NOT EXISTS inspecoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    resultado TEXT NOT NULL CHECK(resultado IN ('OK','NOK','INCONCLUSIVO')),
    classe_detectada TEXT,
    confianca REAL CHECK(confianca BETWEEN 0 AND 1),
    origem TEXT NOT NULL CHECK(origem IN ('real','simulador')),
    ciclo_id TEXT NOT NULL UNIQUE,
    inicio_timestamp TEXT,
    duracao_ms INTEGER CHECK(duracao_ms >= 0),
    motivo TEXT NOT NULL DEFAULT '',
    modelo_versao TEXT NOT NULL DEFAULT 'não informado',
    imagem_path TEXT,
    serial_status TEXT NOT NULL DEFAULT 'nao_enviado'
)"""


def inicializar_banco(db_path=DATABASE_PATH):
    with conexao(db_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("BEGIN IMMEDIATE")
        colunas = {r['name'] for r in conn.execute("PRAGMA table_info(inspecoes)")}
        if colunas and 'ciclo_id' not in colunas:
            # O CHECK antigo permitia apenas OK/NOK. Copiar preserva IDs e dados.
            conn.execute("ALTER TABLE inspecoes RENAME TO inspecoes_v1")
            conn.execute(SCHEMA)
            conn.execute("""INSERT INTO inspecoes
                (id,timestamp,resultado,classe_detectada,confianca,origem,ciclo_id,motivo)
                SELECT id,timestamp,resultado,classe_detectada,confianca,origem,
                       'legado-' || id,'REGISTRO_ANTERIOR' FROM inspecoes_v1""")
            antigo = conn.execute("SELECT COUNT(*) FROM inspecoes_v1").fetchone()[0]
            novo = conn.execute("SELECT COUNT(*) FROM inspecoes").fetchone()[0]
            if antigo != novo:
                raise RuntimeError("Migração interrompida: contagens diferentes.")
            conn.execute("DROP TABLE inspecoes_v1")
        else:
            conn.execute(SCHEMA)
        conn.execute("""CREATE TABLE IF NOT EXISTS estado_estacao (
            id INTEGER PRIMARY KEY CHECK(id=1), sessao_id TEXT NOT NULL,
            atualizado_em TEXT NOT NULL, dados TEXT NOT NULL)""")
        conn.execute("PRAGMA user_version = 2")


def registrar_inspecao(resultado, classe_detectada=None, confianca=None,
                       origem="real", db_path=DATABASE_PATH, ciclo_id=None,
                       inicio_timestamp=None, duracao_ms=None, motivo="",
                       modelo_versao="não informado", imagem_path=None,
                       serial_status="nao_enviado"):
    if resultado not in ("OK", "NOK", "INCONCLUSIVO") or origem not in ("real", "simulador"):
        raise ValueError("Resultado ou origem inválidos.")
    if confianca is not None:
        confianca = float(confianca)
        if not math.isfinite(confianca) or not 0 <= confianca <= 1:
            raise ValueError("Confiança fora de 0 a 1.")
    if resultado in ("OK", "NOK") and (not classe_detectada or confianca is None):
        raise ValueError("Resultado OK/NOK exige classe e confiança.")
    if duracao_ms is not None and (not isinstance(duracao_ms, int) or duracao_ms < 0):
        raise ValueError("Duração deve ser inteiro >= 0.")
    inicializar_banco(db_path)
    timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
    with conexao(db_path) as conn:
        cursor = conn.execute("""INSERT INTO inspecoes
            (timestamp,resultado,classe_detectada,confianca,origem,ciclo_id,
             inicio_timestamp,duracao_ms,motivo,modelo_versao,imagem_path,serial_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (timestamp, resultado, classe_detectada, confianca, origem,
             ciclo_id or uuid4().hex, inicio_timestamp, duracao_ms, motivo,
             modelo_versao, imagem_path, serial_status))
        return cursor.lastrowid


def atualizar_serial(identificador, status, db_path=DATABASE_PATH):
    with conexao(db_path) as conn:
        conn.execute("UPDATE inspecoes SET serial_status=? WHERE id=?", (status, identificador))


def buscar_inspecao(identificador, db_path=DATABASE_PATH):
    inicializar_banco(db_path)
    with conexao(db_path) as conn:
        row = conn.execute("SELECT * FROM inspecoes WHERE id=?", (identificador,)).fetchone()
        return dict(row) if row else None


def publicar_estado(sessao_id, dados, db_path=DATABASE_PATH):
    """Uma sessão dona do banco; impede inferência e simulador concorrentes."""
    inicializar_banco(db_path)
    agora = datetime.now().astimezone()
    with conexao(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        anterior = conn.execute("SELECT * FROM estado_estacao WHERE id=1").fetchone()
        if anterior and anterior['sessao_id'] != sessao_id:
            idade = (agora - datetime.fromisoformat(anterior['atualizado_em'])).total_seconds()
            if idade < STATION_STALE_SECONDS and json.loads(anterior['dados']).get('ativo'):
                raise RuntimeError("Outro processo usa este banco. Pare-o ou use ESTACAO3_DB separado.")
        conn.execute("""INSERT INTO estado_estacao (id,sessao_id,atualizado_em,dados)
            VALUES (1,?,?,?) ON CONFLICT(id) DO UPDATE SET
            sessao_id=excluded.sessao_id, atualizado_em=excluded.atualizado_em,
            dados=excluded.dados""", (sessao_id, agora.isoformat(), json.dumps(dados)))


def _estacao(conn):
    row = conn.execute("SELECT * FROM estado_estacao WHERE id=1").fetchone()
    if not row:
        return {'online': False, 'estado': 'SEM_CONEXAO', 'motivo': 'Processo de inspeção não iniciado.'}
    dados = json.loads(row['dados'])
    idade = max(0, (datetime.now().astimezone() - datetime.fromisoformat(row['atualizado_em'])).total_seconds())
    dados.update(atualizado_em=row['atualizado_em'], idade_segundos=round(idade, 1),
                 online=bool(dados.get('ativo')) and idade <= STATION_STALE_SECONDS)
    dados['ultimo_estado'] = dados['estado']
    dados['ultimo_motivo'] = dados.get('motivo', '')
    if not dados['online']:
        dados['estado'] = 'SEM_CONEXAO'
        dados['motivo'] = 'Processo parado ou sem atualização recente.'
        if dados['ultimo_motivo']:
            dados['motivo'] += ' Último aviso: ' + dados['ultimo_motivo']
    return dados


def _recentes(conn, limite):
    return [dict(row) for row in conn.execute(
        "SELECT * FROM inspecoes ORDER BY id DESC LIMIT ?", (limite,))]


def _contagens(conn):
    dados = dict(conn.execute("""SELECT COUNT(*) AS total,
        COALESCE(SUM(resultado='OK'),0) AS ok,
        COALESCE(SUM(resultado='NOK'),0) AS nok,
        COALESCE(SUM(resultado='INCONCLUSIVO'),0) AS inconclusivo FROM inspecoes""").fetchone())
    for resultado in ('ok', 'nok', 'inconclusivo'):
        dados[f'percentual_{resultado}'] = round(100 * dados[resultado] / dados['total'], 1) if dados['total'] else 0
    return dados


def buscar_inspecoes_recentes(limite=20, db_path=DATABASE_PATH):
    inicializar_banco(db_path)
    with conexao(db_path) as conn:
        return _recentes(conn, max(1, min(int(limite), 100)))


def buscar_contagem(db_path=DATABASE_PATH):
    inicializar_banco(db_path)
    with conexao(db_path) as conn:
        return _contagens(conn)


def buscar_status(db_path=DATABASE_PATH):
    inicializar_banco(db_path)
    with conexao(db_path) as conn:
        conn.execute('BEGIN')
        contagens = _contagens(conn)
        recentes = _recentes(conn, 20)
        return {'ultima': recentes[0] if recentes else None,
                'estacao': _estacao(conn), 'contagens': contagens, 'historico': recentes,
                'grafico': {'labels': ['OK', 'NOK', 'Inconclusivo'],
                            'valores': [contagens['ok'], contagens['nok'], contagens['inconclusivo']]}}


def buscar_dados_grafico(db_path=DATABASE_PATH):
    return buscar_status(db_path)['grafico']
