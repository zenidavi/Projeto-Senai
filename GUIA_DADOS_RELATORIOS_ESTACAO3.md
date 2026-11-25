# Estação 3 — Dados e Relatórios (versão 1)

**Base:** Projeto-Senai / Python + Flask + SQLite + YOLOv8.
**Objetivo:** acrescentar análise de produção, relatórios e diagnóstico ao supervisório existente, preservando o ciclo de inspeção e o banco local.

## Como abrir

Dados e relatórios já faz parte do Flask principal. Na raiz do projeto, instale as dependências de `requirements.txt` no ambiente Python do projeto e inicie o supervisório:

```powershell
.\.venv\Scripts\python.exe supervisorio/app.py
```

Acesse `http://127.0.0.1:5000/analises` ou use **Dados e relatórios** no menu principal. A consulta ao histórico funciona com a inferência desligada. Quando Flask e inferência usarem `ESTACAO3_DB`, configure o mesmo caminho nos dois processos.

## Consultar um banco somente leitura

```powershell
.\.venv\Scripts\python.exe supervisorio/app.py --somente-leitura
```

O modo abre um banco existente da Estação 3 com schema v2, sem inicializar nem migrar o arquivo. Mantém painel, histórico, imagens, análises, CSV e PDF disponíveis, com comandos de inspeção desabilitados. A prévia continua disponível se uma inferência externa estiver ativa e publicando imagens.

Para um banco em WAL, a leitura ainda depende do acesso aos arquivos auxiliares `-wal` e `-shm` ou da possibilidade de criá-los na pasta. Se houver falha no SENAI, registre o caminho usado e a mensagem do terminal antes de alterar permissões. [Documentação do SQLite sobre WAL e leitura](https://sqlite.org/wal.html#read_only_databases)

## O que está implementado

- Indicadores: total, OK, NOK, inconclusivos, taxa de conformidade, duração e confiança médias, registros com imagem.
- Gráfico de resultados, evolução por até 30 dias com registros, contagem por classe, motivo e comunicação.
- Filtros: data inicial/final, origem real/simulada, resultado, classe e versão/hash de IA.
- Histórico paginado de até 100 linhas por página, com acesso às imagens já salvas.
- Diagnóstico da estação: estado e última atualização da IA, serial, leitura do SQLite, idade da prévia JPEG e falhas de publicação na sessão. A inferência publica os tempos da última captura, inferência com anotação, codificação e gravação do JPEG.
- Excel (`.xlsx`) com resumo, gráfico, cabeçalho fixo e histórico filtrável. CSV para importar os dados em outras ferramentas. Ambos exportam até 50.000 registros por consulta.
- PDF em A4 paisagem com resumo e até 100 inspeções mais recentes do filtro.
- Consultas e exportações com conexão SQLite em modo somente leitura.

### Definições importantes

- A taxa de conformidade considera **OK / (OK + NOK)**, excluindo inconclusivos do denominador.
- Os filtros por origem permitem diferenciar inspeções **reais** das **simuladas**.
- A confiança é um valor do detector, não uma probabilidade comprovada de conformidade industrial.
- Um OK com status `sem_confirmacao` **não** significa que o controlador liberou a peça.
- Ausência de registros mostra `—` ou "Sem dados", não zeros ou métricas estimadas quando a divisão não é definida.
- As exportações PDF e Excel usam `reportlab` e `XlsxWriter`, listados em `requirements.txt`.
- O tempo de resposta da API é medido pelo navegador, e **não** representa FPS da câmera.

## Ainda pendente

1. **FPS e latência:** medir a taxa real na estação, incluindo a exibição no navegador. O limite da publicação da prévia é 12 FPS.
2. **QR Code / rastreabilidade por peça:** ainda não existem `peca_id` nem `modelo_esperado` no schema.
3. **Estoque físico e virtual:** estrutura de dados e integração sem simular estoque físico indevidamente.
4. **Previsão de demanda:** somente depois de definir fontes e rotular dados simulados.
5. **Comparação de modelos e testes de generalização da IA:** conjunto de teste independente.
6. **Comunicação física com Arduino/controlador:** protocolo, ACK e testes de falha.

O Flask está configurado para acesso local em `127.0.0.1`.

## Testes de software

```powershell
python -m unittest discover -s tests -p test_analises_estacao3.py -v
```

Os testes não dependem de webcam, Arduino ou modelo YOLO, e utilizam um banco temporário de teste.
