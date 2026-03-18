import os
import sqlite3
import re

def parse_corpus_file(file_path):
    """解析语料文件，将每段完整语料拆分为独立条目"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    pattern = r'(\d+\.\d+\s+.*?)(?=\n\d+\.\d+|\Z)'
    corpus_items = re.findall(pattern, content, re.DOTALL)
    
    cleaned_items = []
    for item in corpus_items:
        item = re.sub(r'(\d+\.\d+)\s+', r'\1 ', item)
        item = ' '.join(item.split())
        cleaned_items.append(item)
    
    return cleaned_items

def import_corpus_to_db():
    corpus_root = "分词语料待校对"
    
    conn = sqlite3.connect('语料.db')
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS corpus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        file_name TEXT NOT NULL,
        original_text TEXT NOT NULL,
        edited_text TEXT,
        item_order INTEGER NOT NULL,
        FOREIGN KEY (book_id) REFERENCES books (id)
    )
    ''')
    
    for book_name in os.listdir(corpus_root):
        book_path = os.path.join(corpus_root, book_name)
        
        if os.path.isdir(book_path):
            print(f"处理书籍: {book_name}")
            cursor.execute("INSERT OR IGNORE INTO books (name) VALUES (?)", (book_name,))
            cursor.execute("SELECT id FROM books WHERE name = ?", (book_name,))
            book_id = cursor.fetchone()[0]
            
            for file_name in sorted(os.listdir(book_path)):
                if file_name.endswith('.txt'):
                    file_path = os.path.join(book_path, file_name)
                    print(f"  处理文件: {file_name}")
                    
                    corpus_items = parse_corpus_file(file_path)
                    
                    for order, item in enumerate(corpus_items, 1):
                        cursor.execute('''
                        INSERT INTO corpus (book_id, file_name, original_text, edited_text, item_order)
                        VALUES (?, ?, ?, ?, ?)
                        ''', (book_id, file_name, item, item, order))
    
    conn.commit()
    conn.close()
    print("语料数据导入完成！")

if __name__ == "__main__":
    import_corpus_to_db()
