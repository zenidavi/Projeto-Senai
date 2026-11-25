(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const fmt = v => Number(v).toLocaleString('pt-BR', {minimumFractionDigits:2,maximumFractionDigits:2}) + ' V';
  const ns = 'http://www.w3.org/2000/svg';
  function svg(tag, attrs, label) { const el=document.createElementNS(ns,tag); Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v)); if(label!==undefined) el.textContent=label; return el; }
  function grafico(rows) {
    const g=$('tensao-grafico'); g.replaceChildren();
    const r=rows.slice().reverse(), max=Math.max(2.2,...r.map(v=>v.tensao_v));
    const x=i=>48+(r.length===1?315:i*630/Math.max(1,r.length-1)); const y=v=>195-v/max*165;
    for(let i=0;i<=4;i++){const v=max*i/4;g.append(svg('line',{x1:48,x2:678,y1:y(v),y2:y(v),class:'grid'}),svg('text',{x:8,y:y(v)+4},v.toFixed(2)));}
    g.append(svg('line',{x1:48,x2:678,y1:y(1.1),y2:y(1.1),class:'limite'}));
    if(r.length){g.append(svg('polyline',{points:r.map((v,i)=>`${x(i)},${y(v.tensao_v)}`).join(' '),class:'serie'}));r.forEach((v,i)=>g.append(svg('circle',{cx:x(i),cy:y(v.tensao_v),r:v.saturada?4:2.5,class:v.saturada?'saturado':'normal'})));g.append(svg('text',{x:48,y:217},r[0].horario_local.slice(11,19)),svg('text',{x:678,y:217,'text-anchor':'end'},r.at(-1).horario_local.slice(11,19)));}
    $('tensao-grafico-nota').textContent=r.length?`${r.length} amostras. Pontos amarelos: leitura no teto nominal.`:'Nenhuma medição.';
  }
  function render(d) {
    const u=d.ultima;const c=$('tensao-conexao');c.textContent=d.online?'Recebendo leituras':d.simulacao?'Simulação · sem dados reais':'Sem dados recentes'; c.className='status '+(d.online?'online':'offline');
    $('tensao-valor').textContent=u?fmt(u.tensao_v):'—'; $('tensao-horario').textContent=u?u.horario_local:'Sem leituras';
    const resultado=$('tensao-resultado');resultado.textContent=u?u.avaliacao:'—';resultado.className='tensao-resultado '+(u?.saturada?'aviso-txt':u?.resultado==='APROVADO'?'ok':u?'nok':'');
    $('tensao-mensagem').textContent=d.simulacao?'Dados reais não são exibidos na simulação.':!d.online?'Última leitura, se existente, é histórica. Inicie o leitor de tensão.':u?.saturada?'Atenção: leitura no teto da faixa. Não use como aprovação; ajuste divisor e calibração.':'Leitura de bancada recebida. Valide a tensão com multímetro.';
    const tbody=$('tensao-historico');tbody.replaceChildren();
    for(const v of d.leituras){const tr=document.createElement('tr'); for(const val of [v.horario_local,fmt(v.tensao_v),v.resultado,v.saturada?'Saturada':'Não calibrada',v.porta]){const td=document.createElement('td');td.textContent=val;tr.append(td);}tbody.append(tr);}
    if(!d.leituras.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=5;td.textContent='Nenhuma medição';tr.append(td);tbody.append(tr);}grafico(d.leituras);
  }
  async function refresh(){try{const r=await fetch('/api/tensao',{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);render(await r.json());}catch(e){$('tensao-conexao').textContent='Conexão indisponível';$('tensao-conexao').className='status offline';$('tensao-mensagem').textContent='Falha consultando as leituras. Valores anteriores não são atuais.';}finally{setTimeout(refresh,1500);}}
  refresh();
})();
