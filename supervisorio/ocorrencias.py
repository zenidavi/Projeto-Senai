"""Acompanhamento de ciclos que exigem revisão pela equipe de qualidade."""
from datetime import datetime
from secrets import compare_digest, token_hex

from flask import Blueprint, abort, redirect, render_template, request, url_for

from supervisorio.database import conexao, conexao_leitura

STATUS = {'pendente': 'Pendente', 'em_analise': 'Em análise', 'resolvida': 'Resolvida'}


def registrar_ocorrencias(app, banco, somente_leitura):
    bp = Blueprint('ocorrencias', __name__, url_prefix='/ocorrencias')
    token = token_hex(32)

    def consultar(conn, identificador=None, status=''):
        tem_tratamento = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tratamentos_ocorrencias'"
        ).fetchone()
        campos = ("COALESCE(t.status, 'pendente') AS status, t.responsavel, t.acao, t.atualizado_em"
                  if tem_tratamento else
                  "'pendente' AS status, NULL AS responsavel, NULL AS acao, NULL AS atualizado_em")
        juncao = ('LEFT JOIN tratamentos_ocorrencias t ON t.ciclo_id=i.ciclo_id'
                  if tem_tratamento else '')
        sql = f"""SELECT i.*, {campos} FROM inspecoes i {juncao}
                  WHERE i.resultado IN ('NOK', 'INCONCLUSIVO')"""
        if identificador is not None:
            return conn.execute(sql + ' AND i.id=?', (identificador,)).fetchone()
        filtro = 'WHERE status=?' if status else ''
        return conn.execute(f'SELECT * FROM ({sql}) {filtro} ORDER BY id DESC',
                            (status,) if status else ()).fetchall()

    @bp.get('')
    def lista():
        status = request.args.get('status', '')
        if status and status not in STATUS:
            abort(400)
        with conexao_leitura(banco) as conn:
            itens = consultar(conn, status=status)
        return render_template('ocorrencias.html', itens=itens, filtro=status, status_opcoes=STATUS)

    @bp.route('/<int:identificador>', methods=['GET', 'POST'])
    def detalhe(identificador):
        if request.method == 'POST':
            if somente_leitura or not compare_digest(request.form.get('token', '').encode(), token.encode()):
                abort(403)
        with conexao_leitura(banco) as conn:
            item = consultar(conn, identificador)
        if item is None:
            abort(404)
        erro = None
        valores = dict(item)
        if request.method == 'POST':
            valores.update({chave: request.form.get(chave, '').strip()
                            for chave in ('status', 'responsavel', 'acao')})
            status, responsavel, acao = (valores[chave] for chave in ('status', 'responsavel', 'acao'))
            if status not in STATUS or len(responsavel) > 120 or len(acao) > 2000:
                erro = 'Confira o status e os limites dos campos.'
            elif status != 'pendente' and not responsavel:
                erro = 'Informe o responsável pelo tratamento.'
            elif status == 'resolvida' and not acao:
                erro = 'Registre a ação tomada antes de resolver.'
            else:
                with conexao(banco) as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    atual = consultar(conn, identificador)
                    if atual is None:
                        abort(404)
                    if (atual['atualizado_em'] or '') != request.form.get('versao', ''):
                        return render_template('ocorrencias.html', item=dict(atual), token=token,
                                               status_opcoes=STATUS,
                                               erro='Outra pessoa atualizou a ocorrência. Confira os dados antes de salvar.'), 409
                    conn.execute("""CREATE TABLE IF NOT EXISTS tratamentos_ocorrencias (
                        ciclo_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL CHECK(status IN ('pendente','em_analise','resolvida')),
                        responsavel TEXT NOT NULL, acao TEXT NOT NULL, atualizado_em TEXT NOT NULL
                    )""")
                    conn.execute("""INSERT INTO tratamentos_ocorrencias VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(ciclo_id) DO UPDATE SET status=excluded.status,
                        responsavel=excluded.responsavel, acao=excluded.acao,
                        atualizado_em=excluded.atualizado_em""",
                        (atual['ciclo_id'], status, responsavel, acao, datetime.now().astimezone().isoformat()))
                return redirect(url_for('.detalhe', identificador=identificador, salvo=1), code=303)
        return render_template('ocorrencias.html', item=valores, token=token, status_opcoes=STATUS,
                               erro=erro, salvo=request.args.get('salvo') == '1'), 400 if erro else 200

    app.register_blueprint(bp)
