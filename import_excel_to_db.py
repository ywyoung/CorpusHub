import sqlite3
import pandas as pd
import os

STUDENT_DATABASE = 'student_base.db'
EXCEL_FILE = 'student_base.xlsx'

def import_students_from_excel():
    """从Excel文件导入学生数据到SQLite数据库"""
    if not os.path.exists(EXCEL_FILE):
        print(f"错误：Excel文件 '{EXCEL_FILE}' 不存在")
        return False
    
    try:
        df = pd.read_excel(EXCEL_FILE)
        
        if '学号' not in df.columns or '姓名' not in df.columns:
            print("错误：Excel文件必须包含'学号'和'姓名'列")
            return False
        
        conn = sqlite3.connect(STUDENT_DATABASE)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL
            )
        ''')
        
        inserted_count = 0
        for index, row in df.iterrows():
            student_id = str(row['学号']).strip()
            name = str(row['姓名']).strip()
            
            if student_id and name:
                try:
                    cursor.execute('''
                        INSERT INTO students (student_id, name)
                        VALUES (?, ?)
                    ''', (student_id, name))
                    inserted_count += 1
                except sqlite3.IntegrityError:
                    print(f"跳过重复记录: 学号 {student_id} - {name}")
        
        conn.commit()
        conn.close()
        
        print(f"成功导入 {inserted_count} 条学生记录")
        return True
    
    except Exception as e:
        print(f"导入过程中出错: {str(e)}")
        return False

if __name__ == '__main__':
    if import_students_from_excel():
        print("学生数据导入成功")
    else:
        print("学生数据导入失败")
