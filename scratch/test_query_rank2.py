import chromadb
client = chromadb.PersistentClient(path="./backend/db")
col = client.get_collection("rule_db")
res = col.query(query_texts=["제출서류"], n_results=30)
for i, dist in enumerate(res["distances"][0]):
    meta = res["metadatas"][0][i]
    print(f"Rank {i+1}: Page {meta.get('page_num', '?')} (dist: {dist:.4f})")
