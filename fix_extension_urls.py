import os

def replace_extension_urls():
    ext_dir = r"d:\Admission-Pilot\extension"
    
    # 1. Update sidepanel.js
    js_path = os.path.join(ext_dir, "sidepanel.js")
    with open(js_path, 'r', encoding='utf-8') as f:
        js_content = f.read()
    
    # Chrome 확장프로그램은 절대경로가 필요하므로 공인 IP 주소 할당
    js_content = js_content.replace('http://127.0.0.1:8000/', 'http://210.93.0.229:8080/api/')
    
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(js_content)
        
    # 2. Update manifest.json
    manifest_path = os.path.join(ext_dir, "manifest.json")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest_content = f.read()
        
    # 권한 허용 주소 업데이트
    manifest_content = manifest_content.replace('http://127.0.0.1:8000/*', 'http://210.93.0.229:8080/*')
    
    with open(manifest_path, 'w', encoding='utf-8') as f:
        f.write(manifest_content)

if __name__ == "__main__":
    replace_extension_urls()
    print("Extension URLs updated successfully!")
