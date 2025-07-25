import os
from flask import Flask, render_template, request, jsonify, Response,send_file 
import json, sqlite3, pathlib, datetime

app = Flask(__name__)
DATA_PATH = pathlib.Path("ocean_qa_test.json")
DB_PATH   = pathlib.Path("results.db")

import json
import sqlite3

import json
import sqlite3

def load_questions():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)  # 假设文件中是一个问题列表



def insert_questions_from_json():
    """从 JSON 文件插入题库数据到数据库"""
    # 读取 JSON 文件
    with open("ocean_qa_test.json", "r", encoding="utf-8") as f:
        questions_data = json.load(f)  # 假设文件中是一个问题列表
    
    # 连接到数据库
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 插入数据
    for question in questions_data:
        question_id = question["question_id"]
        question_text = question["question"]
        
        # 将选项（字典类型）转换为字符串
        options = json.dumps(question["options"], ensure_ascii=False)

        cur.execute("""
            INSERT OR REPLACE INTO questions (question_id, question, options)
            VALUES (?, ?, ?)
        """, (question_id, question_text, options))

    con.commit()
    con.close()




def init_db(force=False):
    """初始化数据库，若表不存在则创建"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 创建 answers 表，记录用户选择
    cur.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            choice TEXT,
            annotator TEXT,
            ts TEXT,
            UNIQUE (question_id, annotator)
        )
    """)

    # 创建 questions 表，记录题库
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            question_id INTEGER PRIMARY KEY,
            question TEXT,
            options TEXT
        )
    """)
    
    # 如果是 force，重新初始化表并清理旧数据
    if force:
        cur.execute("DROP TABLE IF EXISTS answers")
        cur.execute("DROP TABLE IF EXISTS questions")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                choice TEXT,
                annotator TEXT,
                ts TEXT,
                UNIQUE (question_id, annotator)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                question_id INTEGER PRIMARY KEY,
                question TEXT,
                options TEXT
            )
        """)

        # # 插入题库数据
        # questions_data = [
        #     (0, 'In which region did reef islands develop during periods of stable or falling RSLR?', 'A: Queensland, Australia; B: Western Australia; C: India; D: Belize'),
        #     (1, 'What is the main cause of global warming?', 'A: Greenhouse gases; B: Solar radiation; C: Ocean currents; D: Volcanic activity')
        # ]
        
        # cur.executemany("""
        #     INSERT OR REPLACE INTO questions (question_id, question, options)
        #     VALUES (?, ?, ?)
        # """, questions_data)
        
    con.commit()
    con.close()



def save_answer(qid, choice, annotator):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """INSERT OR REPLACE INTO answers
              (question_id, choice, annotator, ts)
           VALUES (?,?,?, datetime('now'))""",  # 使用 SQLite 的当前时间戳
        (qid, choice, annotator)
    )
    con.commit()
    con.close()


def load_user_answers(annotator: str) -> dict:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT question_id, choice FROM answers WHERE annotator=?", (annotator,))
    out = {qid: choice for qid, choice in cur.fetchall()}
    con.close()
    print("Loaded answers:", out) 
    return out

# ---------- 题库 ----------
def load_questions():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ---------- 路由 ----------
@app.route("/")
def index():
    user_id  = request.remote_addr              # 以 IP 作为临时用户标识
    qs       = load_questions()
    answers  = load_user_answers(user_id)       # {question_id: "A/B/C/D"}
    print("加载的答案:", answers)  # 查看数据库中加载的答案
    return render_template("index.html",
                           questions=qs,
                           answers=answers)

@app.route('/pdf/<title>')
def pdf_link(title):
    # Handle logic for the PDF, such as displaying or downloading it
    return send_file(f'static/Ocean-pdf/{title}.pdf', as_attachment=True)


@app.route("/autosave", methods=["POST"])
def autosave():
    data = request.get_json()
    try:
        qid    = int(data["question_id"])
        choice = data["choice"]
    except (KeyError, TypeError, ValueError):
        return jsonify({"status": "error"}), 400

    save_answer(qid, choice, annotator=request.remote_addr)
    return jsonify({"status": "ok"})


@app.route("/download_csv")
def download_csv():
    annotator = request.remote_addr
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 只保留每题最新一条
    cur.execute("""
        SELECT question_id, choice
        FROM answers
        WHERE annotator = ?
        GROUP BY question_id
        ORDER BY question_id
    """, (annotator,))
    rows = cur.fetchall()
    con.close()

    csv_lines = ["question_id,choice"]
    csv_lines += [f"{qid},{choice}" for qid, choice in rows]
    csv_data = "\n".join(csv_lines)
    if not os.path.exists("qa_result"):
        os.makedirs("qa_result")
    file_name = f"qa_result/answers_{annotator.replace(':','_')}_{datetime.datetime.utcnow():%Y%m%dT%H%M%SZ}.csv"
    pathlib.Path(file_name).write_text(csv_data, encoding="utf-8")

    return send_file(file_name,
                     as_attachment=True,
                     download_name=file_name,
                     mimetype="text/csv")


@app.route("/answers")
def answers_page():
    """显示当前用户在数据库中的所有答案"""
    annotator = request.remote_addr
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 获取当前用户已保存的答案
    cur.execute("""
        SELECT question_id, choice, datetime(ts,'unixepoch','localtime') 
        FROM answers
        WHERE annotator = ?
        ORDER BY question_id
    """, (annotator,))
    rows = cur.fetchall()

    # 获取题库中的所有 question_id
    cur.execute("SELECT question_id FROM questions")
    all_question_ids = {row[0] for row in cur.fetchall()}

    # 获取已回答的题目 question_id
    cur.execute("""
        SELECT question_id
        FROM answers
        WHERE annotator = ?
    """, (annotator,))
    answered_question_ids = {row[0] for row in cur.fetchall()}

    # 获取未回答的题目 (题库中的所有 question_id 减去已回答的 question_id)
    unanswered = all_question_ids - answered_question_ids

    con.close()

    return render_template("answers.html", rows=rows, unanswered=unanswered, count=len(rows), unanswered_count=len(unanswered))

@app.route("/clear_answers", methods=["POST"])
def clear_answers():
    """清空当前用户（按 IP）所有答案"""
    annotator = request.remote_addr
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("DELETE FROM answers WHERE annotator=?", (annotator,))
    con.commit()
    con.close()
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    if not DB_PATH.exists():
        init_db(force=True) 
        insert_questions_from_json()
    app.run(host="0.0.0.0", port=5000, debug=True)
