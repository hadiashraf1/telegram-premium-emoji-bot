import os,sqlite3,tempfile,unittest
from harvest import state_connect,queue_candidate,insert_pack_data

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=state_connect(os.path.join(self.tmp.name,"state.db"))
        self.bank=os.path.join(self.tmp.name,"bank.db")
        with sqlite3.connect(self.bank) as db:
            db.execute("""CREATE TABLE emoji(
              id TEXT PRIMARY KEY,emoji TEXT NOT NULL,pack TEXT NOT NULL,title TEXT NOT NULL,
              category TEXT NOT NULL,file_id TEXT NOT NULL DEFAULT '',
              animated INTEGER NOT NULL DEFAULT 0,video INTEGER NOT NULL DEFAULT 0)""")
    def tearDown(self):
        self.state.close(); self.tmp.cleanup()
    def test_queue_dedupes_and_validates(self):
        self.assertTrue(queue_candidate(self.state,"Pack_One","title","q"))
        self.assertFalse(queue_candidate(self.state,"Pack_One","title","q2"))
        self.assertFalse(queue_candidate(self.state,"../bad","x","q"))
    def test_insert_is_idempotent(self):
        pack={"name":"Pack_One","title":"Pack One","stickers":[
          {"custom_emoji_id":"12345","emoji":"✨","file_id":"f1"},
          {"custom_emoji_id":"12345","emoji":"✨","file_id":"f1"},
          {"custom_emoji_id":"bad"}]}
        self.assertEqual(insert_pack_data(self.bank,pack),1)
        self.assertEqual(insert_pack_data(self.bank,pack),0)
    def test_existing_record_is_not_overwritten(self):
        with sqlite3.connect(self.bank) as db:
            db.execute("INSERT INTO emoji VALUES('12345','⭐','old','Old','oldcat','oldfile',0,0)")
        self.assertEqual(insert_pack_data(self.bank,{"name":"new","title":"New","stickers":[
          {"custom_emoji_id":"12345","emoji":"✨","file_id":"newfile"}]}),0)
        with sqlite3.connect(self.bank) as db:
            self.assertEqual(db.execute("SELECT pack,file_id FROM emoji WHERE id='12345'").fetchone(),("old","oldfile"))

if __name__=="__main__": unittest.main(verbosity=2)
