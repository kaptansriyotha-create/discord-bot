import os
import sqlite3
import json
import asyncio
from datetime import datetime, timedelta
import discord
from discord.ext import commands, tasks
from discord import app_commands
import openai
from flask import Flask
from threading import Thread

# ==================== 15. ระบบความปลอดภัย & Environment Variables ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# Keep-Alive Server สำหรับ Render
app = Flask('')
@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run_web, daemon=True).start()

# ==================== 12. ระบบฐานข้อมูล (SQLite) ====================
DB_NAME = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # ตารางตั้งค่าเซิร์ฟเวอร์ (10)
    c.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_channel INTEGER,
                    goodbye_channel INTEGER,
                    mod_log_channel INTEGER,
                    announce_channel INTEGER,
                    auto_role_id INTEGER,
                    antispam_active INTEGER DEFAULT 1,
                    antiraid_active INTEGER DEFAULT 1,
                    ai_active INTEGER DEFAULT 1
                )''')
    # ตารางระบบ Warn (2)
    c.execute('''CREATE TABLE IF NOT EXISTS warns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER,
                    user_id INTEGER,
                    reason TEXT,
                    moderator_id INTEGER,
                    timestamp TEXT
                )''')
    # ตารางความจำ AI (1)
    c.execute('''CREATE TABLE IF NOT EXISTS ai_memory (
                    guild_id INTEGER,
                    user_id INTEGER,
                    role TEXT,
                    content TEXT,
                    PRIMARY KEY (guild_id, user_id, content)
                )''')
    conn.commit()
    conn.close()

init_db()

def get_setting(guild_id, column):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"SELECT {column} FROM guild_settings WHERE guild_id = ?", (guild_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else None

def set_setting(guild_id, column, value):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO guild_settings (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING", (guild_id,))
    c.execute(f"UPDATE guild_settings SET {column} = ? WHERE guild_id = ?", (value, guild_id))
    conn.commit()
    conn.close()

# ==================== Bot Configuration ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ตัวแปรจำลอง Anti-Spam / Anti-Raid ในหน่วยความจำชั่วคราว
user_msg_count = {}
join_tracker = {}

# ==================== 5. ระบบ Mod Log ====================
async def send_mod_log(guild, embed):
    log_channel_id = get_setting(guild.id, "mod_log_channel")
    if log_channel_id:
        channel = guild.get_channel(log_channel_id)
        if channel:
            await channel.send(embed=embed)

# ==================== Event Handlers ====================
@bot.event
async def on_ready():
    # 17. บังคับ Sync ให้มี Slash Commands
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Sync error: {e}")
    
    update_status.start()
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้วค่ะ!')

# 16. ระบบสถานะบอท
@tasks.loop(minutes=5)
async def update_status():
    total_members = sum(g.member_count for g in bot.guilds)
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"{len(bot.guilds)} เซิร์ฟเวอร์ | {total_members} สมาชิก | /help"
        )
    )

# 6. ระบบ Welcome / Goodbye & Auto Role
@bot.event
async def on_member_join(member):
    guild = member.guild
    # Anti-Raid System (4)
    if get_setting(guild.id, "antiraid_active") != 0:
        now = datetime.utcnow()
        joins = join_tracker.get(guild.id, [])
        joins = [t for t in joins if (now - t).seconds < 10]
        joins.append(now)
        join_tracker[guild.id] = joins
        if len(joins) > 5:
            embed = discord.Embed(title="🚨 ตรวจพบ Anti-Raid!", description=f"มีการเข้าร่วม {len(joins)} คนใน 10 วินาที", color=discord.Color.red())
            await send_mod_log(guild, embed)

    # Auto Role (6)
    role_id = get_setting(guild.id, "auto_role_id")
    if role_id:
        role = guild.get_role(role_id)
        if role:
            try: await member.add_roles(role)
            except: pass

    # Welcome Channel (6)
    w_channel_id = get_setting(guild.id, "welcome_channel")
    if w_channel_id:
        channel = guild.get_channel(w_channel_id)
        if channel:
            await channel.send(f"🎉 ยินดีต้อนรับ {member.mention} เข้าสู่ **{guild.name}**!")

    # Mod Log Member Join (5)
    embed = discord.Embed(title="📥 สมาชิกเข้าร่วม", description=f"{member.mention} ({member.name})", color=discord.Color.green())
    await send_mod_log(guild, embed)

@bot.event
async def on_member_remove(member):
    guild = member.guild
    g_channel_id = get_setting(guild.id, "goodbye_channel")
    if g_channel_id:
        channel = guild.get_channel(g_channel_id)
        if channel:
            await channel.send(f"👋 {member.name} ได้ออกจากเซิร์ฟเวอร์ไปแล้ว")

    embed = discord.Embed(title="📤 สมาชิกออกจากเซิร์ฟเวอร์", description=f"{member.name}", color=discord.Color.orange())
    await send_mod_log(guild, embed)

# 3. ระบบ Anti-Spam & 1. AI Chat
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    guild_id = message.guild.id
    user_id = message.author.id

    # 3. Anti-Spam System
    if get_setting(guild_id, "antispam_active") != 0 and not message.author.guild_permissions.administrator:
        now = datetime.now().timestamp()
        msgs = user_msg_count.get(user_id, [])
        msgs = [t for t in msgs if now - t < 5]
        msgs.append(now)
        user_msg_count[user_id] = msgs
        if len(msgs) > 5:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention} กรุณาลดการส่งข้อความรัว (Anti-Spam)", delete_after=3)
            return

    # 1. ระบบ AI Chat (ทำงานเมื่อพูดคุยกับบอท หรือแท็กบอท)
    if bot.user.mentioned_in(message) and get_setting(guild_id, "ai_active") != 0:
        if not OPENAI_API_KEY:
            await message.channel.send("❌ ระบบ AI ยังไม่ได้ตั้งค่า OPENAI_API_KEY")
            return
        
        async with message.channel.typing():
            prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT role, content FROM ai_memory WHERE guild_id = ? AND user_id = ? ORDER BY rowid DESC LIMIT 6", (guild_id, user_id))
            history = c.fetchall()[::-1]
            
            messages = [{"role": "system", "content": "คุณคือบอทผู้ช่วยภาษาไทยที่สุภาพ เขียนโค้ดและตอบคำถามทั่วไปได้"}]
            for r, cnt in history:
                messages.append({"role": r, "content": cnt})
            messages.append({"role": "user", "content": prompt})

            try:
                response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages, max_tokens=500)
                reply = response.choices[0].message.content
                
                # บันทึกความจำลง DB
                c.execute("INSERT INTO ai_memory VALUES (?, ?, 'user', ?)", (guild_id, user_id, prompt))
                c.execute("INSERT INTO ai_memory VALUES (?, ?, 'assistant', ?)", (guild_id, user_id, reply))
                conn.commit()
                conn.close()

                await message.reply(reply)
            except Exception as e:
                await message.reply(f"❌ ระบบ AI ขัดข้อง: {e}")
        return

    await bot.process_commands(message)

# ==================== 17. Slash Commands (คำสั่ง / ทั้งหมด) ====================

# 9. ระบบข้อมูล
@bot.tree.command(name="help", description="ดูเมนูช่วยเหลือและคำสั่งทั้งหมด")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 รายการคำสั่งของบอท", color=discord.Color.blue())
    embed.add_field(name="🛡️ จัดการผู้ใช้", value="`/ban` `/kick` `/timeout` `/warn` `/warns` `/clear_warns` `/purge`", inline=False)
    embed.add_field(name="⚙️ ตั้งค่าเซิร์ฟเวอร์", value="`/setup_welcome` `/setup_logs` `/setup_autorole` `/toggle_antispam`", inline=False)
    embed.add_field(name="📢 ประกาศ & ทั่วไป", value="`/announce` `/ping` `/server` `/status`", inline=False)
    embed.add_field(name="🤖 AI Chat", value="แท็กหาบอทเพื่อพูดคุย ถ่ายทอดความรู้ หรือแก้โค้ดได้ทันที", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ping", description="เช็คความเร็วปิงของบอท")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 พิง: `{round(bot.latency * 1000)} ms`")

@bot.tree.command(name="server", description="ดูข้อมูลเซิร์ฟเวอร์นี้")
async def server_info(interaction: discord.Interaction):
    g = interaction.guild
    embed = discord.Embed(title=f"📊 ข้อมูลเซิร์ฟเวอร์ {g.name}", color=discord.Color.purple())
    embed.add_field(name="👑 เจ้าของ", value=g.owner.mention)
    embed.add_field(name="👥 สมาชิกทั้งหมด", value=str(g.member_count))
    embed.add_field(name="🆔 Guild ID", value=str(g.id))
    await interaction.response.send_message(embed=embed)

# 2. ระบบจัดการสมาชิก & 11. Permission Check
@bot.tree.command(name="ban", description="แบนสมาชิกออกจากเซิร์ฟเวอร์")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "ไม่ได้ระบุ"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🚨 แบน {member.mention} เรียบร้อยแล้ว (สาเหตุ: {reason})")

@bot.tree.command(name="kick", description="เตะสมาชิกออกจากเซิร์ฟเวอร์")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "ไม่ได้ระบุ"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 เตะ {member.mention} เรียบร้อยแล้ว (สาเหตุ: {reason})")

@bot.tree.command(name="timeout", description="ระงับการพิมพ์สมาชิก (เป็นนาที)")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "ไม่ได้ระบุ"):
    duration = timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"🔇 ระงับ {member.mention} เป็นเวลา {minutes} นาที")

@bot.tree.command(name="purge", description="ลบข้อความรวดเร็ว")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 ลบข้อความไปทั้งหมด {len(deleted)} ข้อความ", delete_after=3)

@bot.tree.command(name="warn", description="เตือนสมาชิก")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT INTO warns (guild_id, user_id, reason, moderator_id, timestamp) VALUES (?, ?, ?, ?, ?)",
              (interaction.guild.id, member.id, reason, interaction.user.id, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"⚠️ ตักเตือน {member.mention} เรียบร้อย (สาเหตุ: {reason})")

@bot.tree.command(name="warns", description="ดูประวัติการเตือนของสมาชิก")
async def view_warns(interaction: discord.Interaction, member: discord.Member):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT reason, timestamp FROM warns WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
    records = c.fetchall()
    conn.close()
    
    if not records:
        await interaction.response.send_message(f"✅ {member.mention} ไม่เคยมีประวัติการเตือน")
        return

    embed = discord.Embed(title=f"⚠️ ประวัติการเตือนของ {member.name}", color=discord.Color.gold())
    for r, t in records:
        embed.add_field(name=f"📅 {t}", value=f"สาเหตุ: {r}", inline=False)
    await interaction.response.send_message(embed=embed)

# 8. ระบบประกาศ
@bot.tree.command(name="announce", description="ส่งประกาศแบบ Embed ไปยังห้องที่เลือก")
@app_commands.checks.has_permissions(administrator=True)
async def announce(interaction: discord.Interaction, channel: discord.TextChannel, title: str, message: str, image_url: str = None):
    embed = discord.Embed(title=title, description=message, color=discord.Color.blue())
    if image_url:
        embed.set_image(url=image_url)
    embed.set_footer(text=f"ประกาศโดย {interaction.user.name}")
    await channel.send(embed=embed)
    await interaction.response.send_message(f"✅ ส่งประกาศไปยัง {channel.mention} เรียบร้อย!", ephemeral=True)

# 10. ระบบตั้งค่าเซิร์ฟเวอร์
@bot.tree.command(name="setup_welcome", description="ตั้งค่าห้องต้อนรับ")
@app_commands.checks.has_permissions(administrator=True)
async def setup_welcome(interaction: discord.Interaction, channel: discord.TextChannel):
    set_setting(interaction.guild.id, "welcome_channel", channel.id)
    await interaction.response.send_message(f"✅ ตั้งค่าห้องต้อนรับเป็น {channel.mention}")

@bot.tree.command(name="setup_logs", description="ตั้งค่าห้อง Mod Log")
@app_commands.checks.has_permissions(administrator=True)
async def setup_logs(interaction: discord.Interaction, channel: discord.TextChannel):
    set_setting(interaction.guild.id, "mod_log_channel", channel.id)
    await interaction.response.send_message(f"✅ ตั้งค่าห้อง Mod Log เป็น {channel.mention}")

# 13. ระบบ Error Handler (ป้องกันบอทดับ)
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้งานคำสั่งนี้ค่ะ", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาดในระบบ: {error}", ephemeral=True)

# 14. ระบบ Recovery & Start
def main():
    while True:
        try:
            if not DISCORD_TOKEN:
                print("❌ กรุณาตั้งค่า DISCORD_TOKEN ใน Environment Variables")
                break
            bot.run(DISCORD_TOKEN)
        except Exception as e:
            print(f"🚨 ระบบขัดข้อง บอทกำลังพยายามกู้คืน... Error: {e}")
            asyncio.sleep(5)

if __name__ == "__main__":
    main()
# รันบอท
bot.run(os.getenv('DISCORD_TOKEN
