"""Consultas analiticas, somente leitura, sobre o SQLite existente da Estacao 3.

Nenhum dado artificial e criado. Nao altera schema, contadores nem o estado da IA.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import io
from math import ceil
from supervisorio.database import conexao_leitura, ler_estado_estacao

COLUNAS_CSV = [
    ("id", "ID"), ("ciclo_id", "Ciclo ID"), ("timestamp", "Data/hora"),
    ("resultado", "Resultado visual"), ("classe_detectada", "Classe detectada"),
    ("confianca", "Confianca (0-1)"), ("duracao_ms", "Duracao (ms)"),
    ("motivo", "Motivo"), ("origem", "Origem"),
    ("modelo_versao", "Modelo de IA / hash"),
    ("serial_status", "Status de comunicacao"),
    ("imagem_path", "Imagem (arquivo)"),
    ("inicio_timestamp", "Inicio do ciclo"),
]
RESULTADOS = {'OK', 'NOK', 'INCONCLUSIVO'}
ORIGENS = {'real', 'simulador'}
MAX_EXPORTACAO = 50000
MOTIVO_SQL = "COALESCE(NULLIF(motivo,''),'Sem motivo registrado')"


class FiltroInvalido(ValueError):
    pass


class ExportacaoGrande(ValueError):
    pass


@dataclass(frozen=True)
class Filtros:
    inicio: str = ""
    fim: str = ""
    resultado: str = ""
    origem: str = ""
    classe: str = ""
    versao: str = ""
    motivo: str = ""

    @classmethod
    def ler(cls, args):
        def campo(nome, limite=160):
            valor = str(args.get(nome, '') or '').strip()
            if len(valor) > limite:
                raise FiltroInvalido(f'Filtro {nome} excede {limite} caracteres.')
            return valor
        inicio = campo('inicio', 10)
        fim = campo('fim', 10)
        for nome, valor in (('inicio', inicio), ('fim', fim)):
            if valor:
                try:
                    if len(valor) != 10 or date.fromisoformat(valor).isoformat() != valor:
                        raise ValueError('Formato invalido')
                except ValueError as exc:
                    raise FiltroInvalido(f'Data {nome} invalida. Use AAAA-MM-DD.') from exc
        if inicio and fim and inicio > fim:
            raise FiltroInvalido('Data inicial posterior a data final.')
        resultado = campo('resultado', 20)
        origem = campo('origem', 20)
        if resultado and resultado not in RESULTADOS:
            raise FiltroInvalido('Resultado invalido.')
        if origem and origem not in ORIGENS:
            raise FiltroInvalido('Origem invalida.')
        return cls(inicio, fim, resultado, origem, campo('classe'), campo('versao'), campo('motivo', 2000))

    def clausula(self):
        campos = []
        parametros = []
        if self.inicio:
            campos.append('substr(timestamp,1,10)>=?')
            parametros.append(self.inicio)
        if self.fim:
            campos.append('substr(timestamp,1,10)<=?')
            parametros.append(self.fim)
        for nome, valor in [('resultado', self.resultado), ('origem', self.origem),
                            ('classe_detectada', self.classe), ('modelo_versao', self.versao),
                            (MOTIVO_SQL, self.motivo)]:
            if valor:
                campos.append(f'{nome}=?')
                parametros.append(valor)
        return (' WHERE ' + ' AND '.join(campos)) if campos else '', parametros

    def descricao(self):
        return ', '.join(f'{label}: {valor}' for label, valor in [
            ('Início', self.inicio), ('Fim', self.fim), ('Resultado', self.resultado),
            ('Origem', self.origem), ('Classe', self.classe), ('Versão da IA', self.versao),
            ('Motivo', self.motivo)
        ] if valor) or 'Todos os registros'


def consultar_estado(db_path):
    with conexao_leitura(db_path) as conn:
        conn.execute('SELECT id FROM inspecoes LIMIT 1').fetchone()
        return ler_estado_estacao(conn)


def _grupos(conn, filtro_sql, parametros, campo, limite):
    # campo e uma expressao SQL fixa, definida pelo proprio sistema.
    sql = (f'SELECT {campo} AS grupo, COUNT(*) AS quantidade FROM inspecoes'
           f'{filtro_sql} GROUP BY {campo} ORDER BY quantidade DESC, grupo LIMIT ?')
    return [dict(r) for r in conn.execute(sql, [*parametros, limite])]


def consultar_analises(db_path, filtros: Filtros, pagina=1, por_pagina=30):
    pagina = max(1, min(int(pagina), 1000000))
    por_pagina = max(1, min(int(por_pagina), 100))
    onde, params = filtros.clausula()
    with conexao_leitura(db_path) as conn:
        conn.execute('BEGIN')
        resumo = resumir_inspecoes(conn, onde, params)
        total = resumo['total']
        paginas = max(1, ceil(total / por_pagina))
        pagina = min(pagina, paginas)
        grupos = {
            'origens': _grupos(conn, onde, params, 'origem', 10),
            'classes': _grupos(conn, onde, params, "COALESCE(NULLIF(classe_detectada,''),'Sem classe')", 20),
            'comunicacao': _grupos(conn, onde, params, 'serial_status', 20),
            'versoes': _grupos(conn, onde, params, 'modelo_versao', 15),
            'motivos': _grupos(conn, onde, params, MOTIVO_SQL, 15),
        }
        tendencia_desc = [dict(r) for r in conn.execute(f'''SELECT
            substr(timestamp,1,10) AS dia,
            COUNT(*) AS total,
            COALESCE(SUM(resultado='OK'),0) AS ok,
            COALESCE(SUM(resultado='NOK'),0) AS nok,
            COALESCE(SUM(resultado='INCONCLUSIVO'),0) AS inconclusivos
            FROM inspecoes {onde} GROUP BY substr(timestamp,1,10)
            ORDER BY dia DESC LIMIT 30''', params)]
        historico = [dict(r) for r in conn.execute(
            f'SELECT * FROM inspecoes {onde} ORDER BY id DESC LIMIT ? OFFSET ?',
            [*params, por_pagina, (pagina - 1) * por_pagina])]
        return {
            'resumo': resumo,
            'grupos': grupos,
            'tendencia': list(reversed(tendencia_desc)),
            'historico': historico,
            'pagina': pagina,
            'por_pagina': por_pagina,
            'paginas': paginas,
            'filtros': filtros.__dict__,
            'nota': 'Taxa de conformidade = OK/(OK+NOK); exclui inconclusivos do denominador.',
        }


def resumir_inspecoes(conn, onde, params):
    resumo = dict(conn.execute(f'''SELECT
            COUNT(*) AS total,
            COALESCE(SUM(resultado='OK'),0) AS ok,
            COALESCE(SUM(resultado='NOK'),0) AS nok,
            COALESCE(SUM(resultado='INCONCLUSIVO'),0) AS inconclusivos,
            ROUND(AVG(CASE WHEN resultado IN ('OK','NOK') THEN confianca END)*100,1) AS confianca_media_pct,
            ROUND(AVG(duracao_ms),1) AS duracao_media_ms,
            COALESCE(SUM(imagem_path IS NOT NULL AND imagem_path != ''),0) AS com_imagem,
            COALESCE(SUM(serial_status='confirmado'),0) AS comunicacao_confirmada
            FROM inspecoes {onde}''', params).fetchone())
    total = resumo['total']
    conclusivos = resumo['ok'] + resumo['nok']
    resumo['taxa_conformidade_pct'] = round(100 * resumo['ok'] / conclusivos, 1) if conclusivos else None
    resumo['taxa_nok_pct'] = round(100 * resumo['nok'] / conclusivos, 1) if conclusivos else None
    resumo['taxa_inconclusivo_pct'] = round(100 * resumo['inconclusivos'] / total, 1) if total else None
    resumo['cobertura_imagens_pct'] = round(100 * resumo['com_imagem'] / total, 1) if total else None
    return resumo


def comparar_periodos(db_path, periodos):
    with conexao_leitura(db_path) as conn:
        conn.execute('BEGIN')
        return [resumir_inspecoes(conn, *periodo.clausula()) for periodo in periodos]


def opcoes_filtros(db_path):
    with conexao_leitura(db_path) as conn:
        return {
            'classes': [r[0] for r in conn.execute('''SELECT DISTINCT classe_detectada FROM inspecoes
                WHERE classe_detectada IS NOT NULL AND classe_detectada != '' ORDER BY classe_detectada''')],
            'versoes': [r[0] for r in conn.execute('''SELECT DISTINCT modelo_versao FROM inspecoes
                WHERE modelo_versao IS NOT NULL AND modelo_versao != '' ORDER BY modelo_versao''')],
        }


def _registros_exportacao(conn, onde, params):
    linhas = [dict(r) for r in conn.execute(
        f'SELECT * FROM inspecoes {onde} ORDER BY id DESC LIMIT ?', [*params, MAX_EXPORTACAO + 1])]
    if len(linhas) > MAX_EXPORTACAO:
        raise ExportacaoGrande(f'Exportacao excede {MAX_EXPORTACAO} registros; reduza o periodo.')
    return linhas


def registros_para_exportacao(db_path, filtros: Filtros):
    onde, params = filtros.clausula()
    with conexao_leitura(db_path) as conn:
        return _registros_exportacao(conn, onde, params)


def consultar_exportacao_excel(db_path, filtros: Filtros):
    onde, params = filtros.clausula()
    with conexao_leitura(db_path) as conn:
        conn.execute('BEGIN')
        registros = _registros_exportacao(conn, onde, params)
        return resumir_inspecoes(conn, onde, params), registros


def celula_csv(valor):
    """Evita formulas disparadas pelo Excel ao abrir um CSV exportado."""
    if valor is None:
        return ''
    texto = str(valor)
    if texto.lstrip(' \t\r\n').startswith(('=', '+', '-', '@')):
        return "'" + texto
    return texto


def gerar_csv(registros):
    buffer = io.StringIO(newline='')
    buffer.write('\ufeff')  # UTF-8 BOM, Excel PT-BR.
    writer = csv.writer(buffer, delimiter=';', quoting=csv.QUOTE_MINIMAL, lineterminator='\r\n')
    writer.writerow([titulo for _, titulo in COLUNAS_CSV])
    for item in registros:
        writer.writerow([celula_csv(item.get(chave)) for chave, _ in COLUNAS_CSV])
    return buffer.getvalue().encode('utf-8')


def gerar_pdf(relatorio, filtros, registros):
    """Resumo do recorte e até 100 inspeções em formato A4 paisagem."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from xml.sax.saxutils import escape
    from datetime import datetime

    def seguro(x):
        return escape(str(x if x is not None else '-'))

    azul = colors.HexColor('#001E50')
    acento = colors.HexColor('#0074BD')
    claro = colors.HexColor('#EAF2FA')
    texto = colors.HexColor('#173552')
    largura = 246 * mm
    margem = (landscape(A4)[0] - largura) / 2 - 6
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), rightMargin=margem,
                            leftMargin=margem, topMargin=17*mm, bottomMargin=17*mm)
    st = getSampleStyleSheet()
    st.add(ParagraphStyle(name='TituloEst3', fontName='Helvetica-Bold',
                          fontSize=23, leading=28, textColor=colors.white))
    st.add(ParagraphStyle(name='PeqEst3', parent=st['Normal'], fontSize=8, leading=11,
                          textColor=texto))
    st.add(ParagraphStyle(name='CabEst3', fontName='Helvetica-Bold', fontSize=9, leading=12,
                          textColor=colors.HexColor('#B3DCFA')))
    st.add(ParagraphStyle(name='SecaoEst3', fontName='Helvetica-Bold', fontSize=13,
                          leading=17, spaceAfter=5, textColor=azul))
    faixa = Table([[[Paragraph('SENAI · VOLKSWAGEN  /  ESTAÇÃO 03', st['CabEst3']),
                     Paragraph('Relatório de inspeções', st['TituloEst3'])]]],
                  colWidths=[largura], hAlign='LEFT')
    faixa.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), azul),
        ('LINEBELOW', (0,0), (-1,-1), 3, acento),
        ('LEFTPADDING', (0,0), (-1,-1), 14),
        ('TOPPADDING', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 9),
    ]))
    story = [faixa, Spacer(1, 3*mm),
             Paragraph('<b>Recorte</b> · ' + seguro(filtros.descricao()), st['PeqEst3']),
             Paragraph('Gerado em ' + datetime.now().astimezone().strftime('%d/%m/%Y às %H:%M'), st['PeqEst3']),
             Spacer(1, 3*mm)]
    r = relatorio['resumo']
    def numero(valor):
        return '-' if valor is None else str(valor).replace('.', ',')
    indicadores = [
        ['Inspeções', 'OK', 'NOK', 'Inconclusivos', 'Conformidade*', 'Tempo médio (ms)'],
        [r['total'], r['ok'], r['nok'], r['inconclusivos'],
         numero(r['taxa_conformidade_pct']) + '%' if r['taxa_conformidade_pct'] is not None else '-',
         numero(r['duracao_media_ms'])]
    ]
    t = Table(indicadores, colWidths=[41*mm]*6, hAlign='LEFT')
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), acento),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('BACKGROUND', (0,1), (-1,1), claro),
        ('TEXTCOLOR', (0,1), (-1,1), azul),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 14),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story += [t, Spacer(1, 2*mm), Paragraph(
        '* Conformidade = OK / (OK + NOK), excluindo inconclusivos. Medidas derivadas dos registros filtrados.',
        st['PeqEst3']), Spacer(1, 5*mm)]

    def painel_grupos(titulo, nome, max_linhas=8):
        lista = relatorio['grupos'][nome][:max_linhas]
        linhas = [['Categoria', 'Registros']] + [[seguro(i['grupo']), i['quantidade']] for i in lista]
        if not lista:
            linhas.append(['Sem dados', '-'])
        tab = Table([[Paragraph(str(x), st['PeqEst3']) if c == 0 else str(x)
                      for c,x in enumerate(row)] for row in linhas], colWidths=[90*mm, 27*mm])
        tab.setStyle(TableStyle([('BACKGROUND', (0,0),(-1,0),claro),
                                 ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                                 ('VALIGN',(0,0),(-1,-1),'TOP'),
                                 ('LINEBELOW',(0,0),(-1,-1),.2,colors.HexColor('#d5dfe6')),
                                 ('TOPPADDING',(0,0),(-1,-1),5),
                                 ('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        return [Paragraph(titulo, st['SecaoEst3']), tab]

    secoes = Table([[painel_grupos('Origem das inspeções', 'origens'), '',
                     painel_grupos('Comunicação', 'comunicacao')]],
                   colWidths=[117*mm, 12*mm, 117*mm], hAlign='LEFT')
    secoes.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'),
                               ('LEFTPADDING', (0,0), (-1,-1), 0),
                               ('RIGHTPADDING', (0,0), (-1,-1), 0)]))
    story += [secoes, Spacer(1, 3*mm)]
    n = min(100, len(registros))
    story.append(Paragraph(f'Histórico · {n} de {r["total"]} inspeções', st['SecaoEst3']))
    if n < r['total']:
        story.append(Paragraph('O PDF detalha as 100 inspeções mais recentes. O Excel e o CSV incluem o recorte completo até 50 mil registros.', st['PeqEst3']))
    linhas = [['ID', 'Data/hora', 'Resultado', 'Classe', 'Confiança', 'Duração', 'Origem', 'Comunicação']]
    for item in registros[:100]:
        confianca = item.get('confianca')
        linhas.append([
            str(item.get('id','')), str(item.get('timestamp',''))[:19].replace('T',' '),
            item.get('resultado'), item.get('classe_detectada'),
            '-' if confianca is None else numero(round(float(confianca)*100, 1)) + '%',
            '-' if item.get('duracao_ms') is None else str(item['duracao_ms'])+' ms',
            item.get('origem'), item.get('serial_status')
        ])
    if len(linhas) == 1:
        linhas.append(['-', 'Sem dados', '-', '-', '-', '-', '-', '-'])
    cor_status = {'OK': '#126449', 'NOK': '#A62E47', 'INCONCLUSIVO': '#765008'}
    detalhes = []
    for linha in linhas[1:]:
        celulas = [seguro(valor) for valor in linha]
        if linha[2] in cor_status:
            celulas[2] = f'<font color="{cor_status[linha[2]]}"><b>{celulas[2]}</b></font>'
        detalhes.append([Paragraph(valor, st['PeqEst3']) for valor in celulas])
    tabela = Table([linhas[0], *detalhes], repeatRows=1, hAlign='LEFT',
                   colWidths=[15*mm, 39*mm, 31*mm, 40*mm, 24*mm, 27*mm, 26*mm, 44*mm])
    tabela.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), azul),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,-1),7),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,claro]),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BOTTOMPADDING',(0,0),(-1,-1),3),
        ('TOPPADDING',(0,0),(-1,-1),3),
    ]))
    story.append(tabela)
    def rodape(canvas, document):
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#607080'))
        canvas.drawString(margem + 6, 10*mm, 'Estação 3 | Relatório gerado a partir do SQLite local')
        canvas.drawRightString(landscape(A4)[0] - margem - 6, 10*mm, 'Página %s' % document.page)
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()
