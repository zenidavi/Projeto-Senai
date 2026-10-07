"use strict";
const el = id => document.getElementById(id);
const percentual = valor => `${Number(valor).toLocaleString("pt-BR", {maximumFractionDigits: 1})}%`;
const horario = valor => valor ? new Date(valor).toLocaleString("pt-BR") : "—";
const duracao = valor => valor === null || valor === undefined ? "—" : `${valor} ms`;
const nomes = {
  SEM_CONEXAO: 'Sem conexão', INICIALIZANDO: 'Inicializando', AGUARDANDO: 'Aguardando',
  INSPECIONANDO: 'Inspecionando', CONCLUIDO: 'Concluído', FALHA: 'Falha',
  DETECCAO_ESTAVEL: 'Detecção estável', TEMPO_LIMITE: 'Tempo limite', SEM_DETECCAO: 'Nenhuma detecção',
  SEM_ESTABILIDADE: 'Detecção instável', MULTIPLAS_DETECCOES: 'Múltiplas detecções',
  CLASSE_DESCONHECIDA: 'Classe desconhecida', BAIXA_CONFIANCA: 'Baixa confiança',
  CAMERA_DESCONECTADA_SIMULADA: 'Câmera desconectada (simulação)', CAMERA_SEM_FRAME: 'Câmera sem imagem',
  CANCELADO_OPERADOR: 'Cancelado pelo operador', IMAGEM_NAO_SALVA: 'Imagem não salva',
  REGISTRO_ANTERIOR: 'Registro da versão anterior',
  desabilitada: 'Desabilitada', conectada: 'Conectada', indisponivel: 'Indisponível',
  confirmado: 'Recepção confirmada', sem_confirmacao: 'Sem confirmação', erro: 'Falha de envio',
  nao_aplicavel: 'Não aplicável', nao_enviado: 'Não enviado', pendente: 'Pendente',
  escrito_sem_ack: 'Enviado sem confirmação', simulada: 'Simulada',
  simulada_erro: 'Falha simulada', simulado_erro: 'Falha simulada', simulado_confirmado: 'Confirmação simulada'
};
const legivel = texto => String(texto || '').split(/([:;])/).map(parte => nomes[parte.trim()] || parte.trim()).join(' ');

function atualizar(dados) {
  const estacao = dados.estacao;
  el('estacao-estado').textContent = legivel(estacao.estado);
  el('estacao-estado').className = 'estado-estacao ' + estacao.estado.toLowerCase();
  el('estacao-motivo').textContent = legivel(estacao.motivo) || 'Processo ativo. Aguardando comando ou conclusão do ciclo.';
  el('estacao-origem').textContent = estacao.origem === 'simulador' ? 'SIMULAÇÃO DE EQUIPAMENTOS' : 'Processo de inspeção';
  for (const nome of ['camera', 'modelo']) {
    const valor = estacao[nome];
    el(`${nome}-status`).textContent = !estacao.online ? 'sem atualização' :
      valor === true ? 'disponível' : valor === false ? 'falha' : 'não verificado';
  }
  el('serial-status').textContent = estacao.online ? legivel(estacao.serial) : 'sem atualização';
  el('ciclo-ativo').textContent = estacao.estado === 'INSPECIONANDO' ? estacao.ciclo_id : '—';
  el('estacao-atualizacao').textContent = horario(estacao.atualizado_em);

  const ultima = dados.ultima;
  const c = dados.contagens;
  el("resultado").textContent = ultima ? ultima.resultado : "AGUARDANDO";
  el("resultado").className = "resultado " + (ultima ? ultima.resultado.toLowerCase() : "neutro");
  el("estado").textContent = ultima ? legivel(ultima.motivo) || 'Último ciclo salvo no banco.' : "Nenhuma inspeção registrada.";
  el("classe").textContent = ultima && ultima.classe_detectada ? ultima.classe_detectada : "—";
  el("confianca").textContent = ultima && ultima.confianca !== null ? percentual(ultima.confianca * 100) : "—";
  el("horario").textContent = ultima ? horario(ultima.timestamp) : "—";
  el("origem").textContent = ultima ? (ultima.origem === "simulador" ? "SIMULAÇÃO" : "Inferência real") : "—";
  el('duracao').textContent = ultima ? duracao(ultima.duracao_ms) : '—';
  el('modelo-versao').textContent = ultima ? ultima.modelo_versao : '—';
  for (const nome of ["total", "ok", "nok", "inconclusivo"]) el(nome).textContent = c[nome];
  const soma = dados.grafico.valores.reduce((a, b) => a + b, 0);
  for (const [indice, nome] of ["ok", "nok", "inconclusivo"].entries()) {
    const p = soma ? 100 * dados.grafico.valores[indice] / soma : 0;
    el(`percentual-${nome}`).textContent = percentual(c[`percentual_${nome}`]);
    el(`grafico-${nome}`).textContent = percentual(p);
    el(`barra-${nome}`).style.width = `${p}%`;
  }
  el("grafico").setAttribute("aria-label", `OK: ${c.ok}; NOK: ${c.nok}; inconclusivos: ${c.inconclusivo}; total: ${c.total}`);
  const tbody = el("historico");
  tbody.replaceChildren();
  for (const item of dados.historico) {
    const tr = document.createElement("tr");
    const valores = [item.id, horario(item.timestamp), item.resultado, item.classe_detectada || '—',
      item.confianca === null ? '—' : percentual(item.confianca * 100), duracao(item.duracao_ms),
      legivel(item.motivo) || '—', legivel(item.serial_status), item.origem];
    for (const [indice, texto] of valores.entries()) {
      const td = document.createElement("td");
      td.textContent = texto;
      if (indice === 0) {
        const ciclo = document.createElement('span');
        ciclo.className = 'ciclo-id';
        ciclo.textContent = item.ciclo_id.slice(0, 8);
        ciclo.title = item.ciclo_id;
        td.append(ciclo);
      }
      if (indice === 2) {
        const badge = document.createElement("span");
        badge.className = "badge " + item.resultado.toLowerCase();
        badge.textContent = texto;
        td.replaceChildren(badge);
      }
      tr.append(td);
    }
    const imagem = document.createElement('td');
    if (item.imagem_path) {
      const link = document.createElement('a');
      link.textContent = 'Ver imagem';
      link.href = `/api/inspecoes/${item.id}/imagem`;
      link.target = '_blank';
      link.rel = 'noopener';
      imagem.append(link);
    } else imagem.textContent = '—';
    tr.append(imagem);
    tbody.append(tr);
  }
  if (!dados.historico.length) {
    const td = document.createElement("td");
    td.colSpan = 10;
    td.textContent = "Nenhuma inspeção registrada.";
    const tr = document.createElement("tr");
    tr.append(td);
    tbody.append(tr);
  }
}

async function consultar() {
  try {
    const resposta = await fetch("/api/status", {cache: "no-store", signal: AbortSignal.timeout(5000)});
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    atualizar(await resposta.json());
    el("conexao").textContent = "● Painel conectado · " + new Date().toLocaleTimeString("pt-BR");
    el("conexao").className = "";
  } catch (erro) {
    el("conexao").textContent = "● Falha de conexão · dados podem estar desatualizados";
    el("conexao").className = "erro";
    el('estacao-estado').textContent = 'ESTADO DESATUALIZADO';
    el('estacao-estado').className = 'estado-estacao';
    for (const nome of ['camera','modelo','serial']) el(`${nome}-status`).textContent = 'sem atualização';
  } finally {
    setTimeout(consultar, Number(document.body.dataset.pollInterval));
  }
}
consultar();
