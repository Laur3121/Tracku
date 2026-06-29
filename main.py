import discord
from discord import app_commands
import os
import sqlite3
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            user_name TEXT,
            joined_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

def is_joined(user_id):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    c.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def join_user(user_id, user_name):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, user_name, joined_at) VALUES (?, ?, ?)',
              (user_id, user_name, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()

def leave_user(user_id):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    c.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    c.execute('DELETE FROM activity_log WHERE user_id = ?', (user_id,))
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

def get_week_logs(user_id):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    c.execute('''
        SELECT app_name,
               SUM(
                   CASE 
                       WHEN ended_at IS NOT NULL 
                       THEN (julianday(ended_at) - julianday(started_at)) * 1440
                       ELSE 0
                   END
               ) as total_minutes
        FROM activity_log
        WHERE user_id = ? AND started_at >= ?
        GROUP BY app_name
        ORDER BY total_minutes DESC
    ''', (user_id, week_ago))
    rows = c.fetchall()
    conn.close()
    return rows

def get_server_ranking(guild):
    conn = sqlite3.connect('tracku.db')
    c = conn.cursor()
    week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    member_ids = [str(m.id) for m in guild.members]
    placeholders = ','.join('?' * len(member_ids))
    c.execute(f'''
        SELECT user_name, app_name,
               SUM(
                   CASE 
                       WHEN ended_at IS NOT NULL 
                       THEN (julianday(ended_at) - julianday(started_at)) * 1440
                       ELSE 0
                   END
               ) as total_minutes
        FROM activity_log
        WHERE user_id IN ({placeholders}) AND started_at >= ?
        GROUP BY user_id, app_name
        ORDER BY total_minutes DESC
        LIMIT 10
    ''', member_ids + [week_ago])
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
    if not is_joined(str(after.id)):
        return

    before_apps = {a.name for a in before.activities if a.name}
    after_apps = {a.name for a in after.activities if a.name}

    for app in after_apps - before_apps:
        print(f'{after.name} が {app} を開始')
        log_start(str(after.id), after.name, app)

    for app in before_apps - after_apps:
        print(f'{after.name} が {app} を終了')
        log_end(str(after.id), app)

@tree.command(name='tracku', description='Trackuコマンド')
@app_commands.describe(action='アクション')
@app_commands.choices(action=[
    app_commands.Choice(name='join - 記録を開始', value='join'),
    app_commands.Choice(name='leave - 記録を停止', value='leave'),
    app_commands.Choice(name='today - 今日のログ', value='today'),
    app_commands.Choice(name='week - 今週のログ', value='week'),
    app_commands.Choice(name='summary - 円グラフ', value='summary'),
    app_commands.Choice(name='ranking - ランキング', value='ranking'),
])
async def tracku(interaction: discord.Interaction, action: str = 'today'):

    if action == 'join':
        if is_joined(str(interaction.user.id)):
            await interaction.response.send_message('すでに参加済みです。', ephemeral=True)
            return
        join_user(str(interaction.user.id), interaction.user.name)
        await interaction.response.send_message(
            '✅ Trackuに参加しました！アクティビティの記録を開始します。\n`/tracku leave` でいつでも停止・データ削除できます。',
            ephemeral=True
        )

    elif action == 'leave':
        if not is_joined(str(interaction.user.id)):
            await interaction.response.send_message('まだ参加していません。', ephemeral=True)
            return
        leave_user(str(interaction.user.id))
        await interaction.response.send_message('🗑️ データを削除して退出しました。', ephemeral=True)

    elif action == 'today':
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
            embed.add_field(name=app_name, value=f'{start} → {end}', inline=False)
        await interaction.response.send_message(embed=embed)

    elif action == 'week':
        logs = get_week_logs(str(interaction.user.id))
        if not logs:
            await interaction.response.send_message('今週のアクティビティはまだありません。')
            return
        embed = discord.Embed(
            title=f'📊 {interaction.user.name} の今週のアクティビティ',
            color=0x5865F2
        )
        for app_name, total_minutes in logs:
            hours = int(total_minutes // 60)
            minutes = int(total_minutes % 60)
            embed.add_field(name=app_name, value=f'{hours}時間{minutes}分', inline=False)
        await interaction.response.send_message(embed=embed)

    elif action == 'summary':
        logs = get_week_logs(str(interaction.user.id))
        if not logs:
            await interaction.response.send_message('今週のアクティビティはまだありません。')
            return
        await interaction.response.defer()

        labels = [row[0] for row in logs]
        sizes = [row[1] for row in logs]

        plt.rcParams['font.family'] = 'Hiragino Sans'
        colors = ['#5865F2', '#57F287', '#FEE75C', '#EB459E', '#ED4245']

        fig, ax = plt.subplots(figsize=(7, 7), facecolor='#2B2D31')
        ax.set_facecolor('#2B2D31')
        wedges, texts, autotexts = ax.pie(
            sizes,
            labels=labels,
            autopct='%1.1f%%',
            startangle=90,
            colors=colors[:len(labels)],
            textprops={'color': 'white', 'fontsize': 11}
        )
        for autotext in autotexts:
            autotext.set_color('white')
        ax.set_title(f'{interaction.user.name} の今週の使用時間',
                     color='white', fontsize=14, pad=20)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#2B2D31')
        buf.seek(0)
        plt.close()
        await interaction.followup.send(file=discord.File(buf, filename='summary.png'))

    elif action == 'ranking':
        logs = get_server_ranking(interaction.guild)
        if not logs:
            await interaction.response.send_message('今週のデータがありません。')
            return
        embed = discord.Embed(
            title='🏆 今週のサーバーランキング',
            color=0xF1C40F
        )
        for i, (user_name, app_name, total_minutes) in enumerate(logs):
            hours = int(total_minutes // 60)
            minutes = int(total_minutes % 60)
            embed.add_field(
                name=f'{i+1}. {user_name}',
                value=f'{app_name} - {hours}時間{minutes}分',
                inline=False
            )
        await interaction.response.send_message(embed=embed)

client.run(os.getenv('DISCORD_TOKEN'))