#!/usr/bin/env python3
"""Собирает сайт (Docsify) из заметок в папку _site/. Запускается GitHub Actions при каждом push."""
import os, re, shutil, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, '_site')
SKIP = {'.git', '.github', '_site', 'tools', 'inbox', 'CLAUDE.md'}

def read(p):
    with open(p, encoding='utf-8') as f: return f.read()
def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f: f.write(s)

def strip_photos(t):
    return t.split('\n## Photos / Фото')[0].rstrip()
def photos(folder):
    return sorted(f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png')))
def fix_links(t):
    # ссылки на ru.md/en.md документа -> страница документа (папка)
    return re.sub(r'\]\(([^)\s]*?)/(?:ru|en)\.md\)', r'](\1/)', t)
def abs_links(t, reldir):
    def r(m):
        url = m.group(2)
        if re.match(r'^(https?:|/|#)', url): return m.group(0)
        return f'[{m.group(1)}](/' + os.path.normpath(os.path.join(reldir, url)).replace(os.sep, '/') + ('/' if url.endswith('/') else '') + ')'
    return re.sub(r'\[([^\]]*)\]\(([^)\s]+)\)', r, t)
def title_from(md_text, fallback):
    m = re.search(r'^#\s+(.+)$', md_text, re.M)
    return m.group(1).strip() if m else fallback
def pretty(kebab):
    return kebab.replace('-', ' ').title()
def body_wo_title(t):
    return re.sub(r'^#\s+.+\n?', '', t, count=1).strip()

shutil.rmtree(OUT, ignore_errors=True)
shutil.copytree(ROOT, OUT, ignore=lambda d, names: [n for n in names if n in SKIP])

pages = ['/']
doc_index = {}   # folder(rel) -> title

# 1) страницы документов: папки с ru.md/en.md
for dirpath, dirs, files in os.walk(OUT):
    dirs[:] = [d for d in dirs if d not in SKIP]
    if 'ru.md' in files or 'en.md' in files:
        rel = os.path.relpath(dirpath, OUT).replace(os.sep, '/')
        ru = strip_photos(read(os.path.join(dirpath, 'ru.md'))) if 'ru.md' in files else ''
        en = strip_photos(read(os.path.join(dirpath, 'en.md'))) if 'en.md' in files else ''
        name = pretty(os.path.basename(dirpath))
        parts = [f'# {name}\n']
        if ru: parts.append(fix_links(ru))
        if en:
            parts.append('\n<details><summary><b>Оригинал (English)</b></summary>\n\n' + fix_links(en) + '\n\n</details>')
        imgs = photos(dirpath)
        if imgs:
            parts.append('\n## Фото\n' + '\n'.join(f'![{i}]({i})' for i in imgs))
        write(os.path.join(dirpath, 'README.md'), '\n'.join(parts) + '\n')
        doc_index[rel] = name
        pages.append('/' + rel + '/')

# 2) страницы комнат
rooms = []
rdir = os.path.join(OUT, 'rooms')
for r in sorted(os.listdir(rdir)):
    p = os.path.join(rdir, r)
    if not os.path.isdir(p): continue
    sol = read(os.path.join(p, 'solutions.md')) if os.path.exists(os.path.join(p, 'solutions.md')) else ''
    oq = read(os.path.join(p, 'open-questions.md')) if os.path.exists(os.path.join(p, 'open-questions.md')) else ''
    name = re.sub(r'\s+—\s+решения$', '', title_from(sol, pretty(r))) if sol else pretty(r)
    out = [f'# {name}\n']
    open_items = re.findall(r'^- \[ \].*$', oq, re.M)
    if open_items: out.append(f'> ❓ Не решено: **{len(open_items)}**\n')
    out.append('## ✅ Решения\n' + (fix_links(body_wo_title(sol)) or '_Пока пусто._'))
    out.append('\n## ❓ Открытые вопросы\n' + (fix_links(body_wo_title(oq)) or '_Нет._'))
    for sub, label in (('docs', '📄 Документы'), ('books', '📚 Книги')):
        sp = os.path.join(p, sub)
        if os.path.isdir(sp):
            items = sorted(d for d in os.listdir(sp) if os.path.isdir(os.path.join(sp, d)))
            if items:
                out.append(f'\n## {label}\n' + '\n'.join(f'- [{pretty(d)}]({sub}/{d}/)' for d in items))
    write(os.path.join(p, 'README.md'), '\n'.join(out) + '\n')
    rooms.append((r, name, len(open_items)))
    pages.append(f'/rooms/{r}/')

# 3) «Что не решено» — все открытые вопросы (по исходным файлам)
todo = ['# ❓ Что не решено\n', '_Собрано автоматически из всех `open-questions.md` и других заметок с `- [ ]`._\n']
room_names = {k: n for k, n, _ in rooms}
for dirpath, dirs, files in os.walk(ROOT):
    dirs[:] = sorted(d for d in dirs if d not in SKIP)
    rel = os.path.relpath(dirpath, ROOT).replace(os.sep, '/')
    for f in sorted(files):
        if not f.endswith('.md') or f == 'en.md' or rel == '.': continue
        items = re.findall(r'^- \[ \].*$', read(os.path.join(dirpath, f)), re.M)
        if not items: continue
        if rel.startswith('rooms/') and rel.count('/') == 1:
            head, link = room_names.get(rel.split('/')[1], pretty(rel)), f'/{rel}/'
        elif f == 'ru.md':
            head, link = doc_index.get(rel, pretty(os.path.basename(rel))), f'/{rel}/'
        else:
            head, link = title_from(read(os.path.join(dirpath, f)), pretty(f[:-3])), f'/{rel}/{f}'
        todo.append(f'### [{head}]({link})\n' + fix_links(abs_links('\n'.join(items), rel)) + '\n')
write(os.path.join(OUT, 'todo.md'), '\n'.join(todo))
pages.append('/todo')

# 4) сайдбар
def section(prefix):
    return sorted((k, v) for k, v in doc_index.items() if k.startswith(prefix))
sb = ['- [🏠 Главная](/)', '- [❓ Что не решено](/todo)', '- [📜 Сюжет](/story/timeline.md)', '- 🧩 **Загадки**', '  - [Все загадки](/puzzles/README.md)']
for d in sorted(os.listdir(os.path.join(OUT, 'puzzles'))):
    p = os.path.join(OUT, 'puzzles', d)
    if os.path.isdir(p): sb.append(f'  - [{pretty(d)}](/puzzles/{d}/)')
    elif d.endswith('.md') and d != 'README.md': sb.append(f'  - [{pretty(d[:-3])}](/puzzles/{d})')
sb.append('- 🚪 **Комнаты**')
sb += [f'  - [{n}{" ❓" + str(c) if c else ""}](/rooms/{k}/)' for k, n, c in rooms]
sb.append('- 📄 **Документы (комната неизвестна)**')
seen = set()
for k, v in section('documents/'):
    top = k.split('/')[1]
    if top in seen: continue
    seen.add(top)
    sb.append(f'  - [{pretty(top)}](/documents/{top}/)')
    if not os.path.exists(os.path.join(OUT, 'documents', top, 'README.md')):
        pass
sb.append('- [🎓 Обучение](/tutorials/)')
write(os.path.join(OUT, '_sidebar.md'), '\n'.join(sb) + '\n')

# 5) главная страница для телефона (вместо README репозитория)
total_open = sum(c for _, _, c in rooms)
home = ['# Blue Prince — заметки\n',
        f'[❓ Что не решено](/todo) · [📜 Сюжет](/story/timeline.md) · [🧩 Загадки](/puzzles/README.md)\n',
        '> Поиск — в боковом меню (☰ внизу слева).\n',
        '## 🚪 Комнаты\n' + '\n'.join(f'- [{n}](/rooms/{k}/)' + (f' — ❓ {c}' if c else ' — ✅') for k, n, c in rooms),
        '\n## 📄 Документы без комнаты\n' + '\n'.join(sorted({f'- [{pretty(k.split("/")[1])}](/documents/{k.split("/")[1]}/)' for k in doc_index if k.startswith('documents/')}))]
readme = read(os.path.join(ROOT, 'README.md'))
m = re.search(r'## Игровой прогресс.*', readme, re.S)
if m: home.append('\n' + m.group(0).strip())
write(os.path.join(OUT, 'README.md'), '\n'.join(home) + '\n')

# папки-серии без своей страницы (documents/foreman-logs и т.п.) уже имеют README.md
write(os.path.join(OUT, 'search-paths.js'), 'window.SEARCH_PATHS = ' + json.dumps(sorted(set(pages))) + ';\n')
write(os.path.join(OUT, '.nojekyll'), '')
shutil.copy(os.path.join(ROOT, 'tools', 'index.html'), os.path.join(OUT, 'index.html'))
print(f'OK: {len(pages)} страниц, {len(rooms)} комнат')
