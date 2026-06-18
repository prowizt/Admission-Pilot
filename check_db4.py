import chromadb
import sys
sys.stdout.reconfigure(encoding='utf-8')

client = chromadb.PersistentClient(path='./db')
col = client.get_collection('reference_db')
docs = col.get()['documents']
print("total docs in reference_db:", len(docs))
for i, d in enumerate(docs):
    if '치위생과' in d and '순수외국인' in d:
        print(f"Doc {i} contains both! len={len(d)}")
        print(d)

col2 = client.get_collection('rule_db')
docs2 = col2.get()['documents']
print("total docs in rule_db:", len(docs2))
for i, d in enumerate(docs2):
    if '치위생과' in d and '순수외국인' in d:
        print(f"Rule Doc {i} contains both! len={len(d)}")
        print(d[:500])
