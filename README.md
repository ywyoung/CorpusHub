# CorpusHub

一个基于 Flask 的中文语料校对与文本分析平台。

## 功能特性

- **用户管理**: 支持学生注册、管理员角色认证
- **语料管理**: 上传书籍/文档，自动分词后拆分为待校对语料
- **校对功能**: 多引擎分词对比（jieba / THULAC / LTP），支持词性标注
- **文本校对**: 自动检测常见错别字、标点错误、格式问题
- **统计分析**: 词频统计、高频词云、N-gram 分析、词性分布
- **任务分配**: 管理员可均衡分配语料校对任务给学生
- **操作审计**: 记录学生修改历史与管理员操作

## 技术栈

- **后端**: Flask + SQLite
- **前端**: HTML + JavaScript + Bootstrap
- **分词引擎**: jieba / THULAC / LTP / pkuseg / SnowNLP
- **数据可视化**: matplotlib + wordcloud

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/whysonical/CorpusHub.git
cd CorpusHub
```

### 2. 安装依赖

```bash
pip install flask jieba thulac python-docx wordcloud matplotlib pandas PyPDF2
```

### 3. 运行

```bash
python app.py
```

访问 http://127.0.0.1:5000

### 默认管理员账号

- 用户名: `admin`
- 密码: `admin123`

## 项目结构

```
.
├── app.py                  # 主应用
├── import_excel_to_db.py   # 导入学生Excel
├── import_corpus.py        # 导入语料脚本
├── student_base.xlsx       # 学生名单示例
├── templates/              # HTML 模板
└── temp/                  # 临时文件目录
```

## 许可证

MIT License
