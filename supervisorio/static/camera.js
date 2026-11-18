"use strict";
(() => {
  const painel = document.getElementById("estacao3-camera-supervisorio");
  if (!painel) return;
  const id = nome => document.getElementById(nome);
  const imagem = id("camera-web-imagem"), placeholder = id("camera-web-placeholder");
  const status = id("camera-web-status"), botao = id("camera-web-iniciar");
  const controle = id("camera-web-controle-estado");
  let ocupado = false;
  async function consultar() {
    try {
      const resposta = await fetch("/api/video/controle/estado",{cache:"no-store"});
      if (!resposta.ok) throw Error("Servidor indisponível");
      const dados = await resposta.json();
      botao.disabled = ocupado || !dados.pronto;
      controle.textContent = dados.motivo || "Estado desconhecido";
    } catch {
      botao.disabled = true;
      controle.textContent = "Sem comunicação com o supervisor";
    }
  }
  async function atualizarFrame() {
    const url = "/api/video/frame?ts=" + Date.now();
    try {
      const resposta = await fetch(url,{cache:"no-store"});
      if (!resposta.ok) throw Error("Sem câmera");
      const blob = await resposta.blob();
      if (!blob.type.startsWith("image/")) throw Error("Frame inválido");
      const temporario = URL.createObjectURL(blob);
      const anterior = imagem.dataset.url;
      imagem.onload = () => { if (anterior) URL.revokeObjectURL(anterior); };
      imagem.src = temporario;
      imagem.dataset.url = temporario;
      imagem.hidden = false;
      placeholder.hidden = true;
      status.textContent = "Prévia em execução";
    } catch {
      imagem.hidden = true;
      placeholder.hidden = false;
      status.textContent = "Sem conexão";
    } finally { setTimeout(atualizarFrame,120); }
  }
  botao.addEventListener("click",async () => {
    if (botao.disabled) return;
    ocupado = true;
    botao.disabled = true;
    try {
      const resposta = await fetch("/api/video/controle/inspecionar",{
        method:"POST",headers:{"X-Estacao3-Token":painel.dataset.token}
      });
      const dados = await resposta.json();
      controle.textContent = dados.mensagem || dados.erro || "Falha ao solicitar inspeção";
    } catch { controle.textContent = "Falha ao solicitar inspeção"; }
    finally { ocupado=false; setTimeout(consultar,600); }
  });
  consultar();setInterval(consultar,1400);atualizarFrame();
})();
