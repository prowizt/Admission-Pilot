import chromadb
import sys
import re
sys.stdout.reconfigure(encoding='utf-8')
client = chromadb.PersistentClient(path="./backend/db")
col = client.get_collection("rule_db")
query = "2027학년도 모집요강 간호학부 대학교전형 수시1차 제출서류"
keywords = [k for k in query.split() if k]
res = col.query(query_texts=[query], n_results=60)

docs_map = []
for i, dist in enumerate(res["distances"][0]):
    meta = res["metadatas"][0][i]
    doc_text = res["documents"][0][i]
    
    # 1. 원본 거리
    final_dist = dist
    
    # 2. 키워드 매칭 보너스 계산 (단어 단위)
    match_count = 0
    for kw in keywords:
        if kw in doc_text or kw in meta.get("filename", ""):
            match_count += 1
            
    # 3. 보너스 적용 (일치하는 키워드 1개당 거리를 대폭 낮춰줌)
    # distance는 낮을수록 좋음 (0에 가까울수록). 
    # match_count가 많을수록 거리를 0.1씩 뺌
    final_dist = max(0.01, final_dist - (match_count * 0.15))
    
    docs_map.append({
        "page_num": meta.get('page_num', '?'),
        "dist": dist,
        "final_dist": final_dist,
        "match_count": match_count
    })

# 정렬
sorted_docs = sorted(docs_map, key=lambda x: x["final_dist"])

for i, d in enumerate(sorted_docs[:15]):
    print(f"Rank {i+1}: Page {d['page_num']} (Final Dist: {d['final_dist']:.4f}, Original: {d['dist']:.4f}, Matches: {d['match_count']})")
