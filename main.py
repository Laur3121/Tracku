import discord
from discord import app_commands
import os
import sqlite3
from datetime import datetime, timezone, date
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.presences = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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

def log_start(user_id, user_name, app_name):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO activity_log (user_id, user_name, app_name, started_at)
        VALUES (?, ?, ?, ?)
    ''', (user_id, user_name, app_name, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

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

def get_today_logs(user_id):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    today = datetime.now(timezone.utc).date().isoformat()
    c.execute('''
        SELECT app_name, started_at, ended_at
        FROM activity_log
        WHERE user_id = ? AND started_at LIKE ?
        ORDER BY started_at
    ''', (user_id, f'{today}%'))
    rows = c.fetchall()
    conn.close()
    return rows

@client.event
async def on_ready():
    init_db()
    await tree.sync()
    print(f'{client.user} としてログインしました')

@client.event
async def on_presence_update(before, after):
    before_apps = {a.name for a in before.activities if a.name}
    after_apps = {a.name for a in after.activities if a.name}

    for app in after_apps - before_apps:
        print(f'{after.name} が {app} を開始')
        log_start(str(after.id), after.name, app)

    for app in before_apps - after_apps:
        print(f'{after.name} が {app} を終了')
        log_end(str(after.id), app)

@tree.command(name='tracku', description='今日のアクティビティを表示')
@app_commands.describe(action='today または week')
async def tracku(interaction: discord.Interaction, action: str = 'today'):
    if action == 'today':
        logs = get_today_logs(str(interaction.user.id))
        if not logs:
            await interaction.response.send_message('今日のアクティビティはまだありません。')
            return

        embed = discord.Embed(
            title=f'📊 {interaction.user.name} の今日のアクティビティ',
            color=0x5865F2
        )
        for app_name, started_at, ended_at in logs:
            start = datetime.fromisoformat(started_at).strftime('%H:%M')
            end = datetime.fromisoformat(ended_at).strftime('%H:%M') if ended_at else '進行中'
            embed.add_field(
                name=app_name,
                value=f'{start} → {end}',
                inline=False
            )
        await interaction.response.send_message(embed=embed)

client.run(os.getenv('DISCORD_TOKEN'))