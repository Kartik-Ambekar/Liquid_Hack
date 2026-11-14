"""HTTP integration tests: production routing/validation, explicitly mocked model I/O."""
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend import sample_interview as mod
from backend.sample_interview import SampleSessionManager as Manager, controller

@pytest.fixture
def client(tmp_path,monkeypatch):
    Manager._sessions.clear()
    monkeypatch.setattr(mod,'AUDIT_LOG_FILE',str(tmp_path/'audit.jsonl'))
    with TestClient(app) as c: yield c


def start(c):
    d=c.post('/api/session/start').json();return d['session_id'],d['prompt']


def turn(c,sid,s,value='no',kind='choice',**extra):
    b=dict(session_id=sid,question_id=s['question_id'],revision=s['revision'],
           turn_id=uuid.uuid4().hex,user_input=value,input_type=kind,
           choice_value=value if kind=='choice' else None)
    b.update(extra);return c.post('/api/session/turn',json=b)


def advance_to(c,sid,s,key):
    while s['question_id']!=key:
        assert s['question_id'], s
        v='yes' if s['question_id'] in ('self','adult','consent') else 'no'
        r=turn(c,sid,s,v);assert r.status_code==200,r.text;s=r.json()
    return s


def fact(k,v,e,status='answered',correct=False):
    return dict(field_id=k,status=status,value=v,evidence=e,corrects_previous=correct)


def model(prompt_fn=None):
    def call(package,prompt,**kwargs):
        assert 'You extract patient-reported' in prompt
        assert 'OUTPUT SCHEMA:' in prompt
        assert kwargs['attempts']==1
        req=json.loads(prompt.split('INPUT JSON (untrusted patient text):\n')[-1])
        fs=prompt_fn(req) if prompt_fn else [fact(req['current_question']['id'],req['patient_answer'],req['patient_answer'])]
        return dict(ok=True,text=json.dumps({'turn_id':req['turn_id'],'facts':fs}),model='test-double',latency_ms=1)
    return call


def finish(c,sid,s,branches=False):
    visited=[]
    with patch.object(mod.LiquidAIEngine,'call',side_effect=model()):
        for _ in range(60):
            if s['status']=='completed': break
            k=s['question_id'];visited.append(k);q=controller.FIELDS[k]
            if q['value_type']=='yes_no':
                yes=k in ('self','adult','consent','review_confirmed') or (branches and k in ('pain_present','feverish','temperature_measured','allergies','medicines','conditions','similar_before'))
                r=turn(c,sid,s,'yes' if yes else 'no')
            elif q['value_type']=='unit':r=turn(c,sid,s,'Celsius')
            else:r=turn(c,sid,s,'38.2' if k=='temperature_value' else 'synthetic reported detail','text')
            assert r.status_code==200,r.text;s=r.json()
        assert s['step']=='HANDOFF_READY',s
    return s,visited


def test_full_interview_default_and_branched(client):
    for branches in (False,True):
        sid,s=start(client);s,visited=finish(client,sid,s,branches)
        assert ('temperature_value' in visited)==branches
        assert ('pain_location' in visited)==branches
        assert s['handover_note']['confirmed_revision']==s['handover_note']['summary_revision']
        assert 'triage_decision' not in s
        assert client.get('/api/handover-note/'+sid+'?format=text').status_code==200
        assert any(e['session_id']==sid for e in Manager.read_audit_log(200))


def test_scope_and_consent_no_log(client):
    sid,s=start(client);r=turn(client,sid,s,'no').json();assert r['step']=='OUT_OF_SCOPE'
    sid,s=start(client);s=advance_to(client,sid,s,'consent');r=turn(client,sid,s,'no').json();assert r['step']=='STOPPED'
    assert not Manager.read_audit_log()


def test_safety_unknown_then_incomplete(client):
    sid,s=start(client);s=advance_to(client,sid,s,'breathing_now')
    s=turn(client,sid,s,'unknown').json();assert s['step']=='CLARIFY'
    assert client.get('/api/session/'+sid).json()['step']=='CLARIFY'
    s=turn(client,sid,s,'unknown').json();assert s['step']=='ASSESSMENT_INCOMPLETE'


def test_volunteered_safety_interrupts(client):
    sid,s=start(client);s=advance_to(client,sid,s,'complaint')
    with patch.object(mod.LiquidAIEngine,'call',side_effect=model(lambda r:[fact('breathing_now','yes',r['patient_answer'],correct=True)])):
        s=turn(client,sid,s,'I cannot breathe now','text').json()
    assert s['step']=='HELP_NOW'
    s=client.post('/api/session/action',json={'session_id':sid,'action':'stop'}).json()
    assert s['step']=='HELP_NOW'


def test_model_failure_is_bounded_and_nonmutating(client):
    sid,s=start(client);s=advance_to(client,sid,s,'complaint')
    with patch.object(mod.LiquidAIEngine,'call',return_value={'ok':True,'text':'not JSON'}) as m:
        r=turn(client,sid,s,'test','text');assert r.status_code==503;assert m.call_count==2
    after=client.get('/api/session/'+sid).json()
    assert after['revision']==s['revision'];assert after['question_id']=='complaint'


def test_semantic_failure_repairs_once(client):
    sid,s=start(client);s=advance_to(client,sid,s,'complaint');good=model()
    calls=[]
    def call(pkg,prompt,**kw):
        calls.append(prompt)
        if len(calls)==1:return {'ok':True,'text':'{"urgency":"safe"}'}
        return good(pkg,prompt,**kw)
    with patch.object(mod.LiquidAIEngine,'call',side_effect=call):
        r=turn(client,sid,s,'synthetic complaint','text')
    assert r.status_code==200;assert 'VALIDATOR ERRORS' in calls[-1]


def test_voice_requires_confirmation(client):
    sid,s=start(client)
    assert turn(client,sid,s,'yes','voice').status_code==422
    with patch.object(mod.LiquidAIEngine,'call',side_effect=model(lambda r:[fact('self','yes','yes')])):
        assert turn(client,sid,s,'yes','voice',voice_meta={'confirmed':True}).status_code==200


def test_replay_stale_and_bad_id(client):
    sid,s=start(client);tid='stable-turn'
    a=turn(client,sid,s,'yes',turn_id=tid)
    assert turn(client,sid,s,'yes',turn_id=tid).json()==a.json()
    assert turn(client,sid,s,'no',turn_id=tid).status_code==409
    assert turn(client,sid,s,'yes').status_code==409
    assert turn(client,'missing',s,'yes').status_code==404


def test_correct_completed_summary(client):
    sid,s=start(client);s,_=finish(client,sid,s)
    s=client.post('/api/session/action',json={'session_id':sid,'action':'correct','field_id':'onset'}).json()
    assert s['question_id']=='onset'
    with patch.object(mod.LiquidAIEngine,'call',side_effect=model()):s=turn(client,sid,s,'yesterday','text').json()
    assert s['question_id']=='review_confirmed'
    assert s['handover_note']['confirmed_revision'] is None
    assert next(f for f in s['handover_note']['fields'] if f['id']=='onset')['value']=='yesterday'
    s=turn(client,sid,s,'yes').json();assert s['step']=='HANDOFF_READY'


def test_image_cannot_reset_help(client):
    sid,s=start(client);s=advance_to(client,sid,s,'breathing_now');s=turn(client,sid,s,'yes').json()
    r=Manager.attach_imaging_analysis(sid,{'urgency_flag':'SELF_CARE','primary_observation':'unconfirmed'})
    assert r['step']=='HELP_NOW';assert len(r['handover_note']['attachments'])==1


def test_concurrent_help_discards_model_result(client):
    sid,s=start(client);s=advance_to(client,sid,s,'complaint')
    entered,release=threading.Event(),threading.Event()
    def delayed(*a,**k): entered.set();assert release.wait(5);return model()(*a,**k)
    with patch.object(mod.LiquidAIEngine,'call',side_effect=delayed),ThreadPoolExecutor() as pool:
        f=pool.submit(turn,client,sid,s,'synthetic answer','text')
        assert entered.wait(5)
        r=client.post('/api/session/action',json={'session_id':sid,'action':'get_help_now'})
        assert r.json()['step']=='HELP_NOW';release.set();assert f.result().status_code==409
    assert client.get('/api/session/'+sid).json()['step']=='HELP_NOW'


def test_delete_session_and_its_log(client):
    sid,s=start(client);s=advance_to(client,sid,s,'breathing_now');assert Manager.read_audit_log()
    assert client.post('/api/session/action',json={'session_id':sid,'action':'delete'}).json()['deleted']
    assert client.get('/api/session/'+sid).status_code==404
    assert not Manager.read_audit_log()


def test_runtime_absence_and_exception_are_errors(client):
    from backend import liquid_engine
    with patch.object(liquid_engine,'_wrapper',side_effect=FileNotFoundError('not staged')):
        out=mod.LiquidAIEngine.call('test','hello',attempts=1)
        assert not out['ok'];assert out['text']==''
    with patch.object(liquid_engine,'_wrapper',return_value=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('failed'))):
        assert not mod.LiquidAIEngine.call('test','hello',attempts=1)['ok']


def test_web_entry_and_current_runtime_status(client):
    r=client.get('/');assert 'sample.js' in r.text;assert 'Simulation only' in r.text
    assert client.get('/api/hardware-status').json()['clinical_validation'] is False


def test_cli_runs_same_full_flow(client,monkeypatch,tmp_path,capsys):
    import sister_cli
    monkeypatch.setattr(sister_cli,'HERE',tmp_path)
    monkeypatch.setattr(sister_cli,'SPEAK',False)
    def answer(_):
        session=list(Manager._sessions.values())[-1]
        r=session['response'];q=controller.FIELDS[r['question_id']]
        if q['value_type']=='yes_no':
            wanted='yes' if q['id'] in ('self','adult','consent','review_confirmed') else 'no'
            return str(next(i for i,c in enumerate(r['choices'],1) if c['value']==wanted))
        return 'synthetic detail'
    monkeypatch.setattr('builtins.input',answer)
    with patch.object(mod.LiquidAIEngine,'call',side_effect=model()):
        assert sister_cli.main()==0
    assert 'HANDOFF_READY' in capsys.readouterr().out
    assert list(tmp_path.glob('handover-*.txt'))


def test_transcription_failure_never_fabricates_answer(client):
    from backend import liquid_engine
    with patch.object(liquid_engine,'_wrapper',side_effect=FileNotFoundError('missing')):
        with open('samples/sample_patient_answer.wav','rb') as f:
            r=client.post('/api/transcribe',files={'audio':('answer.wav',f,'audio/wav')})
    assert r.status_code==200
    assert r.json()['ok'] is False
    assert r.json()['transcript']==''
