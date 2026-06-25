import chromadb
import traceback

try:
    client = chromadb.PersistentClient(path='./backend/db')
    col = client.get_collection('rule_db')
    where = {
        '$and': [
            {'year': {'$in': ['2027', 'ALL']}},
            {'filename': {'$in': ['2027학년도 요강.pdf']}}
        ]
    }
    res = col.get(where=where)
    print("Success, found:", len(res['ids']))
except Exception as e:
    print("Error:")
    traceback.print_exc()
