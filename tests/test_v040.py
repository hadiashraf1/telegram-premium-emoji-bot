import tempfile, unittest
from pathlib import Path
from app import Bot, ApiError
from catalog import Catalog, custom_ids
from seed import read_manifest, seed
from test_bot import FakeAPI, message

class TestV040(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Catalog(Path(self.tmp.name)/'db.sqlite'); self.api=FakeAPI(); self.bot=Bot(self.api,self.db,{1})
    def tearDown(self): self.tmp.cleanup()
    def test_alias(self):
        self.db.import_pack('Test','Love','General',[{'custom_emoji_id':'123','emoji':'❤️'}]); self.assertEqual(self.db.search('قلب')[1],1)
    def test_stats_packs(self):
        self.db.import_pack('Test','Love','General',[{'custom_emoji_id':'123','emoji':'❤️'}]); self.assertEqual(self.db.stats(),(1,1,1)); self.assertEqual(self.db.packs()[0][0],('test','Love',1))
    def test_preview_disabled(self):
        self.bot.handle_message(message('/start')); self.assertTrue(self.api.calls[-1][1]['link_preview_options']['is_disabled']); self.assertNotIn('https://t.me/addemoji/PackName',self.api.calls[-1][1]['text'])
    def test_sticker_id(self): self.assertEqual(custom_ids({'sticker':{'custom_emoji_id':'123'}}),['123'])
    def test_manifest(self):
        entries=list(read_manifest(Path(__file__).resolve().parents[1]/'seed-packs.txt')); self.assertEqual(len(entries),33); self.assertEqual(len({n.lower() for _,n in entries}),33)
    def test_seed(self):
        self.assertEqual(seed(self.api,self.db,[('Love','TestPack')],sleep=lambda _:None),(1,0)); self.assertEqual(self.db.stats(),(1,1,1))
    def test_seed_retry(self):
        class API(FakeAPI):
            def call(self, method, **kwargs):
                if not self.calls:
                    self.calls.append((method,kwargs)); raise ApiError(429,retry_after=2)
                return super().call(method,**kwargs)
        delays=[]; self.assertEqual(seed(API(),self.db,[('Love','TestPack')],sleep=delays.append),(1,0)); self.assertIn(2,delays)
    def test_packs_menu(self):
        self.bot.handle_message(message('/packs')); self.assertIn('پک',self.api.calls[-1][1]['text'])
