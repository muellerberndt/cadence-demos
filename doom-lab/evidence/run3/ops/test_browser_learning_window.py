import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from . import browser_learning_window as window


class Context:
    def __init__(self, value): self.value=value
    async def __aenter__(self): return self.value
    async def __aexit__(self, *_): pass


class Session:
    def __init__(self, state):self.state=state;self.sent=[]
    def get(self, url): return Context(self)
    def raise_for_status(self):pass
    async def json(self):return copy.deepcopy(self.state)
    def ws_connect(self, url):return Context(self)
    async def send_json(self, message):
        self.sent.append(message)
        if message['type']=='learning':self.state['learning']['enabled']=message['enabled']
        if message['type']=='mode':self.state['mode']=message['mode']


class WindowTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, *, model='selected', error=None):
        state={'model':{'id':model},'learning':{'enabled':True,'error':error},'mode':'student','episode':2}
        session=Session(state)
        with tempfile.TemporaryDirectory() as directory:
            args=SimpleNamespace(seconds=.01,out=Path(directory)/'window',model='selected',url='http://127.0.0.1:8667')
            with patch.object(window.aiohttp,'ClientSession',return_value=Context(session)):
                await window.monitor(args)
            receipt=json.loads((args.out/'status.json').read_text())
        return session,receipt

    async def test_deadline_disables_learning_and_pauses_only_selected_model(self):
        session,receipt=await self.exercise()
        self.assertEqual(session.sent,[{'type':'learning','enabled':False},{'type':'mode','mode':'idle'}])
        self.assertEqual(receipt['state'],'paused')
        self.assertEqual(receipt['pause_reason'],'deadline')

    async def test_another_model_is_never_controlled(self):
        session,receipt=await self.exercise(model='user_selected_other')
        self.assertEqual(session.sent,[])
        self.assertEqual(receipt['state'],'model_changed_by_another_controller')

    async def test_learner_error_stops_collection_before_deadline(self):
        session,receipt=await self.exercise(error='explicit refusal')
        self.assertEqual(receipt['pause_reason'],'learner_error')
        self.assertFalse(session.state['learning']['enabled'])


if __name__=='__main__':unittest.main()
