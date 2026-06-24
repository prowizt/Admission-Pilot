import chromadb
client = chromadb.PersistentClient(path="./backend/db")
col = client.get_collection("rule_db")
res = col.get()
for i, doc in enumerate(res["documents"]):
    print(f"Document {i} length: {len(doc)} characters")
    meta = res["metadatas"][i]
    print(f"Title: {meta.get('title')} filename: {meta.get('filename')}")
