"""Real browser + real HTTP app, synthetic model boundary only."""
import json
import socket
import threading
import time
from unittest.mock import patch
import pytest
import uvicorn
from backend.main import app
from backend import sample_interview as mod
from backend.sample_interview import controller


def test_browser_full_flow_and_correction(tmp_path,monkeypatch):
    pw=pytest.importorskip('playwright.sync_api')
    monkeypatch.setattr(mod,'AUDIT_LOG_FILE',str(tmp_path/'browser.jsonl'))
    def model(package,prompt,**kwargs):
        r=json.loads(prompt.split('INPUT JSON (untrusted patient text):\n')[-1])
        return {'ok':True,'model':'browser-test-double','text':json.dumps({'turn_id':r['turn_id'],'facts':[
            {'field_id':r['current_question']['id'],'value':r['patient_answer'],'status':'answered',
             'evidence':r['patient_answer'],'corrects_previous':False}]})}
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    with patch.object(mod.LiquidAIEngine,'call',side_effect=model):
        thread.start()
        try:
            for _ in range(100):
                if server.started:break
                time.sleep(.02)
            assert server.started
            with pw.sync_playwright() as p:
                browser=p.chromium.launch()
                page=browser.new_page(viewport={'width':1100,'height':850})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{port}')
                page.wait_for_function('state !== null')
                for _ in range(60):
                    s=page.evaluate('state')
                    if s['status']=='completed': break
                    k=s['question_id'];q=controller.FIELDS[k];rev=s['revision']
                    if q['value_type']=='yes_no':
                        yes=k in ('self','adult','consent','review_confirmed','feverish','temperature_measured')
                        page.locator('#choices').get_by_role('button',name='Yes' if yes else 'No',exact=True).click()
                    elif q['value_type']=='unit':page.locator('#choices').get_by_role('button',name='Celsius',exact=True).click()
                    else:
                        page.locator('#answer').fill('38.2' if k=='temperature_value' else 'synthetic detail')
                        page.locator('#send').click()
                    page.wait_for_function('(r)=>state.revision > r && !busy',arg=rev)
                assert page.evaluate('state.step')=='HANDOFF_READY'
                assert page.locator('#summary').is_visible()
                page.locator('.field').filter(has_text='When did this problem start?').get_by_role('button',name='Correct').click()
                page.wait_for_function("state.question_id === 'onset'")
                page.locator('#answer').fill('Yesterday');page.locator('#send').click()
                page.wait_for_function("state.question_id === 'review_confirmed' && !busy")
                page.locator('#choices').get_by_role('button',name='Yes',exact=True).click()
                page.wait_for_function("state.step === 'HANDOFF_READY'")
                with page.expect_download() as dl:page.locator('#download').click()
                assert dl.value.suggested_filename.startswith('handoff-')
                page.locator('#help').click();page.wait_for_function("state.step === 'HELP_NOW'")
                assert 'urgent medical help' in page.locator('#question').inner_text()
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                assert not errors,errors
                browser.close()
        finally:
            server.should_exit=True;thread.join(timeout=5);sock.close()
