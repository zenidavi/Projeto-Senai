'use strict';
const byId = id => document.getElementById(id);
const n = x => x == null ? '—' : Number(x).toLocaleString('pt-BR', {maximumFractionDigits: 1});
const pct = x => x == null ? '—' : `${n(x)}%`;
const datafmt = x => x ? new Date(x).toLocaleString('pt-BR') : '—';
let paginaAtual = 1, totalPaginas = 1, carregando = false;
let filtrosAplicados = new URLSearchParams();

function lerFiltros() {
  const qs = new URLSearchParams();
  for (const id of ['inicio', 'fim', 'resultado', 'origem', 'classe', 'versao', 'motivo']) {
    const valor = byId(id)?.value.trim();
    if (valor) qs.set(id, valor);
  }
  return qs;
}
function texto(id, valor) { byId(id).textContent = valor == null || valor === '' ? '—' : String(valor); }
function informarErro(erro) {
  const el = byId('erro');
  el.hidden = !erro;
  el.textContent = erro || '';
}
function novo(tag, classe, textoValue) {
  const item = document.createElement(tag);
  if (classe) item.className = classe;
  if (textoValue !== undefined) item.textContent = textoValue;
  return item;
}
async function requisicao(url) {
  const resposta = await fetch(url, {cache: 'no-store', signal: AbortSignal.timeout(10000)});
  if (!resposta.ok) {
    let mensagem = `HTTP ${resposta.status}`;
    let detalhes;
    try { detalhes = await resposta.json(); mensagem = detalhes.erro || mensagem; } catch {}
    throw Object.assign(new Error(mensagem), {detalhes});
  }
  return resposta.json();
}

function desenharDistribuicao(r) {
  const total = r.total || 0;
  const p1 = total ? 100 * r.ok / total : 0;
  const p2 = total ? 100 * r.nok / total : 0;
  texto('anel-total', n(total));
  texto('leg-ok', `${n(r.ok)} · ${pct(total ? 100*r.ok/total : null)}`);
  texto('leg-nok', `${n(r.nok)} · ${pct(total ? 100*r.nok/total : null)}`);
  texto('leg-inc', `${n(r.inconclusivos)} · ${pct(total ? 100*r.inconclusivos/total : null)}`);
  byId('anel').style.background = total
    ? `conic-gradient(#39cf9b 0 ${p1}%, #f57887 ${p1}% ${p1+p2}%, #ffca78 ${p1+p2}% 100%)`
    : '#304352';
  byId('anel').setAttribute('aria-label', `Total ${total}; OK ${r.ok}; NOK ${r.nok}; inconclusivos ${r.inconclusivos}`);
}
function linhasGrupos(id, grupos, todos) {
  const container = byId(id); container.replaceChildren();
  if (!grupos?.length) { container.append(novo('p', 'vazio', 'Nenhum registro para os filtros selecionados.')); return; }
  const total = Math.max(1, Number(todos) || grupos.reduce((a,x) => a+x.quantidade,0));
  for (const g of grupos) {
    const item = novo('div','item-grupo');
    const topo = novo('div','linha-grupo');
    const clicavel = id === 'motivos' && byId('motivo');
    const rotulo = novo(clicavel ? 'button' : 'span', clicavel ? 'motivo-link' : null,
                       g.grupo || 'Sem informação');
    if (clicavel) {
      rotulo.type = 'button';
      rotulo.onclick = async () => {
        const filtros = new URLSearchParams(filtrosAplicados);
        filtros.set('motivo', g.grupo);
        if (await consultar(1, filtros)) {
          for (const [campo, valor] of new FormData(byId('filtros-form'))) {
            byId(campo).value = filtros.get(campo) || '';
          }
          byId('historico-detalhado').focus();
        }
      };
    }
    topo.append(rotulo, novo('strong',null,n(g.quantidade)));
    const fundo = novo('div','fundo-barra'); const barra = novo('div','fill-barra');
    barra.style.width = `${Math.max(0, Math.min(100,100*g.quantidade/total))}%`;
    fundo.append(barra); item.append(topo,fundo); container.append(item);
  }
}
function desenharTendencia(dias) {
  const parent = byId('tendencia'); parent.replaceChildren();
  if (!dias?.length) { parent.append(novo('p','vazio','Ainda não há inspeções nesse período.')); return; }
  const maximo = Math.max(1, ...dias.map(d=>d.total));
  // Barras empilhadas; zero dias sem dados nao e inventado.
  for (const d of dias) {
    const col = novo('div','dia-col');
    col.title = `${d.dia}: ${d.total} inspeções · OK ${d.ok} · NOK ${d.nok} · INC ${d.inconclusivos}`;
    const numeros = novo('span','dia-total', String(d.total));
    const faixa = novo('div','dia-faixa'); faixa.style.height = `${Math.max(3,100*d.total/maximo)}%`;
    for (const [tipo, valor] of [['ok',d.ok], ['nok',d.nok], ['inc',d.inconclusivos]]) {
      if (valor > 0) { const parte=novo('div',`dia-segmento ${tipo}`); parte.style.height=`${100*valor/d.total}%`; faixa.append(parte); }
    }
    const rotulo = novo('span','dia-rotulo',d.dia.slice(8,10)+'/'+d.dia.slice(5,7));
    col.append(numeros,faixa,rotulo); parent.append(col);
  }
}
function desenharHistorico(dados) {
  const parent=byId('historico'); parent.replaceChildren();
  if (!dados.historico?.length) {
    const linha=novo('tr'), td=novo('td',null,'Nenhuma inspeção localizada.'); td.colSpan=10; linha.append(td);parent.append(linha);
  } else {
    for (const item of dados.historico) {
      const tr=novo('tr');
      const id=novo('td'); id.append(novo('strong',null,String(item.id)));
      id.append(novo('small','id-ciclo',(item.ciclo_id||'').slice(0,10)));
      const ocorrencias = byId('filtros-form').dataset.ocorrencias;
      if (ocorrencias && ['NOK', 'INCONCLUSIVO'].includes(item.resultado)) {
        const link = novo('a', 'ocorrencia-link', 'Ver ocorrência');
        link.href = ocorrencias + '/' + encodeURIComponent(item.id);
        id.append(link);
      }
      tr.append(id);
      tr.append(novo('td',null,datafmt(item.timestamp)));
      const resultado=novo('td');resultado.append(novo('span',`badge ${String(item.resultado).toLowerCase()}`,item.resultado));tr.append(resultado);
      tr.append(novo('td',null,item.classe_detectada||'—'));
      tr.append(novo('td',null,item.confianca == null ? '—' : pct(item.confianca*100)));
      tr.append(novo('td',null,item.duracao_ms == null ? '—': `${n(item.duracao_ms)} ms`));
      tr.append(novo('td',null,item.origem === 'real' ? 'Real' : 'Simulação'));
      tr.append(novo('td',null,item.motivo||'—'));
      tr.append(novo('td',null,item.serial_status||'—'));
      const img=novo('td');
      if (item.imagem_path) {
        const a=novo('a',null,'Ver imagem');a.href=`/api/inspecoes/${encodeURIComponent(item.id)}/imagem`;
        a.target='_blank';a.rel='noopener';img.append(a);
      } else img.textContent='—';
      tr.append(img);parent.append(tr);
    }
  }
  totalPaginas=dados.paginas;
  byId('pagina-numero').textContent=`Página ${dados.pagina} de ${totalPaginas}`;
  byId('anterior').disabled=dados.pagina<=1;
  byId('proxima').disabled=dados.pagina>=totalPaginas;
  byId('historico-contagem').textContent=`${n(dados.resumo.total)} registros encontrados`;
}
function renderDados(dados) {
  const r=dados.resumo;
  texto('k-total',n(r.total));
  texto('k-conformidade',pct(r.taxa_conformidade_pct));
  texto('k-ok',n(r.ok));texto('k-nok',n(r.nok));texto('k-inc',n(r.inconclusivos));
  texto('k-duracao',r.duracao_media_ms == null ? '—' : `${n(r.duracao_media_ms)} ms`);
  texto('k-confianca',pct(r.confianca_media_pct));
  texto('k-imagem',pct(r.cobertura_imagens_pct));
  desenharDistribuicao(r); desenharTendencia(dados.tendencia);
  linhasGrupos('classes',dados.grupos.classes,r.total);
  linhasGrupos('motivos',dados.grupos.motivos,r.total);
  linhasGrupos('comunicacao',dados.grupos.comunicacao,r.total);
  desenharHistorico(dados);
}
async function carregarDiagnostico() {
  try {
    const inicio=performance.now();
    const s=await requisicao('/api/analises/diagnostico');
    texto('diag-api',`${n(performance.now()-inicio)} ms`);
    texto('status-estacao',s.simulacao ? 'SIMULAÇÃO' : s.online ? s.estado : 'SEM CONEXÃO');
    byId('status-estacao').className='status '+(s.online?'online':'offline');
    const statusMenu = byId('cc-side-live');
    if (statusMenu) {
      statusMenu.textContent = s.simulacao ? 'Modo simulação' : s.online ? 'Estação online' : 'Estação sem atualização';
      byId('cc-dot')?.classList.toggle('online', s.online);
    }
    texto('diag-camera',s.simulacao ? 'Simulada' : s.online && s.camera===true ? 'Disponível' : s.online && s.camera===false ? 'Falha' : 'Sem confirmação');
    texto('diag-modelo',s.simulacao ? 'Simulado' : s.online && s.modelo===true ? 'Carregado' : s.online && s.modelo===false ? 'Falha' : 'Sem confirmação');
    texto('diag-serial',s.serial);
    texto('diag-atualizacao',datafmt(s.atualizado_em));
    texto('diag-sqlite','Leitura disponível');
    const estadosPreview = {recente: 'Recente', expirado: 'Expirada',
      horario_invalido: 'Horário inválido', indisponivel: 'Indisponível', simulacao: 'Desativada na simulação'};
    const idade = s.preview.idade_segundos;
    texto('diag-preview', estadosPreview[s.preview.estado] + (idade == null ? '' : ` · ${n(idade)} s`));
    texto('diag-jpeg-falhas', s.falhas_publicacao_jpeg == null ? '—' : n(s.falhas_publicacao_jpeg));
    texto('diag-jpeg-erro', s.ultimo_erro_publicacao_jpeg);
    byId('diag-motivo').textContent = s.motivo || '';
    texto('diag-fps-ia',s.fps_inferencia == null ? 'Não instrumentado' : `${n(s.fps_inferencia)} FPS`);
    texto('diag-fps-video',s.fps_transmissao == null ? 'Não instrumentado' : `${n(s.fps_transmissao)} FPS`);
    texto('diag-latencia',s.latencia_inferencia_ms == null ? '—' : `${n(s.latencia_inferencia_ms)} ms`);
    for (const [id, valor] of [
      ['captura', s.latencia_captura_ms], ['codificacao', s.latencia_codificacao_jpeg_ms],
      ['publicacao', s.latencia_publicacao_jpeg_ms]
    ]) texto('diag-' + id, valor == null ? '—' : `${n(valor)} ms`);
  } catch (e) {
    for (const id of ['camera', 'modelo', 'serial', 'atualizacao', 'preview', 'jpeg-falhas',
      'jpeg-erro', 'fps-ia', 'fps-video', 'latencia', 'api', 'captura', 'codificacao',
      'publicacao']) texto('diag-' + id, '—');
    const falhaSQLite = e.detalhes?.sqlite === 'indisponivel';
    const statusMenu = byId('cc-side-live');
    if (statusMenu) statusMenu.textContent = 'Diagnóstico indisponível';
    byId('cc-dot')?.classList.remove('online');
    texto('diag-sqlite', falhaSQLite ? 'Leitura indisponível' : 'Sem confirmação');
    byId('diag-motivo').textContent = e.message;
    texto('status-estacao', falhaSQLite ? 'SQLite indisponível' : 'Falha de comunicação com API');
    byId('status-estacao').className='status offline';
  }
}
async function consultar(pagina, filtros) {
  if (carregando) return;
  carregando=true;
  const botoes = byId('filtros-form').querySelectorAll('button');
  botoes.forEach(botao => { botao.disabled = true; });
  informarErro('');
  const params = new URLSearchParams(filtros);
  params.set('pagina', String(pagina));
  try {
    const dados=await requisicao('/api/analises/dados?'+params);
    renderDados(dados);
    paginaAtual = dados.pagina;
    filtrosAplicados = filtros;
    for (const id of ['link-xlsx', 'link-pdf', 'link-csv']) {
      const link = byId(id);
      if (!link) continue;
      const url = new URL(link.href);
      url.search = filtrosAplicados.toString();
      link.href = url.href;
    }
    byId('exportacoes').hidden = false;
    const contagem = byId('exportacao-contagem');
    if (contagem) contagem.textContent = 'Exportar consulta · ' + n(dados.resumo.total) +
      (dados.resumo.total === 1 ? ' inspeção' : ' inspeções');
    byId('ultima-consulta').textContent='Atualizado às '+new Date().toLocaleTimeString('pt-BR');
    return true;
  } catch(e) { informarErro(e.message); }
  finally {
    carregando=false;
    botoes.forEach(botao => { botao.disabled = false; });
  }
}
async function carregarOpcoes() {
  try {
    const dados=await requisicao('/api/analises/opcoes');
    for (const [id,lista] of [['classe',dados.classes],['versao',dados.versoes]]) {
      const select=byId(id);
      for (const valor of lista) {const opt=document.createElement('option'); opt.value=valor;opt.textContent=valor;select.append(opt);}
    }
  } catch(e) { informarErro('Não foi possível carregar os filtros: '+e.message); }
}
byId('filtros-form').addEventListener('submit',e=>{e.preventDefault();consultar(1,lerFiltros());});
byId('limpar').addEventListener('click',()=>{byId('filtros-form').reset();consultar(1,lerFiltros());});
byId('anterior').addEventListener('click',()=>consultar(Math.max(1,paginaAtual-1),filtrosAplicados));
byId('proxima').addEventListener('click',()=>consultar(Math.min(totalPaginas,paginaAtual+1),filtrosAplicados));
consultar(1,lerFiltros());
carregarOpcoes();
carregarDiagnostico();
setInterval(carregarDiagnostico,5000);
