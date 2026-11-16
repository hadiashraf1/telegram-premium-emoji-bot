import tempfile, unittest
from pathlib import Path
from app import Bot, ApiError
from catalog import Catalog
from test_bot import FakeAPI, message

class TestInline(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Catalog(Path(self.tmp.name)/'db.sqlite')
        self.db.import_pack('Test','Heart 😀','Love',[{'custom_emoji_id':str(i),'emoji': '❤️' if i%2 else '😀'} for i in range(10,20)])
    def tearDown(self): self.tmp.cleanup()
    def test_offsets_and_pagination(self):
        api=FakeAPI(); bot=Bot(api,self.db,{1}); sid=bot.new_session(1,query='heart')
        for page,mid,method in [(0,None,'sendMessage'),(1,42,'editMessageText')]:
            bot.page(1,1,sid,page,mid); m,p=api.calls[-1]; self.assertEqual(m,method)
            self.assertEqual(len(p['entities']),8 if page==0 else 2)
            for e in p['entities']:
                a=e['offset']*2; b=a+e['length']*2
                self.assertEqual(p['text'].encode('utf-16-le')[a:b].decode('utf-16-le'), self.db.get(e['custom_emoji_id'])['emoji'])
            self.assertNotIn('پیش‌نمایش', str(p['reply_markup']))
    def test_rejected_no_fake_emoji(self):
        api=FakeAPI(); api.fail_preview=True; Bot(api,self.db,{1}).handle_message(message('/search heart'))
        p=api.calls[-1][1]; self.assertNotIn('entities',p); self.assertIn('تأیید نشد',p['text']); self.assertNotIn('❤️',p['text'])
    def test_stripped_entities_edit(self):
        class API(FakeAPI):
            def call(self,method,**kw):
                self.calls.append((method,kw)); return {'message_id':42,'entities':[]}
        api=API(); Bot(api,self.db,{1}).handle_message(message('/browse'))
        self.assertEqual(api.calls[-1][0],'editMessageText'); self.assertEqual(api.calls[-1][1]['message_id'],42); self.assertNotIn('entities',api.calls[-1][1])
