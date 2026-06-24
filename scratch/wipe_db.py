import chromadb
client = chromadb.PersistentClient(path="./backend/db")
for collection_name in ["rule_db", "reference_db"]:
    try:
        client.delete_collection(name=collection_name)
        print(f"Collection {collection_name} deleted.")
        client.create_collection(name=collection_name)
        print(f"Collection {collection_name} recreated.")
    except Exception as e:
        print(f"Error handling {collection_name}: {e}")
