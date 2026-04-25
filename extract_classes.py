import re

with open('templates/obras.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Encontrar todas as classes CSS
classes = re.findall(r'class="([^"]+)"', content)
# Extrair cada classe individual
all_classes = set()
for class_attr in classes:
    # Remover condições Jinja2 
    clean_attr = re.sub(r'{%.*?%}', '', class_attr)
    for cls in clean_attr.split():
        if cls and not cls.startswith('{') and not cls.startswith('}'):
            all_classes.add(cls)

print("Classes usadas no obras.html:")
for cls in sorted(all_classes):
    print(f"  {cls}")
