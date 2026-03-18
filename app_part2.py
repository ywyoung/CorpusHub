def analyze_text(text):
    """分析文本，找出潜在问题"""
    issues = []
    
    words = jieba.lcut(text)
    
    common_mistakes = {
        '的': ['地', '得'],
        '在': ['再'],
        '做': ['作'],
        '已': ['以'],
        '即': ['既'],
        '至': ['致'],
        '需': ['须'],
        '分': ['份'],
        '象': ['像'],
        '座': ['坐'],
        '常': ['长'],
        '具': ['俱'],
        '式': ['势'],
        '状': ['壮'],
        '题': ['提'],
        '供': ['贡'],
        '备': ['倍'],
    }
    
    for i, word in enumerate(words):
        if word in common_mistakes:
            if i > 0 and words[i-1] in common_mistakes[word]:
                issues.append({
                    'type': '错别字',
                    'word': words[i-1] + word,
                    'suggestion': word,
                    'position': i-1,
                    'message': f'可能错别字: "{words[i-1]}{word}"，建议使用"{word}"'
                })
    
    punctuation_repeats = re.finditer(r'([，。！？；：、])\1{2,}', text)
    for match in punctuation_repeats:
        issues.append({
            'type': '标点重复',
            'word': match.group(),
            'suggestion': match.group()[0],
            'position': match.start(),
            'message': f'标点重复: "{match.group()}"，建议简化为"{match.group()[0]}"'
        })
    

    space_issues = re.finditer(r'(?<=\w)\s{2,}(?=\w)', text)
    for match in space_issues:
        issues.append({
            'type': '多余空格',
            'word': match.group(),
            'suggestion': ' ',
            'position': match.start(),
            'message': f'多余空格: "{match.group()}"，建议简化为单个空格'
        })
    
    en_punctuation = re.finditer(r'[a-zA-Z][，。！？；：、]', text)
    for match in en_punctuation:
        issues.append({
            'type': '标点错误',
            'word': match.group(),
            'suggestion': match.group()[0] + '.',
            'position': match.start(),
            'message': f'英文后使用中文标点: "{match.group()}"，建议使用英文标点'
        })
    
    has_ending_punctuation = re.search(r'[。！？!?]', text)
    has_line_break = '\n' in text
    
    if len(text) > 50 and not has_ending_punctuation and not has_line_break:
        issues.append({
            'type': '长句警告',
            'word': text,
            'suggestion': '建议拆分句子',
            'position': 0,
            'message': f'长句警告: 句子长度超过50字符（{len(text)}字符），建议拆分以提高可读性'
        })
    

    issues.sort(key=lambda x: x['position'])
    
    return issues

def process_uploaded_file(file, document_name, author):
    """处理上传的文件并进行分析"""
    try:
        text, err = extract_uploaded_text(file)
        if err:
            return None, err
        
        issues = analyze_text(text)
        
        marked_text = text
        offset = 0
        for issue in issues:
            start = issue['position'] + offset
            end = start + len(issue['word'])
            
            marker = f'<span class="highlight {issue["type"]}" title="{issue["message"]}">' 
            marked_text = marked_text[:start] + marker + marked_text[start:end] + '</span>' + marked_text[end:]
            offset += len(marker) + len('</span>')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO proofreading_results (document_name, author, original_text, analyzed_text, issues)
            VALUES (?, ?, ?, ?, ?)
        ''', (document_name, author, text, marked_text, str(issues)))
        result_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return result_id, None
    
    except Exception as e:
        return None, str(e)

def diff_text(text1, text2):
    """比较两个文本的差异"""
    d = Differ()
    result = list(d.compare(text1.splitlines(), text2.splitlines()))
    
    diff_html = []
    for line in result:
        if line.startswith('  '):
            diff_html.append(f'<span>{line[2:]}</span>')
        elif line.startswith('- '):
            diff_html.append(f'<span class="del">{line[2:]}</span>')
        elif line.startswith('+ '):
            diff_html.append(f'<span class="ins">{line[2:]}</span>')
        elif line.startswith('? '):
            continue
    
    return '<br>'.join(diff_html)


app.jinja_env.filters['diff'] = diff_text

@app.route('/upload', methods=["POST"])
def upload_file():
    """处理文件上传"""
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    if 'file' not in request.files:
        return jsonify(success=False, message='没有文件部分')
    
    file = request.files['file']
    if file.filename == '':
        return jsonify(success=False, message='未选择文件')
    
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in ['txt', 'doc', 'docx']:
        return jsonify(success=False, message='只支持txt, doc或docx文件')
    
    try:
        file_ext = file.filename.rsplit('.', 1)[1].lower()
        text = ""
        
        if file_ext == 'txt':
            text = file.read().decode('utf-8')
        elif file_ext in ['doc', 'docx']:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as temp_file:
                file.save(temp_file.name)
                if file_ext == 'docx':
                    doc = docx.Document(temp_file.name)
                    text = '\n'.join([para.text for para in doc.paragraphs])
                else:
                    return jsonify(success=False, message='DOC文件处理需要额外依赖，请转换为DOCX或TXT')
            os.unlink(temp_file.name)
        
        sentences = split_text_into_sentences(text)
        
        if not sentences:
            return jsonify(success=False, message='文件中未找到有效的句子')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        book_name = os.path.splitext(file.filename)[0]
        cursor.execute('INSERT INTO books (name) VALUES (?)', (book_name,))
        book_id = cursor.lastrowid
        
        for i, sentence in enumerate(sentences):
            cursor.execute('''
                INSERT INTO corpus (book_id, original_text, edited_text, file_name, item_order)
                VALUES (?, ?, ?, ?, ?)
            ''', (book_id, sentence, sentence, file.filename, i + 1))
        
        conn.commit()
        conn.close()
        
        return jsonify(success=True, book_id=book_id)
        
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/delete_book/<int:book_id>', methods=["DELETE"])
def delete_book(book_id):
    """删除书籍及其相关语料"""
    if 'username' not in session:
        return jsonify(success=False, message='请先登录')
    
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM corpus WHERE book_id = ?', (book_id,))
        conn.execute('DELETE FROM books WHERE id = ?', (book_id,))
        conn.commit()
        conn.close()
        
        session.pop(f'last_position_{book_id}', None)
        return jsonify(success=True, message='书籍删除成功')
    
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route("/")
def index():
    """首页"""
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('welcome.html')

@app.route('/statistics')
def statistics():
    """统计分析页面"""
    if 'username' not in session:
        flash('请先登录', 'error')
        return redirect(url_for('loginpage'))
    
    books = get_books()
    return render_template('dashboard.html', 
                           books=books,
                           active_page='statistics',
                           content=render_template('statistics.html', 
                                                  books=books,
                                                  analysis_result=None))

@app.route('/analyze_book', methods=['POST'])
def analyze_book():
    """分析书籍数据"""
    if 'username' not in session:
        return jsonify(success=False, message='请先登录')
    
    try:
        book_id = request.form.get('book_id')
        if not book_id:
            return jsonify(success=False, message='请选择书籍')
        
        conn = get_db_connection()
        
        book = conn.execute('SELECT name FROM books WHERE id = ?', (book_id,)).fetchone()
        if not book:
            return jsonify(success=False, message='书籍不存在')
        book_name = book['name']
        
        corpus = conn.execute('''
            SELECT COALESCE(edited_text, original_text) AS text 
            FROM corpus 
            WHERE book_id = ?
        ''', (book_id,)).fetchall()
        conn.close()
        
        if not corpus:
            return jsonify(success=False, message='书籍中没有找到语料')
        
        full_text = ' '.join([row['text'] for row in corpus])
        
        words = jieba.lcut(full_text)
        
        stop_words = {'的', '了', '是', '在', '和', '有', '我', '你', '他', '她', '它', '我们', '你们', '他们', 
                     '这', '那', '就', '也', '都', '要', '不', '很', '而', '与', '及', '等', '或', '并', '但', 
                     '却', '虽然', '如果', '因为', '所以', '为了', '可以', '可能', '一定', '一些', '一个', '一种'}
        
        filtered_words = [word for word in words if len(word) > 1 and word not in stop_words and not re.match(r'^\W+$', word)]
        
        word_freq = Counter(filtered_words)
        top_words = word_freq.most_common(20)
        
        wordcloud = WordCloud(
            font_path='simhei.ttf',
            width=800,
            height=400,
            background_color='white',
            max_words=200
        ).generate(' '.join(filtered_words))
        
        img_buffer = BytesIO()
        plt.figure(figsize=(10, 5))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.axis('off')
        plt.savefig(img_buffer, format='png', bbox_inches='tight', pad_inches=0)
        plt.close()
        wordcloud_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        
        bigrams = []
        for i in range(len(words) - 1):
            if len(words[i]) > 1 and len(words[i+1]) > 1 and words[i] not in stop_words and words[i+1] not in stop_words:
                bigrams.append(words[i] + words[i+1])
        
        bigram_freq = Counter(bigrams)
        top_bigrams = bigram_freq.most_common(10)
        
        trigrams = []
        for i in range(len(words) - 2):
            if (len(words[i]) > 1 and len(words[i+1]) > 1 and len(words[i+2]) > 1 and 
                words[i] not in stop_words and words[i+1] not in stop_words and words[i+2] not in stop_words):
                trigrams.append(words[i] + words[i+1] + words[i+2])
        
        trigram_freq = Counter(trigrams)
        top_trigrams = trigram_freq.most_common(10)
        
        analysis_result = {
            'book_name': book_name,
            'total_words': len(words),
            'unique_words': len(set(words)),
            'top_words': top_words,
            'wordcloud': wordcloud_base64,
            'top_bigrams': top_bigrams,
            'top_trigrams': top_trigrams
        }
        
        thu = thulac.thulac()
        thu_result = thu.cut(full_text)
        
        pos_counter = Counter()
        for word, pos in thu_result:
            if len(word) > 1:  
                pos_counter[pos] += 1
        
        top_pos = pos_counter.most_common(10)
        analysis_result['top_pos'] = top_pos
        
        books = get_books()
        return render_template('dashboard.html', 
                               books=books,
                               active_page='statistics',
                               content=render_template('statistics.html', 
                                                      books=books,
                                                      analysis_result=analysis_result))
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(success=False, message=str(e))
