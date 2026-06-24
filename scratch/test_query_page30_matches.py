import chromadb
import sys
import re
sys.stdout.reconfigure(encoding='utf-8')
client = chromadb.PersistentClient(path="./backend/db")
col = client.get_collection("rule_db")
query = "2027학년도 모집요강 간호학부 대학교전형 수시1차 제출서류"
keywords = [k for k in query.split() if k]
res = col.query(query_texts=[query], n_results=60)

for i, dist in enumerate(res["distances"][0]):
    meta = res["metadatas"][0][i]
    doc_text = res["documents"][0][i]
    if meta.get("page_num") == 30:
        match_count = sum(1 for kw in keywords if kw in doc_text or kw in meta.get("filename", ""))
        print(f"Page 30 Original Dist: {dist:.4f}")
        print(f"Matches ({match_count}): {[kw for kw in keywords if kw in doc_text or kw in meta.get('filename', '')]}")
