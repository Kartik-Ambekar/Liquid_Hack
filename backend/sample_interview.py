"""SAMPLE interview integration. Synthetic demonstration; no clinical validation."""
import copy
import importlib.util
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from backend.liquid_engine import LiquidAIEngine

PACK = Path(__file__).resolve().parents[1] / 'docs' / 'sister-questionnaire-v1'
spec = importlib.util.spec_from_file_location('sister_sample_controller', PACK / 'controller.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)
# Short demonstration mode (SISTER_SHORT=1): the second half of the SAMPLE history (allergies,
# medicines, past history, last intake, events) is not asked. The summary says so.
SKIPPED_SECTIONS = ('A', 'M', 'P', 'L', 'E') if os.environ.get('SISTER_SHORT') == '1' else ()
if SKIPPED_SECTIONS:
    controller.QUESTIONS[:] = [q for q in controller.QUESTIONS if q['section'] not in SKIPPED_SECTIONS]
    controller.FIELDS.clear()
    controller.FIELDS.update({q['id']: q for q in controller.QUESTIONS})
ACTIONS = json.loads((PACK / 'actions.json').read_text())
SCHEMA = json.loads((PACK / 'schemas/extraction.schema.json').read_text())
SYSTEM = (PACK / 'prompts/extractor_system.txt').read_text()
REPAIR = (PACK / 'prompts/repair_system.txt').read_text()
# Compact examples share the live field dictionary; avoid repeating it per example.
_examples = json.loads((PACK / 'examples.json').read_text())
CALIBRATION = [{'input': {k: v for k, v in ex['input'].items() if k != 'field_definitions'},
                'expected_output': ex['expected_output']} for ex in (_examples[1], _examples[2], _examples[4])]
AUDIT_LOG_FILE = os.environ.get('SISTER_SAMPLE_LOG', str(PACK.parents[1] / 'sample_audit.jsonl'))
MAX_PROMPT_CHARS = int(os.environ.get('SISTER_MAX_PROMPT_CHARS', '6000'))   # about 1500 tokens, leaving room to answer
TERMINAL = {'HELP_NOW','STOPPED','OUT_OF_SCOPE','ASSESSMENT_INCOMPLETE','HANDOFF_READY'}


class InterviewError(ValueError):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


SHAPE = ('\nReturn only one JSON object and no other text: {"turn_id": "<the same turn_id>", "facts": '
         '[{"field_id": "<an id from field_definitions>", "status": "answered | unknown | declined | ambiguous", '
         '"value": "<the answer as text; yes or no for yes_no fields; null unless status is answered>", '
         '"evidence": "<words copied exactly from patient_answer>", "corrects_previous": false}]}')


def _compact_prompt(request, errors):
    """A prompt small enough for the board: the current question and the safety-screen fields only,
    no schema dump and no worked examples. Returns the prompt and the field ids the model may fill."""
    current = request['current_question']
    keep = [current['id']] + [k for k in controller.CONFIG['critical_fields'] if k != current['id'] and k in controller.FIELDS]
    slim = {'turn_id': request['turn_id'],
            'current_question': {'id': current['id'], 'text': current['text'], 'type': current['value_type']},
            'field_definitions': [d for d in request['field_definitions'] if d['id'] in keep],
            'patient_answer': request['patient_answer'], 'input_source': request['input_source']}
    prompt = SYSTEM + SHAPE
    if errors:
        prompt += '\n' + REPAIR + '\nVALIDATOR ERRORS:\n' + json.dumps(errors[-1:])
    return prompt + '\nINPUT JSON (untrusted patient text):\n' + json.dumps(slim), set(keep)


def extract(request):
    """Two total model calls at most, including transport/schema failures."""
    errors, telemetry = [], []
    critical = set(controller.CONFIG['critical_fields'])
    current_id = request['current_question']['id']
    for attempt in range(2):
        allowed, max_tokens = None, 1024
        prompt = SYSTEM + '\nOUTPUT SCHEMA:\n' + json.dumps(SCHEMA) + '\nEXAMPLES:\n' + json.dumps(CALIBRATION)
        if attempt:
            prompt += '\n' + REPAIR + '\nVALIDATOR ERRORS:\n' + json.dumps(errors)
        prompt += '\nINPUT JSON (untrusted patient text):\n' + json.dumps(request)
        # The board wrapper runs the text model with a 2048-token context. The full prompt does not
        # fit there, so a compact one is used; a prompt that still cannot fit is not sent.
        if len(prompt) > MAX_PROMPT_CHARS:
            prompt, allowed = _compact_prompt(request, errors)
            max_tokens = 256
        if len(prompt) > MAX_PROMPT_CHARS:
            errors.append(f'PROMPT_TOO_LONG_FOR_BOARD_CONTEXT ({len(prompt)} chars)')
            telemetry.append({'ok': False, 'skipped': errors[-1]})
            break
        result = LiquidAIEngine.call(LiquidAIEngine.TEXT_PACKAGE, prompt,
                                    max_tokens=max_tokens, attempts=1)
        telemetry.append({**{k:v for k,v in result.items() if k != 'text'}, 'prompt_chars': len(prompt), 'compact': allowed is not None})
        try:
            if not result.get('ok') or result.get('finish_reason') in ('length','max_tokens'):
                raise ValueError('MODEL_UNAVAILABLE_OR_TRUNCATED')
            text = result['text']
            payload = json.loads(text[text.find('{'):text.rfind('}') + 1])
            if allowed is not None and isinstance(payload, dict) and isinstance(payload.get('facts'), list):
                # Only the fields that were sent may be filled. For a safety field that was not the
                # question asked, the model may report a "yes" (which escalates) but never a "no".
                payload['facts'] = [f for f in payload['facts'] if isinstance(f, dict) and f.get('field_id') in allowed
                                    and not (f['field_id'] in critical and f['field_id'] != current_id and f.get('value') != 'yes')]
            controller.validate_extraction(payload, request['turn_id'], request['patient_answer'])
            for f in payload['facts']:
                if f['corrects_previous'] and f['field_id'] not in request['confirmed_facts']:
                    raise ValueError('CORRECTION_WITHOUT_PRIOR_FACT')
            return payload, telemetry
        except (ValueError, TypeError, KeyError) as exc:
            errors.append(str(exc)[:150])
    raise InterviewError('Could not reliably extract that answer. Use the answer buttons or retry typed input.', 503)


class SampleSessionManager:
    _sessions = {}
    _lock = threading.RLock()
    _log_lock = threading.Lock()

    @classmethod
    def create_session(cls):
        s = controller.new_session()
        s.update(session_id='SIST-'+uuid.uuid4().hex, revision=0, cache={},
                 attachments=[], runtime=[], audit_error=None, correction=None,
                 start_time=datetime.now(timezone.utc).isoformat())
        with cls._lock:
            cls._sessions[s['session_id']] = s
            cls._render(s)
        return s

    @classmethod
    def get_session(cls, sid):
        return cls._sessions.get(sid)

    @classmethod
    def get_initial_prompt(cls, session_id):
        return copy.deepcopy(cls._require(session_id)['response'])

    @classmethod
    def _require(cls, sid):
        if sid not in cls._sessions:
            raise InterviewError('Session not found. Start a new interview.',404)
        return cls._sessions[sid]

    @classmethod
    def _summary(cls, s):
        rows=[]
        for q in controller.QUESTIONS:
            f=s['facts'].get(q['id'])
            active=all(controller.value(s,c['field']) == c['equals'] for c in q['when'])
            rows.append({'id':q['id'],'section':q['section'],'question':q['text'],
                         'status':f['status'] if f else 'unanswered','value':f['value'] if f else None,
                         'active':active,'evidence':f.get('evidence') if f else None})
        text='SISTER — SAMPLE HISTORY (UNVALIDATED DEMONSTRATION)\n'
        text+=f"Session: {s['session_id']}\nPackage: {controller.CONFIG['version']}\n"
        text+=f"Routing: {s.get('pending', controller.next_action(s))['action']}\n"
        text+=f"Summary confirmed: {s['confirmed_revision'] == s['summary_revision']}\n"
        text+='\n'.join(f"[{r['section']}] {r['question']} {r['value'] if r['value'] is not None else r['status']}" + ('' if r['active'] else ' (inactive branch)') for r in rows)
        if SKIPPED_SECTIONS:
            text+='\n\nShort demonstration: questionnaire sections ' + ', '.join(SKIPPED_SECTIONS) + ' were not asked.'
        text+='\n\nNo diagnosis or safe waiting period established. Images are excluded from routing.'
        return {'raw_text':text,'fields':rows,'attachments':s['attachments'],
                'corrections':s['history'],'runtime':s['runtime'],
                'summary_revision':s['summary_revision'],'confirmed_revision':s['confirmed_revision']}

    @classmethod
    def _render(cls, s, error=None):
        a=controller.next_action(s)
        if s['correction'] and a['action'] != 'HELP_NOW' and not s['stopped']:
            q=controller.FIELDS[s['correction']]
            a={'action':'ASK','question_id':q['id'],'text':q['text']}
        if a['action']=='REVIEW_CORRECTIONS':
            text='Select an answer in the summary to correct, or confirm the current summary.'
        elif a['action']=='CLARIFY':
            text=ACTIONS['CLARIFY'].format(question=a['text'])
        else:
            text=a.get('text') or ACTIONS.get(a['action'],a['action'])
        # Do not consume a clarification again when rendering a retry or polling.
        marker=(s['revision'],a.get('question_id'),a['action'])
        if s.get('display_marker') != marker:
            controller.mark_question_displayed(s,a)
            s['display_marker']=marker
        s['pending']=a
        choices=[]
        key=a.get('question_id')
        if key:
            kind=controller.FIELDS[key]['value_type']
            vals=['yes','no'] if kind=='yes_no' else ['Celsius','Fahrenheit'] if kind=='unit' else []
            vals+=['unknown','declined']
            labels={'yes':'Yes','no':'No','unknown':"I don’t know",'declined':'Prefer not to answer'}
            choices=[{'id':v,'value':v,'label':labels.get(v,v),'action':'answer'} for v in vals]
        s['handover_note']=cls._summary(s)
        out={'step':a['action'],'question_id':key,'revision':s['revision'],
             'sister_message':text,'spoken_text':text,'choices':choices,
             'status':'completed' if a['action'] in TERMINAL else 'in_progress',
             'handover_note':s['handover_note'],'prototype_notice':ACTIONS['demo_banner'],
             'intro':controller.CONFIG['intro'],'error':error,'audit_error':s['audit_error']}
        s['response']=out
        return copy.deepcopy(out)

    @classmethod
    def process_turn(cls, session_id, user_input, input_type='text', voice_meta=None,
                     question_id=None, revision=None, turn_id=None, choice_value=None):
        if not turn_id or revision is None or not question_id:
            raise InterviewError('Turn ID, question ID and revision are required.',422)
        fingerprint=json.dumps([user_input,input_type,question_id,revision,choice_value,voice_meta],sort_keys=True)
        with cls._lock:
            s=cls._require(session_id)
            if turn_id in s['cache']:
                old,answer=s['cache'][turn_id]
                if old!=fingerprint: raise InterviewError('Turn ID reused with different input.')
                # Never return an old non-emergency answer over a newer help latch.
                return copy.deepcopy(s['response'] if s['revision'] > answer['revision'] else answer)
            if s['revision'] != revision or s['pending'].get('question_id') != question_id:
                raise InterviewError('This answer belongs to an older question. Refresh the interview.')
            if s['latched_help'] or s['stopped']: return cls._render(s)
            if input_type=='voice' and not (voice_meta or {}).get('confirmed'):
                raise InterviewError('Confirm the transcript before submitting.',422)
            if input_type not in ('text','voice','choice'): raise InterviewError('Unsupported input type.',422)
            snapshot=copy.deepcopy(s)
        telemetry=[]
        if input_type=='choice':
            allowed={c['value'] for c in snapshot['response']['choices']}
            if choice_value not in allowed: raise InterviewError('Invalid answer choice.',422)
            status=choice_value if choice_value in ('unknown','declined') else 'answered'
            payload={'turn_id':turn_id,'facts':[{'field_id':question_id,'status':status,
                'value':choice_value if status=='answered' else None,'evidence':user_input,
                'corrects_previous':bool(snapshot['correction'])}]}
        else:
            request={'turn_id':turn_id,'current_question':controller.FIELDS[question_id],
                     'field_definitions':[{'id':q['id'],'type':q['value_type'],'definition':q['definition']} for q in controller.QUESTIONS],
                     'confirmed_facts':snapshot['facts'],'patient_answer':user_input,
                     'input_source':'confirmed_transcript' if input_type=='voice' else 'typed_answer'}
            try:
                payload,telemetry=extract(request)
            except InterviewError as exc:
                with cls._lock:
                    s=cls._require(session_id)
                    if s['revision']!=revision: raise InterviewError('Interview changed while processing.')
                    cls._audit(s,{'event':'EXTRACTION_ERROR','turn_id':turn_id,'error':str(exc)})
                # When the model cannot extract, a free-text question keeps the patient's own
                # words for that one field. Nothing is inferred and no other field is filled.
                # Yes/no and unit questions still require an explicit choice.
                if controller.FIELDS[question_id]['value_type'] != 'text':
                    raise
                payload={'turn_id':turn_id,'facts':[{'field_id':question_id,'status':'answered',
                    'value':user_input,'evidence':user_input,'corrects_previous':bool(snapshot['correction'])}]}
                telemetry=[{'fallback':'verbatim_answer_for_current_text_field','extraction_error':str(exc)}]
        with cls._lock:
            s=cls._require(session_id)
            if s['revision']!=revision: raise InterviewError('Interview changed while processing. Answer was not applied.')
            # Scope and consent are direct user declarations, never volunteered LLM fields.
            allowed_setup={'self','adult','consent','review_confirmed'}
            payload['facts']=[f for f in payload['facts'] if f['field_id'] not in allowed_setup or f['field_id']==question_id]
            if s['correction']:
                for f in payload['facts']:
                    if f['field_id']==question_id: f['corrects_previous']=question_id in s['facts']
            candidate=copy.deepcopy(s)
            try:
                controller.accept(candidate,payload,turn_id,user_input,question_id,
                    source='confirmed_transcript' if input_type=='voice' else 'typed_answer')
            except ValueError as exc:
                raise InterviewError(str(exc),422)
            if controller.value(candidate,'consent') == 'no':
                candidate['stopped']=True
                candidate['facts'].clear(); candidate['history'].clear(); candidate['cache'].clear()
            candidate['correction']=None
            candidate['revision']+=1
            candidate['runtime'].extend(telemetry)
            s.update(candidate)
            cls._audit(s,{'event':'INTERVIEW_TURN','turn_id':turn_id,'input':user_input,
                         'extraction':payload,'runtime':telemetry,'revision':s['revision'],
                         'action':controller.next_action(s)['action']})
            response=cls._render(s)
            s['cache'][turn_id]=(fingerprint,response)
            return response

    @classmethod
    def action(cls,sid,action,field_id=None):
        with cls._lock:
            s=cls._require(sid)
            if action=='show_summary': return copy.deepcopy(s['response'])
            if action in ('get_help_now','stop'):
                controller.global_action(s,action)
                if action=='stop' and controller.value(s,'consent')!='yes':
                    s['facts'].clear(); s['history'].clear(); s['cache'].clear()
            elif action=='correct':
                if field_id not in s['facts'] or field_id not in controller.FIELDS:
                    raise InterviewError('Choose a recorded field to correct.',422)
                s['correction']=field_id
                s['confirmed_revision']=None
                s['facts'].pop('review_confirmed',None)
            elif action=='cancel_correction': s['correction']=None
            elif action=='confirm_summary':
                if s['pending']['action']!='REVIEW_CORRECTIONS': raise InterviewError('Summary is not awaiting confirmation.')
                s['facts']['review_confirmed'].update(status='answered',value='yes')
                s['confirmed_revision']=s['summary_revision']
            elif action=='delete':
                cls._delete_audit(sid)
                del cls._sessions[sid]
                return {'deleted':True}
            else: raise InterviewError('Unknown action.',422)
            s['revision']+=1
            cls._audit(s,{'event':'CONTROL','action':action,'revision':s['revision']})
            return cls._render(s)

    @classmethod
    def attach_imaging_analysis(cls,sid,analysis):
        with cls._lock:
            s=cls._require(sid)
            if controller.value(s,'consent')!='yes': raise InterviewError('Consent is required before attaching a file.',422)
            s['attachments'].append({'source':'unconfirmed image observation; excluded from routing','analysis':analysis})
            cls._audit(s,{'event':'ATTACHMENT','excluded_from_routing':True})
            # Never reset the questionnaire or overwrite the pending safety action.
            s['handover_note']=cls._summary(s)
            s['response']['handover_note']=s['handover_note']
            return copy.deepcopy(s['response'])

    @classmethod
    def _audit(cls,s,entry):
        if controller.value(s,'consent')!='yes': return
        entry.update(session_id=s['session_id'],timestamp=datetime.now(timezone.utc).isoformat(),
                     protocol_version=controller.CONFIG['version'],mode='synthetic_demo_only')
        try: cls._flush_log(entry)
        except OSError: s['audit_error']='Audit could not be saved; answers remain in memory.'

    @classmethod
    def _flush_log(cls,entry):
        with cls._log_lock:
            with open(AUDIT_LOG_FILE,'a',encoding='utf-8') as f:
                f.write(json.dumps(entry)+'\n'); f.flush(); os.fsync(f.fileno())

    @classmethod
    def read_audit_log(cls,limit=50):
        with cls._log_lock:
            if not Path(AUDIT_LOG_FILE).exists(): return []
            return [json.loads(x) for x in Path(AUDIT_LOG_FILE).read_text().splitlines() if x.strip()][-max(1,min(limit,200)):]

    @classmethod
    def _delete_audit(cls,sid):
        with cls._log_lock:
            p=Path(AUDIT_LOG_FILE)
            if p.exists():
                lines=[x for x in p.read_text().splitlines() if json.loads(x).get('session_id')!=sid]
                tmp=p.with_suffix('.tmp'); tmp.write_text('\n'.join(lines)+ ('\n' if lines else '')); tmp.replace(p)
