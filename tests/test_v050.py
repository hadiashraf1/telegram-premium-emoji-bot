import tempfile, unittest
from pathlib import Path
from app import Bot, ApiError
from catalog import Catalog
from test_bot import FakeAPI, message

class PreviewAPI(FakeAPI):
    def __init__(self, fail=False, thumb=True):
        super().__init__(); self.fail=fail; self.thumb=thumb
    def call(self, method, **kwargs):
        if method=='sendSticker' and self.fail:
            self.calls.append((method,kwargs)); raise ApiError(400)
        if method=='getCustomEmojiStickers':
            self.calls.append((method,kwargs))
            row={'custom_emoji_id':kwargs['custom_emoji_ids'][0], 'file_id':'actual', 'emoji':'❤️', 'set_name':'TestPack'}
            if self.thumb: row['thumbnail']={'file_id':'thumb'}
            return [row]
        return super().call(method,**kwargs)
    def send_thumbnail(self, chat, file_id, caption, keyboard):
        self.calls.append(('thumbnail',{'chat':chat,'file_id':file_id,'caption':caption,'keyboard':keyboard})); return True

class TestV050(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Catalog(Path(self.tmp.name)/'db.sqlite')
        self.db.import_pack('TestPack','Hearts','Love',[{'custom_emoji_id':'123','emoji':'❤️','file_id':'actual'}])
    def tearDown(self): self.tmp.cleanup()
    def test_page_numbered(self):
        api=PreviewAPI(); bot=Bot(api,self.db,{1}); bot.handle_message(message('/search heart'))
        payload=api.calls[-1][1]; self.assertIn('1. ❤️',payload['text']); self.assertEqual(payload['entities'][0]['custom_emoji_id'],'123'); self.assertEqual(payload['reply_markup']['inline_keyboard'][0][0]['copy_text']['text'],'123')
    def test_preview_exact_file(self):
        api=PreviewAPI(); Bot(api,self.db,{1}).preview(1,'123'); self.assertEqual(api.calls[-1][0],'sendSticker'); self.assertEqual(api.calls[-1][1]['sticker'],'actual')
    def test_thumbnail_fallback(self):
        api=PreviewAPI(fail=True); Bot(api,self.db,{1}).preview(1,'123'); self.assertEqual(api.calls[-1][0],'thumbnail'); self.assertEqual(api.calls[-1][1]['file_id'],'thumb')
    def test_pack_fallback(self):
        api=PreviewAPI(fail=True,thumb=False); Bot(api,self.db,{1}).preview(1,'123'); self.assertEqual(api.calls[-1][0],'sendMessage'); self.assertIn('https://t.me/addemoji/testpack',str(api.calls[-1][1]))
    def test_preview_callback(self):
        api=PreviewAPI(); Bot(api,self.db,{1}).handle_callback({'id':'c','from':{'id':1},'message':{'chat':{'id':1,'type':'private'}},'data':'v:123'}); self.assertEqual([m for m,_ in api.calls],['answerCallbackQuery','sendSticker'])
    def test_no_download_on_search(self):
        api=PreviewAPI(); Bot(api,self.db,{1}).handle_message(message('/browse')); self.assertEqual([m for m,_ in api.calls],['sendMessage'])
