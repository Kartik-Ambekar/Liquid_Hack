/* Model-independent UI; all questions and next actions come from the server. */
let sid=null, state=null, busy=false, epoch=0, correction=false;
const $=id=>document.getElementById(id);
async function api(path,body){
  const r=await fetch(path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});
  const data=await r.json(); if(!r.ok) throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)); return data;
}
function message(e){$('error').textContent=e.message||String(e);}
function render(data){
  state=data; $('question').textContent=data.sister_message; $('intro').textContent=data.intro;
  $('status').textContent=data.status==='completed'?`Interview stopped: ${data.step}`:`Question: ${data.question_id||'review'}`;
  if(data.audit_error) message(data.audit_error);
  $('choices').replaceChildren();
  for(const c of data.choices){const b=document.createElement('button');b.textContent=c.label;b.disabled=busy;b.onclick=()=>submit(c.label,'choice',c.value);$('choices').append(b);}
  $('answerForm').hidden=!data.question_id; $('voice').hidden=!data.question_id;
  $('send').disabled=busy; $('confirmTranscript').disabled=busy;
  $('confirmSummary').hidden=data.step!=='REVIEW_CORRECTIONS'; $('cancelCorrection').hidden=!correction;
  $('fields').replaceChildren();
  for(const f of data.handover_note.fields){
    const row=document.createElement('div');row.className='field';
    const text=document.createElement('span');text.textContent=`${f.question} — ${f.value??f.status}${f.active?'':' (inactive branch)'}`;row.append(text);
    if(f.status!=='unanswered'&&f.id!=='review_confirmed'&&data.step!=='HELP_NOW'&&data.step!=='STOPPED'){
      const b=document.createElement('button');b.textContent='Correct';b.onclick=()=>control('correct',f.id);row.append(b);
    }$('fields').append(row);
  }
  if(data.question_id==='review_confirmed'||data.status==='completed'||data.step==='REVIEW_CORRECTIONS') $('summary').hidden=false;
}
async function start(){
  if(recording) recording.stop(false);
  epoch++; const ticket=epoch; busy=false; correction=false;
  $('error').textContent='';$('answer').value='';$('transcriptPanel').hidden=true;$('summary').hidden=true;
  try{const d=await api('/api/session/start',{});if(ticket!==epoch)return;sid=d.session_id;render(d.prompt);}catch(e){message(e);}
}
async function submit(answer,type='text',choice=null){
  if(busy||!sid||!state.question_id||!answer.trim())return;
  busy=true;render(state);const ticket=epoch;
  const body={session_id:sid,user_input:answer,input_type:type,choice_value:choice,
    question_id:state.question_id,revision:state.revision,turn_id:crypto.randomUUID(),
    voice_meta:type==='voice'?{confirmed:true}:null};
  $('error').textContent='';$('status').textContent='Recording your answer…';
  try{const d=await api('/api/session/turn',body);if(ticket!==epoch)return;correction=false;$('answer').value='';$('transcriptPanel').hidden=true;render(d);}
  catch(e){if(ticket===epoch){message(e);try{render(await api(`/api/session/${sid}`));}catch(x){message(x);}}}
  finally{if(ticket===epoch){busy=false;render(state);}}
}
async function control(action,field_id=null){
  if(!sid)return;
  // Help/stop invalidate pending answers immediately; server revisions enforce this too.
  if(recording) recording.stop(false);
  epoch++;busy=false;const ticket=epoch;
  try{const d=await api('/api/session/action',{session_id:sid,action,field_id});if(ticket!==epoch)return;
    if(action==='delete'){sid=null;state=null;$('question').textContent='Session deleted.';$('fields').replaceChildren();$('choices').replaceChildren();$('answerForm').hidden=true;$('voice').hidden=true;$('summary').hidden=true;return;}
    correction=action==='correct';render(d);
  }catch(e){message(e);}
}
$('answerForm').onsubmit=e=>{e.preventDefault();submit($('answer').value);};
$('help').onclick=()=>control('get_help_now');$('stop').onclick=()=>control('stop');$('restart').onclick=start;
$('delete').onclick=()=>control('delete');$('cancelCorrection').onclick=()=>control('cancel_correction');
$('confirmSummary').onclick=()=>control('confirm_summary');$('summaryToggle').onclick=()=>{$('summary').hidden=!$('summary').hidden;};
$('download').onclick=()=>{if(!state)return;const u=URL.createObjectURL(new Blob([state.handover_note.raw_text],{type:'text/plain'}));const a=document.createElement('a');a.href=u;a.download=`handoff-${sid}.txt`;a.click();URL.revokeObjectURL(u);};
async function transcribe(blob){
  const ticket=epoch,revision=state.revision;const fd=new FormData();fd.append('audio',blob,'answer.wav');
  $('transcriptPanel').hidden=true;$('transcribe').disabled=true;
  try{const r=await fetch('/api/transcribe',{method:'POST',body:fd});const d=await r.json();
    if(!r.ok||!d.ok||!d.transcript)throw Error('Transcription unavailable. Please type your answer.');
    if(ticket!==epoch||revision!==state.revision)return;
    $('transcript').value=d.transcript;$('transcriptPanel').hidden=false;
  }catch(e){if(ticket===epoch)message(e);}finally{$('transcribe').disabled=false;}
}
$('transcribe').onclick=()=>{const f=$('audio').files[0];if(f)transcribe(f);};
$('confirmTranscript').onclick=()=>submit($('transcript').value,'voice');
let recording=null;
$('record').onclick=async()=>{
  if(recording){recording.stop();return;}
  try{
    const recordingEpoch=epoch,recordingRevision=state.revision;
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    if(recordingEpoch!==epoch||recordingRevision!==state.revision){stream.getTracks().forEach(t=>t.stop());return;}
    const ctx=new AudioContext({sampleRate:16000}),source=ctx.createMediaStreamSource(stream),processor=ctx.createScriptProcessor(4096,1,1),chunks=[];
    processor.onaudioprocess=e=>chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    source.connect(processor);processor.connect(ctx.destination);$('record').textContent='Stop recording';
    const timer=setTimeout(()=>recording?.stop(),30000);
    recording={stop:async(send=true)=>{recording=null;clearTimeout(timer);processor.disconnect();source.disconnect();stream.getTracks().forEach(t=>t.stop());
      const rate=ctx.sampleRate;await ctx.close();recording=null;$('record').textContent='Record answer';
      const n=chunks.reduce((n,a)=>n+a.length,0),b=new ArrayBuffer(44+n*2),v=new DataView(b);
      const put=(off,s)=>{for(let i=0;i<s.length;i++)v.setUint8(off+i,s.charCodeAt(i));};
      put(0,'RIFF');v.setUint32(4,36+n*2,true);put(8,'WAVE');put(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);put(36,'data');v.setUint32(40,n*2,true);
      let off=44;for(const a of chunks)for(const x of a){const f=Math.max(-1,Math.min(1,x));v.setInt16(off,f<0?f*32768:f*32767,true);off+=2;}
      if(send&&recordingEpoch===epoch&&recordingRevision===state.revision) await transcribe(new Blob([b],{type:'audio/wav'}));}};
  }catch(e){message('Microphone unavailable. Use typed input or a WAV file.');}
};
api('/api/hardware-status').then(d=>$('runtime').textContent=JSON.stringify(d,null,2)).catch(message);
start();
