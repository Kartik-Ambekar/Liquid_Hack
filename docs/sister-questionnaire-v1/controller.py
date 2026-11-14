"""Reference routing only, for synthetic demonstrations. No model or clinical validation."""
import json
from pathlib import Path
ROOT = Path(__file__).parent
CONFIG = json.loads((ROOT / 'questionnaire.json').read_text())
QUESTIONS = CONFIG['questions']
FIELDS = {q['id']: q for q in QUESTIONS}


def new_session(mode='synthetic_demo_only'):
    if mode != 'synthetic_demo_only':
        raise ValueError('This unreviewed package is restricted to synthetic demonstration.')
    return {'mode': mode, 'facts': {}, 'history': [], 'clarifications': {},
            'latched_help': False, 'stopped': False, 'summary_revision': 0,
            'confirmed_revision': None}


def validate_extraction(payload, turn_id, answer):
    if not isinstance(payload, dict) or set(payload) != {'turn_id', 'facts'}:
        raise ValueError('BAD_ENVELOPE')
    if payload['turn_id'] != turn_id or not isinstance(payload['facts'], list):
        raise ValueError('BAD_TURN_OR_FACTS')
    if len(payload['facts']) > len(FIELDS):
        raise ValueError('TOO_MANY_FACTS')
    seen = set()
    for fact in payload['facts']:
        if not isinstance(fact, dict) or set(fact) != {'field_id','value','status','evidence','corrects_previous'}:
            raise ValueError('BAD_FACT_SHAPE')
        key = fact['field_id']
        if not isinstance(key, str) or key not in FIELDS or key in seen:
            raise ValueError('BAD_OR_DUPLICATE_FIELD')
        seen.add(key)
        if not isinstance(fact['evidence'], str) or not fact['evidence'] or fact['evidence'] not in answer:
            raise ValueError('UNSUPPORTED_EVIDENCE')
        if type(fact['corrects_previous']) is not bool:
            raise ValueError('BAD_CORRECTION_FLAG')
        status, value = fact['status'], fact['value']
        if status not in ('answered','unknown','declined','ambiguous'):
            raise ValueError('BAD_STATUS')
        if status != 'answered':
            if value is not None:
                raise ValueError('NONANSWER_HAS_VALUE')
        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError('ANSWER_MISSING_VALUE')
            kind = FIELDS[key]['value_type']
            if kind == 'yes_no' and value not in ('yes','no'):
                raise ValueError('BAD_YES_NO')
            if kind == 'unit' and value not in ('Celsius','Fahrenheit'):
                raise ValueError('BAD_UNIT')
    return payload


def value(session, key):
    f = session['facts'].get(key)
    return f['value'] if f and f['status'] == 'answered' else None


def accept(session, payload, turn_id, answer, current_question_id, source='typed_answer'):
    if source not in ('typed_answer','confirmed_transcript'):
        raise ValueError('UNCONFIRMED_INPUT')
    if current_question_id not in FIELDS:
        raise ValueError('UNKNOWN_QUESTION')
    validate_extraction(payload, turn_id, answer)
    # Validate the entire batch before mutation. Actual applications also enforce request size,
    # turn ordering, idempotency, evidence semantics and explicit user corrections.
    incoming = payload['facts']
    for f in incoming:
        if f['corrects_previous'] and f['field_id'] not in session['facts']:
            raise ValueError('CORRECTION_WITHOUT_PRIOR_FACT')
    for f0 in incoming:
        f = dict(f0)
        key = f['field_id']
        old = session['facts'].get(key)
        # Any validated affirmative safety report latches help before conflict handling.
        if key in CONFIG['critical_fields'] and f['status'] == 'answered' and f['value'] == 'yes':
            session['latched_help'] = True
        if old and old['status'] == 'answered' and f['status'] == 'answered' and old['value'] != f['value'] and not f['corrects_previous']:
            f.update(status='ambiguous', value=None)
        f.update(turn_id=turn_id, source=source)
        session['history'].append({'field_id': key, 'before': old, 'after': dict(f)})
        session['facts'][key] = f
        if key != 'review_confirmed':
            session['summary_revision'] += 1
            session['confirmed_revision'] = None
            session['facts'].pop('review_confirmed', None)
        if key == 'review_confirmed' and f['status'] == 'answered' and f['value'] == 'yes' and not any(x['field_id'] != 'review_confirmed' for x in incoming):
            session['confirmed_revision'] = session['summary_revision']
    # A non-answer to the active question must not leave an endless empty turn loop.
    if not any(f['field_id'] == current_question_id for f in incoming):
        session['facts'][current_question_id] = dict(field_id=current_question_id,
            status='ambiguous', value=None, evidence=None, source='controller', turn_id=turn_id)
    return next_action(session)


def global_action(session, action):
    if action == 'get_help_now':
        session['latched_help'] = True
    elif action == 'stop':
        session['stopped'] = True
    else:
        raise ValueError('Use the UI correction or summary flow for other actions.')
    return next_action(session)


def next_action(s):
    if s['latched_help']:
        return {'action': 'HELP_NOW'}
    if s['stopped']:
        return {'action': 'STOPPED'}
    for key in ('self','adult'):
        if value(s, key) == 'no':
            return {'action': 'OUT_OF_SCOPE', 'reason': key}
    if value(s, 'consent') == 'no':
        return {'action': 'STOPPED', 'reason': 'consent'}
    if value(s, 'pregnancy_context') == 'yes':
        return {'action': 'OUT_OF_SCOPE', 'reason': 'pregnancy_context'}
    # Injury/exposure details are captured for handoff; no injury triage implemented.
    if value(s, 'injury_exposure') == 'yes' and 'event_details' in s['facts']:
        return {'action': 'OUT_OF_SCOPE', 'reason': 'injury_or_exposure'}
    for q in QUESTIONS:
        if not all(value(s, c['field']) == c['equals'] for c in q['when']):
            continue
        key = q['id']
        f = s['facts'].get(key)
        if f is None:
            return {'action': 'ASK', 'question_id': key, 'text': q['text']}
        protected = q['critical'] or q['section'] in ('setup','scope')
        if f['status'] in ('unknown','declined','ambiguous'):
            if f['status'] == 'ambiguous' or protected:
                n = s['clarifications'].get(key, 0)
                if n < CONFIG['max_clarifications_per_field']:
                    return {'action': 'CLARIFY', 'question_id': key, 'text': q['text']}
                if protected:
                    return {'action': 'ASSESSMENT_INCOMPLETE', 'reason': key}
            continue
        if key == 'review_confirmed':
            if value(s,key) == 'no':
                return {'action': 'REVIEW_CORRECTIONS'}
            if s['confirmed_revision'] != s['summary_revision']:
                return {'action': 'ASK', 'question_id': key, 'text': q['text']}
    return {'action': 'HANDOFF_READY'}


def mark_question_displayed(s, action):
    """Only call once per actual rendered clarification, not during polling."""
    if action['action'] == 'CLARIFY':
        key = action['question_id']
        s['clarifications'][key] = s['clarifications'].get(key,0) + 1
