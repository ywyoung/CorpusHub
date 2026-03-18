@app.route("/registpage")
def registpage():
    return render_template("register.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        xh = request.form["student_id"]
        xm = request.form["name"]
        username = request.form["username"]
        password = request.form["password"]
  
        conn_student = get_student_db_connection()
        cursor_student = conn_student.cursor()
        cursor_student.execute("SELECT * FROM students WHERE student_id = ? AND name = ?", (xh, xm))
        student = cursor_student.fetchone()
        conn_student.close()
        
        if not student:
            flash("非允许用户，不能注册", "error")
            return render_template("register.html")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM 用户 WHERE 学号 = ?", (xh,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            flash(f"你已经注册过，用户名是{existing_user['用户名']}", "info")
            conn.close()
            return render_template("login.html")
        
        cursor.execute("SELECT * FROM 用户 WHERE 用户名 = ?", (username,))
        if cursor.fetchone():
            flash(f"用户名 {username} 已经被别人注册过", "error")
            conn.close()
            return render_template("register.html")
        
        cursor.execute('''
            INSERT INTO 用户 (学号, 姓名, 用户名, 密码, 角色) 
            VALUES (?, ?, ?, ?, ?)
        ''', (xh, xm, username, password, '学生'))
        conn.commit()
        conn.close()
        
        flash("注册成功，请登录", "success")
        return redirect(url_for("loginpage"))
    
    return render_template("register.html")

@app.route("/loginpage")
def loginpage():
    return render_template("login.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM 用户 WHERE 用户名 = ? AND 密码 = ?", (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session['username'] = username
            session['role'] = user['角色'] if '角色' in user.keys() else '学生'
            return redirect(url_for('dashboard'))
        else:
            flash("用户名或密码错误", "error")
            return render_template("login.html", username=username or "", password=password or "")
    
    return render_template("login.html", username="", password="")

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))  

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    books = get_books()
    return render_template('dashboard.html', books=books, active_page='bookshelf', content=None)

@app.route('/bookshelf')
def bookshelf():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    books = get_books()
    return render_template('dashboard.html', books=books, active_page='bookshelf', content=render_template('bookshelf.html', books=books))

@app.route('/book/<int:book_id>')
def book_page(book_id):
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    
    if not book:
        conn.close()
        return redirect(url_for('dashboard'))
    
    last_position_key = f'last_position_{book_id}'
    last_position = session.get(last_position_key)
    
    if last_position:
        corpus_exists = conn.execute('SELECT id FROM corpus WHERE id = ? AND book_id = ?', 
                                   (last_position, book_id)).fetchone()
        if corpus_exists:
            conn.close()
            return redirect(url_for('edit_corpus', book_id=book_id, corpus_id=last_position))
    
    first_corpus = conn.execute('''
        SELECT id FROM corpus 
        WHERE book_id = ?
        ORDER BY file_name, item_order
        LIMIT 1
    ''', (book_id,)).fetchone()
    conn.close()
    
    if first_corpus:
        return redirect(url_for('edit_corpus', book_id=book_id, corpus_id=first_corpus['id']))
    
    books = get_books()
    return render_template('dashboard.html', books=books, content=render_template('no_corpus.html', book_name=book['name']))

@app.route('/book/<int:book_id>/<int:corpus_id>', methods=["GET", "POST"])
def edit_corpus(book_id, corpus_id):
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    conn = get_db_connection()
    book = conn.execute('SELECT * FROM books WHERE id = ?', (book_id,)).fetchone()
    
    if not book:
        conn.close()
        return redirect(url_for('dashboard'))
    
    current_corpus = conn.execute('''
        SELECT id, original_text, edited_text, file_name, item_order,
               admin_remark, admin_modified, admin_modified_by, admin_modified_at
        FROM corpus 
        WHERE id = ?
    ''', (corpus_id,)).fetchone()
    
    if not current_corpus:
        conn.close()
        return redirect(url_for('book_page', book_id=book_id))
    
    corpus = conn.execute('''
        SELECT id 
        FROM corpus 
        WHERE book_id = ? 
        ORDER BY file_name, item_order
    ''', (book_id,)).fetchall()
    corpus_ids = [row['id'] for row in corpus]
    
    file_corpus_count = conn.execute('''
        SELECT COUNT(*) 
        FROM corpus 
        WHERE book_id = ? 
        AND file_name = ?
    ''', (book_id, current_corpus['file_name'])).fetchone()[0]
    
    file_corpus_position = conn.execute('''
        SELECT COUNT(*) 
        FROM corpus 
        WHERE book_id = ? 
        AND file_name = ?
        AND item_order <= ?
    ''', (book_id, current_corpus['file_name'], current_corpus['item_order'])).fetchone()[0]
    
    conn.close()
    
    segmented_text = ' '.join(jieba.cut(current_corpus['original_text']))
    
    try:
        thu = thulac.thulac(seg_only=True)
        thu_result = thu.cut(current_corpus['original_text'], text=True)
        thulac_text = thu_result.replace('\n', ' ').replace('\t', ' ')
    except Exception as e:
        thulac_text = None
    
    seg3_text = None
    try:
        from ltp import LTP
        ltp = LTP()
        seg, _ = ltp.seg([current_corpus['original_text']])
        words = seg[0] if seg and len(seg) > 0 else []
        seg3_text = ' '.join(words)
    except Exception:
        try:
            import pkuseg
            seg = pkuseg.pkuseg()
            words = seg.cut(current_corpus['original_text'])
            seg3_text = ' '.join(words)
        except Exception:
            try:
                from snownlp import SnowNLP
                s = SnowNLP(current_corpus['original_text'])
                words = s.words
                seg3_text = ' '.join(words)
            except Exception:
                seg3_text = None
    
    if request.method == 'POST':
        edited_text = request.form.get('edited_text', '')
        user = session.get('username', '未知用户')
        update_corpus(corpus_id, edited_text, current_corpus['original_text'], user)
        session[f'last_position_{book_id}'] = corpus_id
    
    try:
        current_index = corpus_ids.index(corpus_id)
        next_index = (current_index + 1) % len(corpus_ids)
        prev_index = (current_index - 1) % len(corpus_ids)
        
        next_corpus_id = corpus_ids[next_index]
        prev_corpus_id = corpus_ids[prev_index]
    except (ValueError, IndexError):
        next_corpus_id = corpus_ids[0] if corpus_ids else 0
        prev_corpus_id = corpus_ids[0] if corpus_ids else 0
    
    books = get_books()
    return render_template('dashboard.html', 
                           books=books,
                           content=render_template('edit.html', 
                           book_id=book_id,
                           book_name=book['name'],
                           corpus_id=current_corpus['id'],
                           original_text=current_corpus['original_text'],
                           edited_text=current_corpus['edited_text'],
                           file_name=current_corpus['file_name'],
                           item_order=current_corpus['item_order'],
                           current_index=current_index,
                           prev_corpus_id=prev_corpus_id,
                           next_corpus_id=next_corpus_id,
                           total=len(corpus_ids),
                           file_corpus_position=file_corpus_position,
                           file_corpus_count=file_corpus_count,
                           segmented_text=segmented_text,
                           thulac_text=thulac_text,  
                           corpus_ids=corpus_ids,
                           admin_remark=current_corpus['admin_remark'],
                           admin_modified=current_corpus['admin_modified'],
                           admin_modified_by=current_corpus['admin_modified_by'],
                           admin_modified_at=current_corpus['admin_modified_at'],
                           seg3_text=seg3_text,
                           existing_pos_tags=(get_pos_tags_for_corpus(current_corpus['id']) or [])))

@app.route('/text_proofreading', methods=["GET", "POST"])
def text_proofreading():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    if request.method == 'POST':
        document_name = request.form.get('document_name', '未命名文档')
        author = request.form.get('author', '匿名')
        file = request.files.get('file')
        
        if not file or file.filename == '':
            return render_template('text_proofreading.html', error='请选择要上传的文件')
        
        if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in ['pdf', 'doc', 'docx', 'txt']:
            return render_template('text_proofreading.html', error='只支持PDF、DOC、DOCX或TXT文件')
        
        result_id, error = process_uploaded_file(file, document_name, author)
        if error:
            return render_template('text_proofreading.html', error=error)
        return redirect(url_for('proofreading_result', result_id=result_id))
    
    return render_template('text_proofreading.html')

@app.route('/proofreading_result/<int:result_id>')
def proofreading_result(result_id):
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    conn = get_db_connection()
    result = conn.execute('SELECT * FROM proofreading_results WHERE id = ?', (result_id,)).fetchone()
    conn.close()
    
    if not result:
        return redirect(url_for('text_proofreading'))
    
    try:
        issues = ast.literal_eval(result['issues'])
    except:
        issues = []
    
    created_at = datetime.datetime.strptime(result['created_at'], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
    
    return render_template('proofreading_result.html', 
                          document_name=result['document_name'],
                          author=result['author'],
                          original_text=result['original_text'],
                          analyzed_text=result['analyzed_text'],
                          issues=issues,
                          created_at=created_at,
                          result_id=result_id)

@app.route('/first_proofreading/confirm/<int:result_id>', methods=["POST"])
def first_proofreading_confirm(result_id):
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    conn = get_db_connection()
    result = conn.execute('SELECT * FROM proofreading_results WHERE id = ?', (result_id,)).fetchone()
    if not result:
        conn.close()
        return redirect(url_for('text_proofreading'))
    
    corrected_text = request.form.get('corrected_text', result['original_text'])
    cur = conn.cursor()
    cur.execute('UPDATE proofreading_results SET corrected_text = ? WHERE id = ?', (corrected_text, result_id))
    conn.commit()
    conn.close()
    
    sentences = split_text_into_sentences(corrected_text)
    if not sentences:
        return render_template('text_proofreading.html', error='未能拆分出有效句子')
    
    base_name = result['document_name'] or '未命名文档'
    if result['author']:
        base_name = f"{base_name}_{result['author']}"
    base_name = sanitize_filename(base_name)
    
    output_dir, count, base_txt_path = save_sentences_chunks(sentences, base_name, corrected_text)
    book_id = import_generated_book_to_db(base_name, result['author'], output_dir)
    success_message = f"已处理完成。原始文本保存为 {base_txt_path}，拆分文件已保存到 {output_dir}，共 {count} 个文件。"
    return render_template('text_proofreading.html', error=None, success_message=success_message, success_book_id=book_id, success_book_name=base_name)

@app.route('/proofreading_history')
def proofreading_history():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    conn = get_db_connection()
    history = conn.execute('''
        SELECT h.id, h.edited_at, h.original_text, h.edited_text, h.user,
               b.name AS book_name, c.file_name, c.item_order
        FROM proofreading_history h
        JOIN books b ON h.book_id = b.id
        JOIN corpus c ON h.corpus_id = c.id
        ORDER BY h.edited_at DESC
        LIMIT 100
    ''').fetchall()
    conn.close()
    
    formatted_history = []
    for record in history:
        record_dict = dict(record)
        edited_at = datetime.datetime.strptime(record_dict['edited_at'], '%Y-%m-%d %H:%M:%S')
        record_dict['formatted_time'] = edited_at.strftime('%Y-%m-%d %H:%M')
        record_dict['diff'] = diff_text(record_dict['original_text'], record_dict['edited_text'])
        formatted_history.append(record_dict)
    
    books = get_books()
    return render_template('dashboard.html', 
                           books=books,
                           active_page='history',
                           content=render_template('proofreading_history.html', 
                           history=formatted_history))

@app.route('/profile', methods=["GET", "POST"])
def profile():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM 用户 WHERE 用户名 = ?", (session['username'],))
    user = cursor.fetchone()
    
    message = None
    message_type = None
    
    if request.method == 'POST':
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not old_password or not new_password or not confirm_password:
            message = '所有字段都必须填写'
            message_type = 'error'
        elif user['密码'] != old_password:
            message = '原密码不正确'
            message_type = 'error'
        elif new_password != confirm_password:
            message = '新密码和确认密码不一致'
            message_type = 'error'
        else:
            cursor.execute('''
                UPDATE 用户 
                SET 密码 = ?
                WHERE 用户名 = ?

            ''', (new_password, session['username']))
            conn.commit()
            message = '密码修改成功'
            message_type = 'success'
    
    conn.close()
    
    books = get_books()
    return render_template('dashboard.html', 
                           books=books,
                           active_page='profile',
                           content=render_template('profile.html', 
                                                  user=dict(user),
                                                  message=message,
                                                  message_type=message_type))

@app.route('/admin')
def admin_dashboard():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    if session.get('role') != '管理员':
        flash('没有权限', 'error')
        return redirect(url_for('dashboard'))
    books = get_books()
    return render_template('dashboard.html',
                           books=books,
                           active_page='admin',
                           content=render_template('admin.html', students=get_students(), books=books, submissions=get_latest_student_submissions()))

@app.route('/admin/import_students', methods=["POST"])
def admin_import_students():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    if session.get('role') != '管理员':
        flash('没有权限', 'error')
        return redirect(url_for('dashboard'))
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('请选择Excel文件', 'error')
        return redirect(url_for('admin_dashboard'))
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in ['xlsx', 'xls']:
        flash('仅支持Excel文件（.xlsx/.xls）', 'error')
        return redirect(url_for('admin_dashboard'))
    ok, msg = import_students_from_excel_file(file)
    flash(msg, 'success' if ok else 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/assign_tasks', methods=["POST"])
def admin_assign_tasks():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    if session.get('role') != '管理员':
        flash('没有权限', 'error')
        return redirect(url_for('dashboard'))
    book_id = request.form.get('book_id')
    student_ids = request.form.getlist('student_ids')
    if not book_id or not student_ids:
        flash('请提供书籍与学生名单', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        book_id_int = int(book_id)
    except:
        flash('无效的书籍ID', 'error')
        return redirect(url_for('admin_dashboard'))
    count = assign_tasks_balanced(book_id_int, student_ids)
    if count > 0:
        flash(f'已按字节数均衡分配 {count} 条任务', 'success')
    else:
        flash('没有可分配的任务或已全部分配', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/submission/edit', methods=["POST"])
def admin_edit_submission():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    if session.get('role') != '管理员':
        flash('没有权限', 'error')
        return redirect(url_for('dashboard'))
    corpus_id = request.form.get('corpus_id')
    new_text = request.form.get('new_text', '')
    remark = request.form.get('remark', '此条已由管理员修改')
    if not corpus_id:
        flash('缺少语料ID', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        conn = get_db_connection()
        corpus = conn.execute('SELECT id, original_text, book_id FROM corpus WHERE id = ?', (corpus_id,)).fetchone()
        if not corpus:
            conn.close()
            flash('语料不存在', 'error')
            return redirect(url_for('admin_dashboard'))
        update_corpus(corpus['id'], new_text, corpus['original_text'], session['username'])
        cur = conn.cursor()
        cur.execute('''
            UPDATE corpus
            SET admin_modified = 1, admin_remark = ?, admin_modified_by = ?, admin_modified_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (remark, session['username'], corpus['id']))
        cur.execute('''
            INSERT INTO admin_actions (book_id, corpus_id, action, detail, admin_username)
            VALUES (?, ?, 'modify', ?, ?)
        ''', (corpus['book_id'], corpus['id'], remark, session['username']))
        conn.commit()
        conn.close()
        flash('已修改并记录管理员备注', 'success')
    except Exception as e:
        flash(f'修改失败: {str(e)}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/submission/delete', methods=["POST"])
def admin_delete_submission():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    if session.get('role') != '管理员':
        flash('没有权限', 'error')
        return redirect(url_for('dashboard'))
    corpus_id = request.form.get('corpus_id')
    remark = request.form.get('remark', '此条已由管理员删除学生提交')
    if not corpus_id:
        flash('缺少语料ID', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        conn = get_db_connection()
        corpus = conn.execute('SELECT id, book_id FROM corpus WHERE id = ?', (corpus_id,)).fetchone()
        if not corpus:
            conn.close()
            flash('语料不存在', 'error')
            return redirect(url_for('admin_dashboard'))
        cur = conn.cursor()
        cur.execute('UPDATE corpus SET edited_text = NULL, admin_modified = 1, admin_remark = ?, admin_modified_by = ?, admin_modified_at = CURRENT_TIMESTAMP WHERE id = ?', (remark, session['username'], corpus['id']))
        cur.execute('INSERT INTO admin_actions (book_id, corpus_id, action, detail, admin_username) VALUES (?, ?, \'delete\', ?, ?)', (corpus['book_id'], corpus['id'], remark, session['username']))
        conn.commit()
        conn.close()
        flash('已删除该学生提交并记录管理员备注', 'success')
    except Exception as e:
        flash(f'删除失败: {str(e)}', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/my_tasks')
def my_tasks():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    books = get_books()
    tasks = get_my_tasks(session['username'])
    return render_template('dashboard.html',
                           books=books,
                           active_page='my_tasks',
                           content=render_template('my_tasks.html', tasks=tasks))
@app.route('/admin/reset_password', methods=["POST"])
def admin_reset_password():
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    if session.get('role') != '管理员':
        flash('没有权限', 'error')
        return redirect(url_for('dashboard'))
    target_username = request.form.get('target_username')
    target_student_id = request.form.get('target_student_id')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    if not new_password or not confirm_password or new_password != confirm_password:
        flash('新密码不一致', 'error')
        return redirect(url_for('admin_dashboard'))
    conn = get_db_connection()
    cursor = conn.cursor()
    if target_username:
        cursor.execute("UPDATE 用户 SET 密码 = ? WHERE 用户名 = ?", (new_password, target_username))
    elif target_student_id:
        cursor.execute("UPDATE 用户 SET 密码 = ? WHERE 学号 = ?", (new_password, target_student_id))
    else:
        conn.close()
        flash('请提供用户名或学号', 'error')
        return redirect(url_for('admin_dashboard'))
    conn.commit()
    conn.close()
    flash('密码已重置', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    jieba.initialize()
    app.run(debug=True)
