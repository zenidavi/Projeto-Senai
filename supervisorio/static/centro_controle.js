/* Centro de Controle E3 — visualização sobre o supervisório existente.
 * Não inicia inspeções, não toca em hardware nem altera IDs consumidos por dashboard.js.
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const create = (tag, className, value) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  };
  function start() {
    if (document.body.classList.contains('cc-center')) return;
    const header = document.querySelector('body > header');
    const main = document.querySelector('body > main');
    if (!header || !main) return;
    const analytics = !!$('filtros-form');
    document.body.classList.add('cc-center');
    if (analytics) document.body.classList.add('cc-analytics');
    const shell = create('div', 'cc-shell');
    const aside = create('aside', 'cc-sidebar');
    aside.setAttribute('aria-label', 'Menu do centro de controle');
    aside.innerHTML = `<div class="cc-brand"><span class="cc-brand-mark" aria-label="Estação 03">03</span><div><strong>Volkswagen</strong><small>SENAI · Supervisório</small></div></div>`;
    const nav = create('nav', 'cc-navigation');
    nav.setAttribute('aria-label', 'Seções do supervisório');
    const menu = analytics ? [
      ['◫', 'Visão operacional', '/'], ['▥', 'Resumo analítico', '#resumo-titulo'],
      ['▥', 'Filtros de produção', '#filtros-form'], ['▤', 'Histórico detalhado', '#historico'],
      ['▦', 'Exportar relatórios', '#exportacoes']
    ] : [
      ['◫', 'Visão operacional', '#cc-topo'], ['▣', 'Câmera e inspeção', '#estacao3-camera-supervisorio'],
      ['▥', 'Indicadores', '#cc-indicadores'], ['⌁', 'Fluxo industrial', '#cc-fluxo'],
      ['▤', 'Histórico', '#cc-historico'], ['▦', 'Dados e relatórios', '/analises']
    ];
    menu.forEach(([symbol, label, url], index) => {
      if (url.startsWith('#') && !$((url.slice(1)))) {
        // Links para âncoras que o servidor não forneceu não são adicionados.
        // A maioria dos nós dinâmicos será adicionada abaixo: pule apenas câmera.
        if (url === '#estacao3-camera-supervisorio') return;
      }
      const ativo = index === (analytics ? 1 : 0);
      const a = create('a', ativo ? 'cc-active' : '');
      a.href = url;
      if (ativo) a.setAttribute('aria-current', 'location');
      const icon = create('span', 'cc-nav-icon', symbol);
      a.append(icon, document.createTextNode(label));
      a.addEventListener('click', () => {
        document.body.classList.remove('cc-menu-open');
        nav.querySelectorAll('a').forEach(x => {
          x.classList.remove('cc-active');
          x.removeAttribute('aria-current');
        });
        a.classList.add('cc-active');
        a.setAttribute('aria-current', 'location');
      });
      nav.append(a);
    });
    aside.append(nav);
    const foot = create('div', 'cc-side-bottom');
    foot.innerHTML = `<b>SISTEMA DE INSPEÇÃO</b><span class="cc-dot" id="cc-dot"></span><span id="cc-side-live">Aguardando estação</span><div style="margin-top:11px">YOLOv8 · Flask · SQLite<br>Modo de desenvolvimento local</div>`;
    aside.append(foot);
    const content = create('div', 'cc-content');
    document.body.append(shell);
    shell.append(aside, content);
    const footer = document.querySelector('body > footer');
    content.append(header, main);
    if (footer) content.append(footer);
    header.classList.add('cc-topbar');
    const topMeta = create('div', 'cc-top-meta');
    const menuButton = create('button', 'cc-menu-toggle', '☰ Menu');
    menuButton.type = 'button';
    menuButton.setAttribute('aria-label', 'Abrir ou fechar menu de navegação');
    menuButton.addEventListener('click', () => document.body.classList.toggle('cc-menu-open'));
    topMeta.append(menuButton);
    const clockWrap = create('div');
    clockWrap.innerHTML = `<div class="cc-eyebrow">HORÁRIO LOCAL</div><strong id="cc-time">--:--:--</strong>`;
    topMeta.append(clockWrap);
    if (!analytics) {
      const link = create('a', 'cc-quick', 'Ver análises');
      link.href = '/analises'; link.id = 'cc-analytics-link';
      topMeta.append(link);
    }
    header.append(topMeta);
    if (!analytics) {
      fetch('/analises', {method:'HEAD', cache:'no-store', signal:AbortSignal.timeout(2600)})
        .then(response => {if (!response.ok) {
          document.querySelectorAll('.cc-navigation a[href="/analises"], #cc-analytics-link').forEach(link => link.remove());
        }})
        .catch(() => {});
    }
    const refreshClock = () => {
      const clock = $('cc-time');
      if (clock) clock.textContent = new Date().toLocaleTimeString('pt-BR');
    };
    refreshClock(); setInterval(refreshClock, 1000);
    if (analytics) {
      const anchor = $('resumo-titulo');
      if (anchor) anchor.scrollMarginTop = '20px';
      return;
    }
    buildMain(main);
    loadData(); setInterval(loadData, 7000);
  }
  function buildMain(main) {
    main.classList.add('cc-dashboard-grid');
    const hero = create('section', 'cc-intro');
    hero.id = 'cc-topo';
    const intro = create('div');
    intro.innerHTML = `<h2>Visão operacional</h2><p>Acompanhe o último ciclo, os indicadores de qualidade e o histórico da estação.</p>`;
    hero.append(intro);
    const system = create('div', 'cc-system-state');
    system.innerHTML = `<span>ESTADO DO PROCESSO</span><strong id="cc-online">Consultando…</strong>`;
    hero.append(system);
    const abas = main.querySelector('.abas-estacao');
    if (abas) abas.after(hero);
    else main.prepend(hero);
    const camera = $('estacao3-camera-supervisorio');
    if (camera) camera.classList.add('cc-camera');
    else document.body.classList.add('cc-no-camera');
    const operational = $('estacao-estado')?.closest('section');
    if (operational) operational.classList.add('cc-operational');
    const latest = $('resultado')?.closest('section');
    if (latest) latest.classList.add('cc-latest');
    const stats = $('total')?.closest('.metricas');
    if (stats) {stats.classList.add('cc-metrics');stats.id = 'cc-indicadores';}
    const chart = $('grafico')?.closest('section');
    if (chart) chart.classList.add('cc-original-chart');
    const history = $('historico')?.closest('section');
    if (history) { history.classList.add('cc-historic');history.id = 'cc-historico'; }
    const notes = main.querySelector('.nota');
    if (notes && notes.parentElement===main) notes.classList.add('cc-note');

    const trend = create('section', 'painel cc-trend-card');
    trend.id = 'cc-tendencia';
    trend.innerHTML = `<div class="cc-subtitle">TELEMETRIA / EVENTOS</div><div class="cc-section-title"><h2>Inspeções recentes</h2><small>Últimos 20 registros</small></div><div id="cc-bars" class="cc-empty-graph">Consultando histórico…</div><div class="cc-legend"><span><i style="background:#46e3b2"></i>OK</span><span><i style="background:#ff7890"></i>NOK</span><span><i style="background:#ffcb6d"></i>Inconclusivo</span></div><p class="cc-layout-note">Altura da barra representa a confiança registrada. Inconclusivos não possuem score.</p>`;
    const topology = create('section', 'painel cc-topology');
    topology.id='cc-fluxo';
    topology.innerHTML = `<div class="cc-subtitle">ARQUITETURA / COMPONENTES</div><div class="cc-section-title"><h2>Fluxo de inspeção</h2><small>Disponibilidade reportada pelo sistema</small></div><div class="cc-flow"><div class="cc-flow-node"><b>01 · Webcam</b><span id="cc-flow-camera">Não verificada</span></div><div class="cc-flow-arrow">›</div><div class="cc-flow-node"><b>02 · YOLOv8</b><span id="cc-flow-model">Não verificado</span></div><div class="cc-flow-arrow">›</div><div class="cc-flow-node"><b>03 · SQLite</b><span id="cc-flow-db">Aguardando API</span></div><div class="cc-flow-arrow">›</div><div class="cc-flow-node"><b>04 · Controlador</b><span id="cc-flow-gateway">Integração pendente</span></div></div><div class="cc-flow-foot"><span>● Resultado visual ≠ confirmação de comunicação</span><span>● FPS: medição pendente</span></div>`;
    const events = create('section', 'painel cc-events');
    events.id='cc-atividade';
    events.innerHTML = `<div class="cc-subtitle">RASTREABILIDADE / LOG</div><div class="cc-section-title"><h2>Atividade recente</h2><small>Base SQLite</small></div><div id="cc-event-list" class="cc-live-feed"><span class="cc-empty">Consultando registros…</span></div>`;
    // Gráficos adicionais são elementos independentes: nunca movemos nem recriamos IDs da aplicação.
    if (stats) stats.after(trend);
    else main.append(trend);
    if (chart) chart.after(topology);
    else main.append(topology);
    topology.after(events);
  }
  function setText(id, content) { const n = $(id); if(n) n.textContent = content; }
  function displayState(value, online) {
    if (!online) return 'Sem atualização';
    if (value===true) return 'Disponível';
    if (value===false) return 'Falha';
    return 'Não verificado';
  }
  function renderRecent(records) {
    const bars = $('cc-bars');
    const list = $('cc-event-list');
    if (!bars || !list) return;
    bars.replaceChildren(); list.replaceChildren();
    const items = Array.isArray(records) ? records.slice(0,20) : [];
    if (!items.length) {
      bars.className='cc-empty-graph';
      bars.textContent='Nenhuma inspeção registrada neste banco.';
      list.append(create('div','cc-empty','Nenhum evento registrado.'));
      return;
    }
    bars.className='cc-bars';
    for(const record of [...items].reverse()) {
      const status = ['OK','NOK','INCONCLUSIVO'].includes(record.resultado) ? record.resultado.toLowerCase() : '';
      const bar=create('div','cc-bar '+status);
      const conf=typeof record.confianca==='number'? Math.max(0,Math.min(1,record.confianca)): null;
      bar.style.height = (conf===null ? 13 : Math.max(8,Math.round(conf*100)))+'%';
      bar.title = `${record.resultado || 'Sem resultado'} · ${conf===null?'sem confiança':(conf*100).toFixed(1)+'%'} · ${record.id ?? 'ID indisponível'}`;
      bars.append(bar);
    }
    items.slice(0,4).forEach(record=>{
      const event=create('div','cc-event');
      const left=create('div');
      const code=create('strong','',`#${record.id ?? '—'}`);
      const label=create('span','cc-event-label',record.classe_detectada || record.motivo || 'Inspeção');
      left.append(code,label);
      const right=create('div'); right.style.textAlign='right';
      const status=create('em',String(record.resultado||'').toLowerCase(),record.resultado || '—');
      const time=create('small','',record.timestamp?new Date(record.timestamp).toLocaleString('pt-BR'):'—');
      right.append(status,create('br'),time);
      event.append(left,right); list.append(event);
    });
  }
  async function loadData() {
    try {
      const res = await fetch('/api/status', {cache:'no-store',signal:AbortSignal.timeout(4500)});
      if (!res.ok) throw new Error('API '+res.status);
      const data=await res.json();
      const state=data.estacao || {};
      const live=!!state.online;
      setText('cc-online',live ? ({INSPECIONANDO:'Inspecionando',AGUARDANDO:'Aguardando',CONCLUIDO:'Concluído',FALHA:'Falha'}[state.estado]||'Conectado') : 'Sem conexão');
      setText('cc-side-live',live?'Estação conectada':'Estação sem atualização');
      const dot=$('cc-dot'); if(dot) dot.classList.toggle('online',live);
      setText('cc-flow-camera',displayState(state.camera,live));
      setText('cc-flow-model',displayState(state.modelo,live));
      setText('cc-flow-db','API SQLite respondendo');
      const serial=state.serial;
      setText('cc-flow-gateway',!live?'Sem atualização': serial==='desabilitada'?'Desabilitado / teste local': serial==='conectada'?'Serial conectada (ACK não verificado aqui)': serial ? 'Serial: '+serial : 'Não verificado');
      renderRecent(data.historico);
    } catch (_) {
      setText('cc-online','Dados indisponíveis');
      setText('cc-side-live','Sem resposta da API');
      setText('cc-flow-db','API indisponível');
      const dot=$('cc-dot'); if(dot) dot.classList.remove('online');
      const bars=$('cc-bars'); if(bars) { bars.className='cc-empty-graph';bars.textContent='API de dados indisponível.'; }
      const events=$('cc-event-list'); if(events) {events.replaceChildren(create('div','cc-empty','Sem atualização de eventos.'));}
    }
  }
  if (document.readyState==='loading') document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
})();
