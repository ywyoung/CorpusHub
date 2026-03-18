from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3
import os
import re
import tempfile
import docx
import jieba
import datetime
from difflib import Differ
import ast
import thulac
from collections import Counter
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import base64
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
DATABASE = '语料.db'
STUDENT_DATABASE = 'student_base.db'  
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = 'admin123'


def init_student_db():
    conn = sqlite3.connect(STUDENT_DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            author TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    book_columns = [row[1] for row in cursor.execute("PRAGMA table_info(books)").fetchall()]
    if 'author' not in book_columns:
        cursor.execute("ALTER TABLE books ADD COLUMN author TEXT")
    if 'created_at' not in book_columns:
        cursor.execute("ALTER TABLE books ADD COLUMN created_at TEXT")
        cursor.execute("UPDATE books SET created_at = datetime('now') WHERE created_at IS NULL")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS corpus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            edited_text TEXT,
            file_name TEXT,
            item_order INTEGER,
            FOREIGN KEY (book_id) REFERENCES books (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proofreading_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_name TEXT NOT NULL,
            author TEXT,
            original_text TEXT NOT NULL,
            analyzed_text TEXT NOT NULL,
            issues TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    pr_cols = [row[1] for row in cursor.execute("PRAGMA table_info(proofreading_results)").fetchall()]
    if 'corrected_text' not in pr_cols:
        cursor.execute("ALTER TABLE proofreading_results ADD COLUMN corrected_text TEXT")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS proofreading_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            corpus_id INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            edited_text TEXT NOT NULL,
            edited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user TEXT,
            FOREIGN KEY (book_id) REFERENCES books (id),
            FOREIGN KEY (corpus_id) REFERENCES corpus (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            corpus_id INTEGER NOT NULL,
            student_id TEXT NOT NULL,
            username TEXT,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(corpus_id, student_id),
            FOREIGN KEY (book_id) REFERENCES books (id),
            FOREIGN KEY (corpus_id) REFERENCES corpus (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            corpus_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            admin_username TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (book_id) REFERENCES books (id),
            FOREIGN KEY (corpus_id) REFERENCES corpus (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pos_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            corpus_id INTEGER NOT NULL UNIQUE,
            content TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user TEXT,
            FOREIGN KEY (book_id) REFERENCES books (id),
            FOREIGN KEY (corpus_id) REFERENCES corpus (id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS 用户 (
            用户id INTEGER PRIMARY KEY AUTOINCREMENT,
            学号 TEXT,
            姓名 TEXT,
            用户名 TEXT UNIQUE,
            密码 TEXT,
            角色 TEXT DEFAULT '学生'
        )
    ''')
    
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(用户)").fetchall()]
    if '角色' not in columns:
        cursor.execute("ALTER TABLE 用户 ADD COLUMN 角色 TEXT DEFAULT '学生'")
    
    admin_exists = cursor.execute("SELECT 1 FROM 用户 WHERE 角色 = '管理员' LIMIT 1").fetchone()
    if not admin_exists:
        cursor.execute('''
            INSERT INTO 用户 (学号, 姓名, 用户名, 密码, 角色)
            VALUES (?, ?, ?, ?, ?)
        ''', ('000000', '管理员', DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, '管理员'))
    
    conn.commit()
    conn.close()

init_student_db()
init_db()

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_student_db_connection():
    conn = sqlite3.connect(STUDENT_DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_students():
    conn = get_student_db_connection()
    students = conn.execute('SELECT student_id, name FROM students ORDER BY student_id').fetchall()
    conn.close()
    return [dict(s) for s in students]

def import_students_from_excel_file(file_storage):
    try:
        import pandas as pd
    except Exception:
        return False, '服务器未安装Excel解析依赖，请安装pandas后重试'
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            file_storage.save(tmp.name)
            df = pd.read_excel(tmp.name)
        os.unlink(tmp.name)
        if '学号' not in df.columns or '姓名' not in df.columns:
            return False, "Excel文件表头必须包含'学号'与'姓名'"
        conn = get_student_db_connection()
        cursor = conn.cursor()
        inserted = 0
        for _, row in df.iterrows():
            sid = str(row['学号']).strip()
            name = str(row['姓名']).strip()
            if sid and name:
                try:
                    cursor.execute('INSERT INTO students (student_id, name) VALUES (?, ?)', (sid, name))
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
        conn.commit()
        conn.close()
        return True, f'成功导入 {inserted} 条学生记录'
    except Exception as e:
        return False, str(e)

def compute_corpus_lengths(book_id):
    conn = get_db_connection()
    rows = conn.execute('SELECT id, original_text FROM corpus WHERE book_id = ?', (book_id,)).fetchall()
    conn.close()
    items = []
    for r in rows:
        text = r['original_text'] or ''
        length = len(text.encode('utf-8'))
        items.append({'corpus_id': r['id'], 'length': length})
    return items

def get_existing_assignments(book_id):
    conn = get_db_connection()
    rows = conn.execute('SELECT corpus_id, student_id FROM assignments WHERE book_id = ?', (book_id,)).fetchall()
    conn.close()
    return {(row['corpus_id'], row['student_id']) for row in rows}

def assign_tasks_balanced(book_id, student_ids):
    items = compute_corpus_lengths(book_id)
    existing = get_existing_assignments(book_id)
    items = [it for it in items if all((it['corpus_id'], sid) not in existing for sid in student_ids)]
    items.sort(key=lambda x: x['length'], reverse=True)
    load = {sid: 0 for sid in student_ids}
    plan = []
    for it in items:
        target = min(load.items(), key=lambda kv: kv[1])[0]
        plan.append((it['corpus_id'], target))
        load[target] += it['length']
    if not plan:
        return 0
    conn = get_db_connection()
    cursor = conn.cursor()
    for corpus_id, sid in plan:
        cursor.execute('INSERT OR IGNORE INTO assignments (book_id, corpus_id, student_id) VALUES (?, ?, ?)', (book_id, corpus_id, sid))
    conn.commit()
    conn.close()
    return len(plan)

def ensure_admin_fields():
    conn = get_db_connection()
    cursor = conn.cursor()
    columns = [row[1] for row in cursor.execute("PRAGMA table_info(corpus)").fetchall()]
    if 'admin_remark' not in columns:
        cursor.execute("ALTER TABLE corpus ADD COLUMN admin_remark TEXT")
    if 'admin_modified' not in columns:
        cursor.execute("ALTER TABLE corpus ADD COLUMN admin_modified INTEGER DEFAULT 0")
    if 'admin_modified_by' not in columns:
        cursor.execute("ALTER TABLE corpus ADD COLUMN admin_modified_by TEXT")
    if 'admin_modified_at' not in columns:
        cursor.execute("ALTER TABLE corpus ADD COLUMN admin_modified_at TIMESTAMP")
    conn.commit()
    conn.close()

ensure_admin_fields()

def get_latest_student_submissions():
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT h.id as history_id, h.book_id, h.corpus_id, h.original_text, h.edited_text, h.edited_at, h.user,
               b.name AS book_name, c.file_name, c.item_order,
               c.admin_remark, c.admin_modified, c.admin_modified_by, c.admin_modified_at
        FROM proofreading_history h
        JOIN (
            SELECT MAX(id) AS max_id
            FROM proofreading_history
            GROUP BY corpus_id
        ) latest ON latest.max_id = h.id
        JOIN books b ON b.id = h.book_id
        JOIN corpus c ON c.id = h.corpus_id
        ORDER BY h.edited_at DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def _map_pos_tag(tag):
    t = tag.lower() if tag else ''
    if t in {'n', 'nr', 'ns', 'nt', 'nz'}:
        return 'N'
    if t in {'v', 'vi', 'vn', 'vd'}:
        return 'V'
    if t in {'a', 'ad', 'an', 'ag'}:
        return 'ADJ'
    if t in {'d'}:
        return 'ADV'
    if t in {'r', 'rr', 'rz', 'rzt'}:
        return 'PRON'
    if t in {'p'}:
        return 'PREP'
    if t in {'c'}:
        return 'CONJ'
    if t in {'m', 'mq'}:
        return 'NUM'
    if t in {'u'}:
        return 'AUX'
    if t in {'w'}:
        return 'PUNC'
    return 'OTHER'

def pos_tag_text(text):
    tokens = []
    try:
        from ltp import LTP
        ltp = LTP()
        seg, hidden = ltp.seg([text])
        pos = ltp.pos(hidden)
        words = seg[0] if seg else []
        tags = pos[0] if pos else []
        for w, t in zip(words, tags):
            tokens.append({'word': w, 'tag': _map_pos_tag(t)})
        if tokens:
            return tokens
    except Exception:
        pass
    try:
        thu = thulac.thulac()
        result = thu.cut(text)
        for w, t in result:
            tokens.append({'word': w, 'tag': _map_pos_tag(t)})
        if tokens:
            return tokens
    except Exception:
        pass
    try:
        import jieba.posseg as pseg
        words = pseg.cut(text)
        for item in words:
            tokens.append({'word': item.word, 'tag': _map_pos_tag(item.flag)})
    except Exception:
        pass
    return tokens

def get_pos_tags_for_corpus(corpus_id):
    conn = get_db_connection()
    row = conn.execute('SELECT content FROM pos_tags WHERE corpus_id = ?', (corpus_id,)).fetchone()
    conn.close()
    if not row or not row['content']:
        return None
    try:
        return ast.literal_eval(row['content'])
    except Exception:
        return None

@app.route('/pos_tag', methods=["POST"])
def pos_tag():
    if 'username' not in session:
        return jsonify(success=False, message='请先登录')
    text = request.form.get('text', '')
    corpus_id = request.form.get('corpus_id')
    if not text:
        return jsonify(success=False, message='文本为空')
    tokens = pos_tag_text(text)
    return jsonify(success=True, tokens=tokens)

@app.route('/save_pos_tags', methods=["POST"])
def save_pos_tags():
    if 'username' not in session:
        return jsonify(success=False, message='请先登录')
    corpus_id = request.form.get('corpus_id')
    book_id = request.form.get('book_id')
    content = request.form.get('content')
    if not corpus_id or not book_id or not content:
        return jsonify(success=False, message='缺少参数')
    try:
        tokens = ast.literal_eval(content)
    except Exception:
        tokens = None
    if tokens is None:
        return jsonify(success=False, message='标注内容格式错误')
    conn = get_db_connection()
    row = conn.execute('SELECT id FROM pos_tags WHERE corpus_id = ?', (corpus_id,)).fetchone()
    if row:
        conn.execute('UPDATE pos_tags SET content = ?, updated_at = CURRENT_TIMESTAMP, user = ? WHERE corpus_id = ?', (str(tokens), session['username'], corpus_id))
    else:
        conn.execute('INSERT INTO pos_tags (book_id, corpus_id, content, user) VALUES (?, ?, ?, ?)', (book_id, corpus_id, str(tokens), session['username']))
    conn.commit()
    conn.close()
    return jsonify(success=True, message='标注已保存')

def get_my_tasks(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 学号 FROM 用户 WHERE 用户名 = ?", (username,))
    row = cursor.fetchone()
    student_id = row['学号'] if row else None
    tasks = []
    if student_id:
        tasks = conn.execute('''
            SELECT a.book_id, a.corpus_id, b.name AS book_name, c.file_name, c.item_order,
                   c.original_text, c.edited_text,
                   c.admin_remark, c.admin_modified, c.admin_modified_by, c.admin_modified_at,
                   EXISTS(SELECT 1 FROM proofreading_history h WHERE h.corpus_id = a.corpus_id AND h.user = ?) AS edited_by_me
            FROM assignments a
            JOIN books b ON b.id = a.book_id
            JOIN corpus c ON c.id = a.corpus_id
            WHERE a.student_id = ?
            ORDER BY b.name, c.file_name, c.item_order
        ''', (username, student_id)).fetchall()
    conn.close()
    return [dict(t) for t in tasks]

def get_books():
    conn = get_db_connection()
    books = conn.execute('SELECT * FROM books').fetchall()
    
    books_with_progress = []
    for book in books:
        corpus_count = conn.execute('SELECT COUNT(*) FROM corpus WHERE book_id = ?', 
                                  (book['id'],)).fetchone()[0]
        edited_count = conn.execute('SELECT COUNT(*) FROM corpus WHERE book_id = ? AND edited_text IS NOT NULL', 
                                  (book['id'],)).fetchone()[0]
        progress = round((edited_count / corpus_count * 100), 1) if corpus_count > 0 else 0
        book_dict = dict(book)
        book_dict['progress'] = progress
        books_with_progress.append(book_dict)
    
    conn.close()
    return books_with_progress

def get_corpus_list(book_id):
    conn = get_db_connection()
    corpus = conn.execute('''
        SELECT id, original_text, edited_text, file_name, item_order 
        FROM corpus 
        WHERE book_id = ?
        ORDER BY file_name, item_order
    ''', (book_id,)).fetchall()
    conn.close()
    return corpus

def update_corpus(corpus_id, edited_text, original_text, user):
    conn = get_db_connection()
    conn.execute('''
        UPDATE corpus 
        SET edited_text = ?
        WHERE id = ?
    ''', (edited_text, corpus_id))

    conn.execute('''
        INSERT INTO proofreading_history 
        (book_id, corpus_id, original_text, edited_text, user)
        SELECT c.book_id, c.id, ?, ?, ?
        FROM corpus c
        WHERE c.id = ?
    ''', (original_text, edited_text, user, corpus_id))
    
    conn.commit()
    conn.close()

def split_text_into_sentences(text):
    sentences = re.split(r'(?<=[，。！？!?；:：])\s*|\n\s*\n', text)
    
    refined_sentences = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue

        if re.search(r'[，。！？!?；:：]$', s):
            refined_sentences.append(s)
        else:
            parts = re.split(r'([，。！？!?；:：])', s)
            if len(parts) > 1:
                buffer = ""
                for part in parts:
                    if part and part in "，。！？!?；:：":
                        buffer += part
                        if buffer.strip():
                            refined_sentences.append(buffer.strip())
                        buffer = ""
                    else:
                        buffer += part
                if buffer.strip():
                    refined_sentences.append(buffer.strip())
            else:
                refined_sentences.append(s)
    
    return [s for s in refined_sentences if s.strip()]

def extract_pdf_text(file):
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return None, '缺少依赖，请先安装 PyPDF2'
    data = file.read()
    reader = PdfReader(BytesIO(data))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text:
            text += page_text + "\n"
    if not text.strip():
        return None, '未能从PDF中提取到文本'
    return text, None

def extract_docx_text(temp_path):
    try:
        doc = docx.Document(temp_path)
        text = '\n'.join([para.text for para in doc.paragraphs])
        return text, None
    except Exception as e:
        return None, f'DOCX解析失败: {str(e)}'

def extract_doc_text(temp_path):
    try:
        import win32com.client
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        doc = word.Documents.Open(temp_path)
        temp_txt = temp_path + ".txt"
        doc.SaveAs(temp_txt, FileFormat=win32com.client.constants.wdFormatText)
        doc.Close()
        word.Quit()
        with open(temp_txt, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        try:
            os.remove(temp_txt)
        except Exception:
            pass
        return content, None
    except Exception as e:
        return None, f'DOC解析失败，可能缺少系统Word组件: {str(e)}'

def extract_uploaded_text(file):
    filename = file.filename
    if '.' not in filename:
        return None, '文件缺少扩展名'
    ext = filename.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        return extract_pdf_text(file)
    elif ext == 'txt':
        try:
            return file.read().decode('utf-8'), None
        except Exception:
            return None, 'TXT文件必须为UTF-8编码'
    elif ext in ['doc', 'docx']:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name
        try:
            if ext == 'docx':
                text, err = extract_docx_text(temp_path)
            else:
                text, err = extract_doc_text(temp_path)
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        if err:
            return None, err
        return text, None
    else:
        return None, '仅支持PDF、DOC、DOCX或TXT文件'

def sanitize_filename(name):
    return re.sub(r'[\\/:*?"<>|]+', '_', name).strip()

def save_sentences_chunks(sentences, base_name, original_text):
    project_root = os.path.dirname(os.path.abspath(__file__))
    temp_dir = os.path.join(project_root, "temp")
    os.makedirs(temp_dir, exist_ok=True)
    base_txt_path = os.path.join(temp_dir, f"{base_name}.txt")
    with open(base_txt_path, 'w', encoding='utf-8') as f:
        f.write(original_text)
    target_root = os.path.join(project_root, "分词语料待校对")
    os.makedirs(target_root, exist_ok=True)
    output_dir = os.path.join(target_root, base_name)
    os.makedirs(output_dir, exist_ok=True)
    chunk_size = 100
    file_count = 0
    for i in range(0, len(sentences), chunk_size):
        chunk = sentences[i:i+chunk_size]
        file_count += 1
        chunk_path = os.path.join(output_dir, f"{file_count}.txt")
        with open(chunk_path, 'w', encoding='utf-8') as f:
            for idx, s in enumerate(chunk, 1):
                tokens = jieba.lcut(s.strip())
                numbered = f"{file_count}.{idx}  " + '  '.join(tokens)
                f.write(numbered + "\n")
    return output_dir, file_count, base_txt_path

def import_generated_book_to_db(base_name, author, output_dir):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO books (name, author, created_at) VALUES (?, ?, datetime('now'))", (base_name, author))
    cursor.execute("SELECT id FROM books WHERE name = ? ORDER BY id DESC LIMIT 1", (base_name,))
    row = cursor.fetchone()
    book_id = row['id'] if isinstance(row, sqlite3.Row) else row[0]
    for file_name in sorted(os.listdir(output_dir), key=lambda x: int(os.path.splitext(x)[0]) if x.split('.')[0].isdigit() else x):
        if not file_name.endswith('.txt'):
            continue
        file_path = os.path.join(output_dir, file_name)
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        for order, line in enumerate(lines, 1):
            cursor.execute('''
                INSERT INTO corpus (book_id, original_text, edited_text, file_name, item_order)
                VALUES (?, ?, ?, ?, ?)
            ''', (book_id, line, line, file_name, order))
    conn.commit()
    conn.close()
    return book_id
