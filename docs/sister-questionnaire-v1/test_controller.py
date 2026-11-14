import json
import unittest
from controller import *

def fact(k,v,status='answered',cor=False):
    return {'field_id':k,'status':status,'value':v,'evidence':'answer','corrects_previous':cor}

def seed(s,**values):
    for k,v in values.items(): s['facts'][k]=fact(k,v)

def baseline():
    s=new_session()
    seed(s,self='yes',adult='yes',consent='yes',pregnancy_context='no')
    seed(s,**{k:'no' for k in CONFIG['critical_fields']})
    return s

class Routing(unittest.TestCase):
    def test_demo_gate(self):
        with self.assertRaises(ValueError): new_session('patient_use')
    def test_first_question(self):
        self.assertEqual(next_action(new_session())['question_id'],'self')
    def test_scope(self):
        s=new_session(); seed(s,self='no')
        self.assertEqual(next_action(s)['action'],'OUT_OF_SCOPE')
    def test_consent(self):
        s=new_session(); seed(s,consent='no')
        self.assertEqual(next_action(s)['action'],'STOPPED')
    def test_unknown_safety(self):
        s=baseline(); s['facts']['breathing_now']=fact('breathing_now',None,'unknown')
        a=next_action(s); self.assertEqual(a['action'],'CLARIFY')
        self.assertEqual(next_action(s),a) # polling cannot consume clarification
        mark_question_displayed(s,a)
        self.assertEqual(next_action(s)['action'],'ASSESSMENT_INCOMPLETE')
    def test_midstream_help_and_latch(self):
        s=baseline()
        a=accept(s,{'turn_id':'t','facts':[fact('breathing_now','yes',cor=True)]},'t','answer','complaint')
        self.assertEqual(a['action'],'HELP_NOW')
        accept(s,{'turn_id':'u','facts':[fact('breathing_now','no',cor=True)]},'u','answer','breathing_now')
        self.assertEqual(next_action(s)['action'],'HELP_NOW')
    def test_direct_help(self):
        self.assertEqual(global_action(new_session(),'get_help_now')['action'],'HELP_NOW')
    def test_conditional_skips_and_completion(self):
        s=baseline()
        for q in QUESTIONS:
            if q['id'] not in s['facts']:
                s['facts'][q['id']]=fact(q['id'], 'no' if q['value_type']=='yes_no' else 'reported')
        seed(s,pain_present='no',feverish='no',review_confirmed='yes')
        for k in ('pain_location','pain_description','pain_change','temperature_value','temperature_unit','temperature_time','temperature_measured'):
            s['facts'].pop(k)
        s['confirmed_revision']=s['summary_revision']
        self.assertEqual(next_action(s)['action'],'HANDOFF_READY')
    def test_reject_extra_engine_field(self):
        with self.assertRaises(ValueError): validate_extraction({'turn_id':'t','facts':[],'urgency':'safe'},'t','answer')
    def test_reject_wrong_unit(self):
        with self.assertRaises(ValueError): validate_extraction({'turn_id':'t','facts':[fact('temperature_unit','probably Celsius')]},'t','answer')
    def test_reject_evidence(self):
        with self.assertRaises(ValueError): validate_extraction({'turn_id':'t','facts':[fact('onset','yesterday')]},'t','different')
    def test_conflict_and_history(self):
        s=baseline(); seed(s,onset='yesterday')
        accept(s,{'turn_id':'t','facts':[fact('onset','today')]},'t','answer','onset')
        self.assertEqual(s['facts']['onset']['status'],'ambiguous')
        self.assertEqual(s['history'][-1]['before']['value'],'yesterday')
    def test_asr_must_be_confirmed(self):
        with self.assertRaises(ValueError): accept(baseline(),{'turn_id':'t','facts':[]},'t','answer','onset',source='raw_asr')
    def test_correction_cannot_confirm_unseen_summary(self):
        s=baseline(); seed(s,onset='yesterday')
        accept(s,{'turn_id':'t','facts':[fact('onset','today',cor=True),fact('review_confirmed','yes')]},'t','answer','review_confirmed')
        self.assertIsNone(s['confirmed_revision'])
    def test_examples_are_valid(self):
        for case in json.loads((ROOT/'examples.json').read_text()):
            validate_extraction(case['expected_output'],case['input']['turn_id'],case['input']['patient_answer'])

if __name__=='__main__': unittest.main()
