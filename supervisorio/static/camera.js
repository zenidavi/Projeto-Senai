"use strict";
(function(){
  const painel=document.getElementById('estacao3-camera-supervisorio');
  if(!painel)return;
  const foto=document.getElementById('camera-web-imagem');
  const videoStatus=document.getElementById('camera-web-status');
  const placeholder=document.getElementById('camera-web-placeholder');
  const controleStatus=document.getElementById('camera-web-controle-estado');
  const botao=document.getElementById('camera-web-iniciar');
  const token=painel.dataset.token;
  let enviando=false, ultimoClique=0;
  const proximo=(ms)=>setTimeout(atualizarVideo,ms);

  function atualizarVideo(){
    if(document.hidden){proximo(1000);return;}
    foto.onload=function(){
      foto.hidden=false;placeholder.hidden=true;
      videoStatus.textContent='● Imagem atualizada';proximo(65);
    };
    foto.onerror=function(){
      foto.hidden=true;placeholder.hidden=false;
      videoStatus.textContent='Aguardando inferência...';proximo(1000);
    };
    foto.src='/api/video/frame?t='+Date.now();
  }

  atualizarVideo();
  if(!botao)return;

  async function atualizarControle(){
    try{
      const r=await fetch('/api/video/controle/estado',{cache:'no-store',signal:AbortSignal.timeout(3000)});
      if(!r.ok)throw Error('HTTP '+r.status);
      const d=await r.json();
      if(!enviando&&Date.now()-ultimoClique>1700)controleStatus.textContent=d.motivo;
      botao.disabled=enviando||!d.pronto||Date.now()-ultimoClique<2200;
    }catch(e){
      botao.disabled=true;controleStatus.textContent='Sem comunicação com o controle local.';
    }finally{setTimeout(atualizarControle,1000);}
  }

  botao.addEventListener('click',async()=>{
    if(botao.disabled||enviando)return;
    enviando=true;botao.disabled=true;ultimoClique=Date.now();
    controleStatus.textContent='Enviando solicitação...';
    try{
      const r=await fetch('/api/video/controle/inspecionar',{
        method:'POST',headers:{'X-Estacao3-Token':token,'Content-Type':'application/json'},
        body:'{}',cache:'no-store',signal:AbortSignal.timeout(3000)
      });
      const d=await r.json();
      controleStatus.textContent=d.mensagem||'Solicitação recebida.';
      if(r.ok&&d.solicitacao_id){
        let confirmacao;
        for(let i=0;i<6;i++){
          await new Promise(resolve=>setTimeout(resolve,400));
          const ack=await fetch('/api/video/controle/comando/'+d.solicitacao_id,{
            cache:'no-store',signal:AbortSignal.timeout(3000)
          });
          if(!ack.ok)continue;
          const resultado=await ack.json();
          if(resultado.entregue){confirmacao=resultado;break;}
        }
        if(confirmacao?.aceito === true){
          controleStatus.textContent='Ciclo iniciado. Consulte o histórico após a inspeção.';
        }else if(confirmacao?.aceito === false){
          controleStatus.textContent='A IA recebeu o comando e a estação ainda não podia iniciar outro ciclo.';
        }else if(confirmacao?.entregue){
          controleStatus.textContent='Comando entregue à IA. Consulte o estado da estação.';
        }else{
          controleStatus.textContent='Sem confirmação de entrega do comando. Confira a janela da IA.';
        }
      }
    }catch(e){controleStatus.textContent='Falha ao solicitar inspeção: '+e.message;}
    finally{enviando=false;}
  });
  atualizarControle();
})();
