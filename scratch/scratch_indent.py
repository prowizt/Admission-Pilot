import sys

with open('backend/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.strip() == '# [라우터 전용 API 키 분리]':
        start_idx = i
    if start_idx != -1 and 'years = re.findall(r"\\b(202\\d)\\b", all_text)' in line and 'except Exception' in lines[i-5]:
        end_idx = i + 4
        break

if start_idx != -1 and end_idx != -1:
    for i in range(start_idx, end_idx + 1):
        lines[i] = '    ' + lines[i]
    with open('backend/main.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'Successfully indented lines {start_idx} to {end_idx}')
else:
    print('Failed to find block')
    print('start_idx:', start_idx, 'end_idx:', end_idx)
