import chromadb
import sys
sys.stdout.reconfigure(encoding='utf-8')
client = chromadb.PersistentClient(path="./backend/db")
col = client.get_collection("rule_db")
res = col.get(where={"page_num": 30})
if res and res["metadatas"]:
    print(res["metadatas"][0])
