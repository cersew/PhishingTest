import smtplib
import sqlite3
import sys
from email.mime.text import MIMEText
from datetime import datetime

# 📌 Данные для SMTP-сервера (замени на свои)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = "super1234567899999@gmail.com"
EMAIL_PASS = "gkqc mlzb woay rpql"

# 📌 Получаем список email из аргументов командной строки
if len(sys.argv) < 2:
    print("Қате: email енгізілмеген!")
    sys.exit(1)

emails = sys.argv[1].split(",")  # Разбираем e-mail через запятую

# 📌 Подключаемся к базе данных и добавляем всех сотрудников со статусом "Не переходил"
conn = sqlite3.connect("phishing.db")
cursor = conn.cursor()
for email in emails:
    cursor.execute("INSERT INTO phishing_results (email, status, timestamp) VALUES (?, ?, ?)",
                   (email, "Ашқан жоқ", datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
conn.commit()
conn.close()

# 📌 Функция отправки фишингового письма
def send_phishing_email(recipient_email):
    subject = "Шұғыл қауіпсіздік жаңартуы"
    phishing_link = f"http://127.0.0.1:5000/login?email={recipient_email}"
    tracking_pixel = f'<img src="http://127.0.0.1:5000/track_email?email={recipient_email}" width="1" height="1">'

    body = f"""
    <p>Құрметті әріптес,</p>
    <p>Қауіпсіздікті арттыру үшін деректерді шұғыл түрде жаңарту қажет. 
    Келесі сілтеме бойынша өтіңіз:</p>
    <p><a href="{phishing_link}">{phishing_link}</a></p>
    {tracking_pixel}
    """

    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = recipient_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, recipient_email, msg.as_string())
            print(f"✅ Хат жіберілді: {recipient_email}")
    except Exception as e:
        print(f"❌ Хат жіберілген жоқ (қате) {recipient_email}: {e}")

# 📌 Отправляем письма всем указанным e-mail
for email in emails:
    send_phishing_email(email)

print("Барлық хаттар сәтті жіберілді!")
