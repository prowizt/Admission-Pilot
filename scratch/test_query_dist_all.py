import chromadb
import sys
sys.stdout.reconfigure(encoding='utf-8')
client = chromadb.PersistentClient(path="./backend/db")
col = client.get_collection("rule_db")
res = col.query(query_texts=["2027학년도 모집요강 간호학부 대학교전형 수시1차 제출서류"], n_results=50)
for i, dist in enumerate(res["distances"][0]):
    meta = res["metadatas"][0][i]
    print(f"Rank {i+1}: Page {meta.get('page_num', '?')} (dist: {dist:.4f})")
