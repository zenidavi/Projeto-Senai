"""Exportação Excel do recorte da Estação 3."""
from datetime import datetime
from io import BytesIO

from supervisorio.analises_dados import COLUNAS_CSV


def gerar_xlsx(resumo, filtros, registros):
    import xlsxwriter

    buffer = BytesIO()
    azul = '#001E50'
    acento = '#0074BD'
    with xlsxwriter.Workbook(buffer, {
        'constant_memory': True, 'strings_to_formulas': False, 'strings_to_urls': False,
    }) as livro:
        livro.set_properties({'title': 'Estação 03 | Inspeções', 'subject': 'SENAI · Volkswagen'})
        titulo = livro.add_format({'bg_color': azul, 'font_color': 'white', 'bold': True,
                                  'font_size': 17, 'valign': 'vcenter'})
        subtitulo = livro.add_format({'font_color': azul, 'font_size': 10, 'text_wrap': True,
                                     'valign': 'vcenter'})
        cabecalho = livro.add_format({'bg_color': acento, 'font_color': 'white', 'bold': True,
                                     'valign': 'vcenter'})
        fundos = ('#FFFFFF', '#EAF2FA')
        corpo = [livro.add_format({'bg_color': fundo, 'font_color': azul}) for fundo in fundos]
        percentuais = [livro.add_format({'bg_color': fundo, 'font_color': azul,
                                        'num_format': '0.0%'}) for fundo in fundos]
        cores_resultado = {'OK': '#126449', 'NOK': '#A62E47', 'INCONCLUSIVO': '#765008'}
        resultados = {
            resultado: [livro.add_format({'bg_color': fundo, 'font_color': cor, 'bold': True})
                        for fundo in fundos]
            for resultado, cor in cores_resultado.items()
        }

        def faixa(planilha, titulo_texto, ultima_coluna):
            planilha.hide_gridlines(2)
            planilha.set_tab_color(acento)
            planilha.set_row(0, 36)
            planilha.merge_range(0, 0, 0, ultima_coluna, titulo_texto, titulo)
            planilha.set_row(1, 32)
            planilha.merge_range(1, 0, 1, ultima_coluna, filtros.descricao(), subtitulo)
            planilha.merge_range(2, 0, 2, ultima_coluna,
                                  'SQLite da Estação 03 · ' + datetime.now().astimezone().strftime('%d/%m/%Y %H:%M'),
                                  subtitulo)

        painel = livro.add_worksheet('Resumo')
        faixa(painel, 'SENAI · Volkswagen | Resumo de inspeções', 8)
        painel.set_column('A:A', 28)
        painel.set_column('B:B', 16)
        painel.set_column('C:I', 13)
        painel.set_row(4, 24)
        painel.write_row(4, 0, ('Indicador', 'Valor'), cabecalho)
        indicadores = (
            ('Total de inspeções', 'total', False),
            ('OK', 'ok', False),
            ('NOK', 'nok', False),
            ('Inconclusivos', 'inconclusivos', False),
            ('Conformidade', 'taxa_conformidade_pct', True),
            ('Duração média (ms)', 'duracao_media_ms', False),
            ('Confiança média', 'confianca_media_pct', True),
            ('Com imagem', 'com_imagem', False),
        )
        for linha, (rotulo, chave, percentual) in enumerate(indicadores, start=5):
            faixa_linha = linha % 2
            valor = resumo[chave]
            painel.write_string(linha, 0, rotulo, corpo[faixa_linha])
            if valor is None:
                painel.write_blank(linha, 1, None, corpo[faixa_linha])
            else:
                painel.write_number(linha, 1, valor / 100 if percentual else valor,
                                     percentuais[faixa_linha] if percentual else corpo[faixa_linha])
        painel.merge_range('A15:I15', 'Conformidade = OK / (OK + NOK).', subtitulo)
        if resumo['total']:
            grafico = livro.add_chart({'type': 'column'})
            grafico.add_series({
                'categories': ['Resumo', 6, 0, 8, 0], 'values': ['Resumo', 6, 1, 8, 1],
                'categories_data': ['OK', 'NOK', 'Inconclusivos'],
                'values_data': [resumo['ok'], resumo['nok'], resumo['inconclusivos']],
                'points': [{'fill': {'color': cor}} for cor in cores_resultado.values()],
            })
            grafico.set_title({'name': 'Resultado das inspeções'})
            grafico.set_legend({'none': True})
            grafico.set_y_axis({'min': 0, 'num_format': '0'})
            grafico.set_size({'width': 410, 'height': 195})
            painel.insert_chart('D5', grafico)

        historico = livro.add_worksheet('Inspeções')
        faixa(historico, 'SENAI · Volkswagen | Histórico de inspeções', len(COLUNAS_CSV) - 1)
        larguras = (8, 36, 34, 21, 20, 19, 16, 45, 14, 30, 25, 40, 34)
        for coluna, largura in enumerate(larguras):
            historico.set_column(coluna, coluna, largura)
        historico.set_row(4, 24)
        titulos = [nome for _, nome in COLUNAS_CSV]
        titulos[5] = 'Confiança (%)'
        historico.write_row(4, 0, titulos, cabecalho)
        historico.freeze_panes(5, 1)
        historico.autofilter(4, 0, 4 + len(registros), len(titulos) - 1)
        for linha, item in enumerate(registros, start=5):
            faixa_linha = linha % 2
            for coluna, (chave, _) in enumerate(COLUNAS_CSV):
                valor = item.get(chave)
                estilo = corpo[faixa_linha]
                if chave == 'confianca':
                    estilo = percentuais[faixa_linha]
                elif chave == 'resultado' and valor in resultados:
                    estilo = resultados[valor][faixa_linha]
                historico.write(linha, coluna, valor, estilo)
    return buffer.getvalue()
