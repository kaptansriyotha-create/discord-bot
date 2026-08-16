import os
import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# ==================== Keep-Alive Server ====================
app = Flask('')
@app.route('/')
def home():
    return "Bot is online!"

Thread(target=lambda: app.run(host='0.0.0.0', port=8080), daemon=True).start()

# ==================== Config & Setup ====================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ตั้งค่า YT-DLP สำหรับระบบเล่นเพลง
ytdl_format_options = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True
}
ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

# ตัวแปรเก็บประวัติการสแปมของผู้ใช้
spam_tracker = {}

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s) successfully!")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้วค่ะ!')

# ==================== ระบบ Anti-Spam 3 Level ====================
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    # ข้ามการตรวจถ้าผู้ใช้เป็นแอดมิน
    if message.author.guild_permissions.administrator:
        await bot.process_commands(message)
        return

    user_id = message.author.id
    now = datetime.utcnow()

    if user_id not in spam_tracker:
        spam_tracker[user_id] = {
            "timestamps": [],
            "warnings": 0,
            "last_warning": now
        }

    user_data = spam_tracker[user_id]
    
    # รีเซ็ตการเตือนถ้าเวลาผ่านไปเกิน 10 นาทีโดยไม่ทำผิดซ้ำ
    if (now - user_data["last_warning"]).total_seconds() > 600:
        user_data["warnings"] = 0

    # ตรวจจับข้อความที่ส่งใน 3 วินาทีล่าสุด
    user_data["timestamps"] = [t for t in user_data["timestamps"] if (now - t).total_seconds() < 3]
    user_data["timestamps"].append(now)

    # เงื่อนไขเมื่อตรวจพบการส่งรัว (มากกว่า 3 ข้อความใน 3 วินาที)
    if len(user_data["timestamps"]) > 3:
        try:
            await message.delete()
        except:
            pass

        user_data["warnings"] += 1
        user_data["last_warning"] = now
        user_data["timestamps"] = []  # รีเซ็ตการนับรอบสแปมชั่วคราว

        warn_level = user_data["warnings"]

        # Level 1: เตือนในแชท
        if warn_level == 1:
            await message.channel.send(
                f"⚠️ **[Anti-Spam Level 1]** {message.author.mention} กรุณาหยุดสแปมข้อความ! (เตือนครั้งที่ 1)",
                delete_after=5
            )

        # Level 2: Timeout 5 นาที
        elif warn_level == 2:
            try:
                await message.author.timeout(timedelta(minutes=5), reason="Anti-Spam Level 2: สแปมข้อความซ้ำ")
                await message.channel.send(
                    f"🔇 **[Anti-Spam Level 2]** {message.author.mention} ถูกระงับการพิมพ์เป็นเวลา 5 นาที เนื่องจากสแปมข้อความซ้ำ"
                )
            except Exception as e:
                await message.channel.send(f"❌ ไม่สามารถระงับการพิมพ์ {message.author.mention} ได้: {e}")

        # Level 3: Ban ออกจากเซิร์ฟเวอร์
        elif warn_level >= 3:
            try:
                await message.author.ban(reason="Anti-Spam Level 3: ทำผิดกฎสแปมครบ 3 ครั้ง")
                await message.channel.send(
                    f"🚨 **[Anti-Spam Level 3]** แบน {message.author.mention} ออกจากเซิร์ฟเวอร์ถาวรเนื่องจากสแปมข้อความขั้นรุนแรง!"
                )
            except Exception as e:
                await message.channel.send(f"❌ ไม่สามารถแบน {message.author.mention} ได้: {e}")

        return

    await bot.process_commands(message)

# ==================== Slash Commands ====================

# 1. เช็คสถานะบอทตามรูปแบบที่กำหนด
@bot.tree.command(name="สถานะ", description="เช็คสถานะการทำงานและระบบป้องกันของบอท")
async def status(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    
    embed = discord.Embed(title="📊 สถานะการทำงานของบอท", color=discord.Color.green())
    embed.add_field(name="🛡️ ระบบป้องกันอยู่เลเวล", value="Level 3 (Warn -> Timeout -> Ban)", inline=False)
    embed.add_field(name="🤖 สถานะออน", value="ออนไลน์พร้อมใช้งาน 24 ชั่วโมง", inline=False)
    embed.add_field(name="🟢 ความเร็วปิง", value=f"{latency} ms", inline=False)
    
    await interaction.response.send_message(embed=embed)

# 2. ระบบเล่นเพลงจาก YouTube Link
@bot.tree.command(name="play", description="เล่นเพลงจาก URL YouTube")
async def play(interaction: discord.Interaction, url: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ คุณต้องเชื่อมต่อกับห้องเสียงก่อนค่ะ!", ephemeral=True)

    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    if not voice_client:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        
        if 'entries' in data:
            data = data['entries'][0]

        audio_url = data['url']
        title = data.get('title', 'ไม่ทราบชื่อเพลง')

        if voice_client.is_playing():
            voice_client.stop()

        source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options)
        voice_client.play(source)

        embed = discord.Embed(title="🎵 กำลังเล่นเพลง", description=f"[{title}]({url})", color=discord.Color.blue())
        await interaction.followup.send(embed=embed)

    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการดึงเพลง: {e}")

@bot.tree.command(name="stop", description="หยุดเล่นเพลงและออกจากห้องเสียง")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await interaction.response.send_message("⏹️ หยุดเล่นเพลงและออกจากห้องเรียบร้อยแล้วค่ะ")
    else:
        await interaction.response.send_message("❌ บอทไม่ได้อยู่ในห้องเสียงค่ะ", ephemeral=True)

# ==================== Start Bot ====================
if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ ไม่พบ DISCORD_TOKEN ใน Environment Variables")
    
