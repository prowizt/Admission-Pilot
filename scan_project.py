import os
import re

# ==========================================
# Admission-Pilot 디렉터리 구조 생성
# ==========================================
EXCLUDE_DIRS = {
    'node_modules', '.venv', 'venv', '.git', 
    '__pycache__', 'dist', 'build', '.cursor', '.vscode', 'db' # db 폴더(ChromaDB) 추가 제외
}
OUTPUT_FILE = 'project_file_structure.txt'

def get_code_comment(file_path):
    """파일 확장자에 따라 최상단에 있는 한글 주석을 추출합니다."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ['.py', '.js', '.jsx', '.ts', '.tsx', '.sql', '.css', '.env']:
        return ""

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[:15]
            
            for line in lines:
                line = line.strip()
                if not line: continue
                
                clean_line = ""
                if line.startswith('#'): clean_line = line.lstrip('#').strip()
                elif line.startswith('//'): clean_line = line.lstrip('//').strip()
                elif line.startswith('--'): clean_line = line.lstrip('--').strip()
                elif line.startswith('/*'): clean_line = line.replace('/*', '').replace('*/', '').strip()
                
                # 한글이 포함되어 있으면 반환
                if clean_line and re.search(r'[ㄱ-ㅎㅏ-ㅣ가-힣]', clean_line):
                    return clean_line
    except Exception:
        pass
    return ""

def generate_tree(dir_path, prefix=""):
    """재귀적으로 폴더 구조를 트리 형태로 생성합니다."""
    tree_lines = []
    try:
        entries = sorted(os.listdir(dir_path))
    except PermissionError:
        return []

    entries = [e for e in entries if e not in EXCLUDE_DIRS]
    
    for i, entry in enumerate(entries):
        path = os.path.join(dir_path, entry)
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        
        if os.path.isfile(path):
            summary = get_code_comment(path)
            comment_str = f"  # {summary}" if summary else ""
            tree_lines.append(f"{prefix}{connector}{entry}{comment_str}")
        else:
            tree_lines.append(f"{prefix}{connector}{entry}/")
            new_prefix = prefix + ("    " if is_last else "│   ")
            tree_lines.extend(generate_tree(path, new_prefix))
            
    return tree_lines

def main():
    project_root = os.getcwd()
    print(f"🔍 [Admission-Pilot] 프로젝트 한글 주석 스캔 시작: {project_root}")
    
    tree = generate_tree(project_root)
    
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    output = [
        "=========================================",
        f" Admission-Pilot Structure Tree",
        f" Generated at: {now}",
        "=========================================",
        "."
    ]
    output.extend(tree)
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))
        
    print(f"✅ 추출 완료! '{OUTPUT_FILE}' 파일을 확인하세요.")

if __name__ == "__main__":
    main()