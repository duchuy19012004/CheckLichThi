import re

with open('debug_output.html', encoding='utf-8') as f:
    html = f.read()

# Tim ham ShowExam
matches = re.findall(r'ShowExam.{0,500}', html, re.DOTALL)
for m in matches:
    print(m)
    print('---')

# Tim trong cac file JS duoc tham chieu
js_files = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', html)
print('JS files:')
for j in js_files:
    print(' ', j)
