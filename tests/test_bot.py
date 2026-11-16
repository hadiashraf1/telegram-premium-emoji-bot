import tempfile
import unittest
from pathlib import Path
from catalog import Catalog, custom_ids, pack_name, utf16_length
from app import Bot, ApiError, html_code, copy_button

class FakeAPI:
    def __init__(self): self.calls=[]; self.fail_preview=False
    def call(self, method, **kwargs):
        self.calls.append((method,kwargs))
        if method=='getStickerSet': return {'name':'TestPack','title':'Test hearts','sticker_type':'custom_emoji','stickers':[{'custom_emoji_id':'123456','emoji':'❤️'}]}
        if method=='getCustomEmojiStickers': return [{'custom_emoji_id':kwargs['custom_emoji_ids'][0],'emoji':'😀','set_name':'TestPack'}]
        if method=='sendMessage' and 'entities' in kwargs and self.fail_preview: raise ApiError(400)
        return True

def message(text, uid=1, **kwargs):
    return {'chat':{'id':uid,'type':'private'},'from':{'id':uid},'text':text,**kwargs}

class TestCatalog(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'db.sqlite'; self.db=Catalog(self.path)
    def tearDown(self): self.tmp.cleanup()
    def test_pack(self): self.assertEqual(pack_name('https://t.me/addemoji/Test_1'),'Test_1')
    def test_invalid_pack(self):
        for value in ('https://evil.com/addemoji/Test','https://t.me/addstickers/Test','a/b',''):
            with self.assertRaises(ValueError): pack_name(value)
    def test_extract(self):
        e={'type':'custom_emoji','custom_emoji_id':'12345'}
        self.assertEqual(custom_ids({'entities':[e,e,{'type':'bold'}],'caption_entities':[{'type':'custom_emoji','custom_emoji_id':'6789'}]}),['12345','6789'])
    def test_utf16(self): self.assertEqual(utf16_length('😀'),2)
    def test_upsert(self):
        self.db.import_pack('Test','Heart','Love',[{'custom_emoji_id':'123','emoji':'❤️'}]); self.db.import_pack('Test','Heart','Love',[{'custom_emoji_id':'123','emoji':'😀'}]); self.assertEqual(self.db.get('123')['emoji'],'😀'); self.assertEqual(self.db.search()[1],1)
    def test_search_and_categories(self):
        self.db.import_pack('Test','Heart','Love',[{'custom_emoji_id':'123','emoji':'❤️'}]); self.assertEqual(self.db.search('heart')[1],1); self.assertEqual(self.db.search(category='Love')[1],1); self.assertEqual(self.db.categories(),[('Love',1)]); self.assertEqual(self.db.search("' OR 1=1 --")[1],0)
    def test_paging(self):
        self.db.import_pack('Test','Heart','Love',[{'custom_emoji_id':str(i),'emoji':'😀'} for i in range(1,20)]); rows,total,page=self.db.search(page=999); self.assertEqual((len(rows),total,page),(3,19,2))
    def test_persistence(self):
        self.db.import_pack('Test','Heart','Love',[{'custom_emoji_id':'123','emoji':'❤️'}]); self.assertIsNotNone(Catalog(self.path).get('123'))
    def test_noncustom_ignored(self): self.assertEqual(self.db.import_pack('Test','Heart','Love',[{'file_id':'abc'}]),0)

class TestBot(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Catalog(Path(self.tmp.name)/"db.sqlite"); self.api=FakeAPI(); self.bot=Bot(self.api,self.db,{1})
    def tearDown(self): self.tmp.cleanup()
    def test_import_admin(self): self.bot.handle_message(message('/import Love | TestPack')); self.assertEqual(self.db.search()[1],1)
    def test_import_denied(self): self.bot.handle_message(message('/import Love | TestPack',uid=2)); self.assertEqual(self.db.search()[1],0); self.assertFalse(any(m=='getStickerSet' for m,_ in self.api.calls))
    def test_copy(self): self.assertEqual(copy_button('Copy','123')['copy_text']['text'],'123'); self.assertEqual(html_code('123','&'),'<tg-emoji emoji-id="123">&amp;</tg-emoji>')
    def test_preview_fallback(self): self.api.fail_preview=True; self.bot.detail(1,'123'); self.assertEqual(self.api.calls[-1][0],'sendMessage'); self.assertNotIn('entities',self.api.calls[-1][1])
    def test_private_only(self): self.bot.handle_message({'chat':{'id':1,'type':'group'},'text':'/start'}); self.assertEqual(self.api.calls,[])
    def test_browse(self): self.bot.handle_message(message('/browse')); self.assertIn('0',self.api.calls[-1][1]['text'])
    def test_extraction_message(self): self.bot.handle_message(message('😀',entities=[{'type':'custom_emoji','custom_emoji_id':'123'}])); self.assertIn('123',self.api.calls[-1][1]['text'])
    def test_session_owner(self): sid=self.bot.new_session(1); self.bot.page(2,2,sid); self.assertEqual(self.api.calls,[])

if __name__=='__main__': unittest.main()
