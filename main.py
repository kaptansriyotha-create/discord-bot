import os
import discord
import yt_dlp
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread

# --- Setup ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online!"
Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- Music Settings ---
ytdl_format_options = {'format': 'bestaudio/best', 'noplaylist': True}
ffmpeg_options = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f'Logged in as {bot.user}')

# --- Protection: Anti-Spam (Simple) ---
user_msgs = {}
@bot.event
async def on_message(message):
    if message.author.bot: return
    # Anti-Spam: ลบถ้าพิมพ์เกิน 5 ข้อความใน 5 วินาที
    uid = message.author.id
    if uid not in user_msgs: user_msgs[uid] = []
    user_msgs[uid].append(message.created_at.timestamp())
    user_msgs[uid] = [t for t in user_msgs[uid] if message.created_at.timestamp() - t < 5]
    if len(user_msgs[uid]) > 5:
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} อย่าสแปมข้อความค่ะ!", delete_after=3)
    await bot.process_commands(message)

# --- Moderation Commands ---
@bot.tree.command(name="ban", description="แบนสมาชิก")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "ไม่ระบุ"):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 แบน {member.name} แล้ว")

@bot.tree.command(name="kick", description="เตะสมาชิก")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "ไม่ระบุ"):
    await member.kick(reason=reason)
    await interaction.response.send_message(f"👢 เตะ {member.name} แล้ว")

@bot.tree.command(name="purge", description="ลบข้อความ")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    await interaction.channel.purge(limit=amount)
    await interaction.response.send_message(f"🧹 ลบ {amount} ข้อความแล้ว", ephemeral=True)

# --- Music Commands ---
@bot.tree.command(name="play", description="เล่นเพลง")
async def play(interaction: discord.Interaction, url: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ เข้าห้องเสียงก่อนนะ!")
    channel = interaction.user.voice.channel
    voice = await channel.connect() if not interaction.guild.voice_client else interaction.guild.voice_client
    
    await interaction.response.send_message(f"🎵 กำลังเล่น: {url}")
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
    source = discord.FFmpegPCMAudio(data['url'], **ffmpeg_options)
    voice.play(source)

@bot.tree.command(name="stop", description="หยุดเพลงและออกจากห้อง")
async def stop(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("⏹️ หยุดเพลงแล้ว")

bot.run(os.getenv('DISCORD_TOKEN'))
