import os

def replace_api_url(directory):
    count = 0
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(('.tsx', '.ts', '.js', '.jsx')):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                if 'http://127.0.0.1:8000/' in content:
                    new_content = content.replace('http://127.0.0.1:8000/', '/api/')
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Updated {filepath}")
                    count += 1
    return count

if __name__ == "__main__":
    c1 = replace_api_url(r"d:\Admission-Pilot\frontend\src")
    c2 = replace_api_url(r"d:\Admission-Pilot\student-web\src")
    print(f"Total files updated: {c1 + c2}")
