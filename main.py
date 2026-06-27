import discord
import os
import sqlite3
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.presences = True
intents.members = True

client = discord.Client(intents=intents)

# DB初期化
def init_db():
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            user_name TEXT,
            app_name TEXT,
            started_at TEXT,
            ended_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

# 開始を記録
def log_start(user_id, user_name, app_name):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO activity_log (user_id, user_name, app_name, started_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, user_name, app_name, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

# 終了を記録
def log_end(user_id, app_name):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    c.execute('''
        UPDATE activity_log
        SET ended_at = ?
        WHERE user_id = ? AND app_name = ? AND ended_at IS NULL
    ''', (datetime.now(timezone.utc).isoformat(), user_id, app_name))
    conn.commit()
    conn.close()

@client.event
async def on_ready():
    init_db()
    print(f'{client.user} としてログインしました')

@client.event
async def on_presence_update(before, after):
    before_apps = {a.name for a in before.activities if a.name}
    after_apps = {a.name for a in after.activities if a.name}

    # 新しく始まったアクティビティ
    for app in after_apps - before_apps:
        print(f'{after.name} が {app} を開始')
        log_start(str(after.id), after.name, app)

    # 終わったアクティビティ
    for app in before_apps - after_apps:
        print(f'{after.name} が {app} を終了')
        log_end(str(after.id), app)

client.run(os.getenv('DISCORD_TOKEN'))
