import os
import discord
import asyncio
import random
import yt_dlp
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread

# ตั้งค่า Intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ตัวแปรระบบต้อนรับ
welcome_config = {
    "message": "ยินดีต้อนรับคุณ {user} เข้าสู่ {server} นะครับ! 🎉",
    "channel_id": None
}

# ระบบ Web Server (สำหรับ Render)
app = Flask('')
@app.route('/')
def home():
    return "บอททำงานปกติแล้วค่ะ!"
def run():
    app.run(host='0.0.0.0', port=8080)
Thread(target=run).start()

# เหตุการณ์เมื่อบอทออนไลน์
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing: {e}")
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้วค่ะ!')

# ระบบต้อนรับสมาชิกใหม่
@bot.event
async def on_member_join(member):
    if welcome_config["channel_id"]:
        channel = member.guild.get_channel(welcome_config["channel_id"])
        if channel:
            msg = welcome_config["message"].format(user=member.mention, server=member.guild.name)
            await channel.send(msg)

# ==================== Slash Commands (คำสั่ง /) ====================

@bot.tree.command(name="สถานะ", description="เช็คสถานะการทำงานของบอท")
async def status(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="📊 สถานะบอท", color=discord.Color.green())
    embed.add_field(name="🟢 ความเร็วปิง", value=f"{latency} ms", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ตั้งค่าต้อนรับ", description="ปรับแต่งข้อความต้อนรับสมาชิกใหม่")
async def set_welcome(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    welcome_config["channel_id"] = channel.id
    welcome_config["message"] = message
    await interaction.response.send_message(f"✅ ตั้งค่าเรียบร้อย! ส่งไปที่ {channel.mention}")

@bot.tree.command(name="play", description="เล่นเพลงจาก YouTube")
async def play(interaction: discord.Interaction, url: str):
    await interaction.response.send_message(f"🎵 กำลังเพิ่มเพลง: {url}")
    # (เพิ่มโค้ดเล่นเพลงตามโครงสร้างเดิมของคุณที่นี่)

@bot.tree.command(name="stop", description="หยุดเพลงและออกจากห้องเสียง")
async def stop(interaction: discord.Interaction):
    if interaction.user.voice:
        await interaction.user.voice.channel.disconnect()
        await interaction.response.send_message("⏹️ หยุดเพลงเรียบร้อยแล้วค่ะ")
    else:
        await interaction.response.send_message("❌ คุณไม่ได้อยู่ในห้องเสียง!")

# รันบอท
bot.run(os.getenv('DISCORD_TOKEN'))
