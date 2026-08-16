import os
import asyncio
import random
from collections import defaultdict
import discord
from discord.ext import commands
import yt_dlp
from flask import Flask
from threading import Thread

# ================= 🌐 ระบบเปิดออนไลน์ 24 ชั่วโมง =================
app = Flask('')
@app.route('/')
def home():
    return "บอททำงานปกติแล้วค่ะ!"

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()

# ================= 🤖 ตั้งค่าบอท =================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ตัวแปรเก็บการตั้งค่าระบบต่างๆ
SPAM_LEVEL = 1
ANNOUNCE_CHANNEL_ID = None
CHAT_CHANNEL_ID = None
WELCOME_CHANNEL_ID = None
LOG_CHANNEL_ID = None

user_messages = defaultdict(list)
user_memory = defaultdict(list)

# ================= 🛡️ 1. ระบบกันยิงดิส (Anti-Raid) =================
@bot.event
async def on_member_join(member):
    if member.bot:
        await member.ban(reason="ระบบกันยิงดิส: บล็อกบอทไม่อนุญาต")
        if LOG_CHANNEL_ID:
            log_ch = bot.get_channel(LOG_CHANNEL_ID)
            if log_ch:
                await log_ch.send(f"🛡️ **[กันยิงดิส]** แบนบอทแปลกปลอม: `{member.name}`")
        return

    if WELCOME_CHANNEL_ID:
        welcome_ch = bot.get_channel(WELCOME_CHANNEL_ID)
        if welcome_ch:
            embed = discord.Embed(
                title="💖 ยินดีต้อนรับสมาชิกใหม่ค่ะ!",
                description=f"ยินดีต้อนรับคุณ {member.mention} เข้าสู่เซิร์ฟเวอร์นะคะ! ขอให้มีความสุขน้า 🥰",
                color=0xff69b4
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await welcome_ch.send(embed=embed)

@bot.event
async def on_member_remove(member):
    if WELCOME_CHANNEL_ID and not member.bot:
        welcome_ch = bot.get_channel(WELCOME_CHANNEL_ID)
        if welcome_ch:
            await welcome_ch.send(f"👋 คุณ **{member.display_name}** ได้ออกจากเซิร์ฟเวอร์ไปแล้ว ไว้เจอกันใหม่นะคะ...")

# ================= 📜 2. ระบบบันทึกการกระทำ (Logs) =================
@bot.event
async def on_user_update(before, after):
    if LOG_CHANNEL_ID and before.name != after.name:
        log_ch = bot.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(f"📝 **[เปลี่ยนชื่อบัญชี]** `{before.name}` ➡️ `{after.name}` ({after.mention})")

@bot.event
async def on_member_update(before, after):
    if LOG_CHANNEL_ID and before.display_name != after.display_name:
        log_ch = bot.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            await log_ch.send(f"📝 **[เปลี่ยนชื่อในเซิร์ฟ]** `{before.display_name}` ➡️ `{after.display_name}` ({after.mention})")

@bot.event
async def on_voice_state_update(member, before, after):
    if not LOG_CHANNEL_ID or member.bot:
        return
    log_ch = bot.get_channel(LOG_CHANNEL_ID)
    if not log_ch:
        return

    if before.channel is None and after.channel is not None:
        await log_ch.send(f"🔊 **[เข้าห้องเสียง]** {member.mention} เข้าห้อง **{after.channel.name}**")
    elif before.channel is not None and after.channel is None:
        await log_ch.send(f"🔇 **[ออกจากห้องเสียง]** {member.mention} ออกจากห้อง **{before.channel.name}**")
    elif before.channel != after.channel:
        await log_ch.send(f"🔄 **[ย้ายห้องเสียง]** {member.mention} ย้ายไปห้อง **{after.channel.name}**")

# ================= 🛡️ 3. ระบบกันสแปม & AI ฟีลแฟน =================
SWEET_RESPONSES = [
    "เค้าอยู่นี่แล้วค่ะตัวเอง มีอะไรให้ช่วยไหมคะ? 💖",
    "คิดถึงจังเลย วันนี้เหนื่อยไหมคะเค้าส่งกำลังใจให้นะ 🥰",
    "ว่าไงคะคนเก่ง กินข้าวหรือยังเอ่ย? 🍳",
    "เค้าจำได้นะว่าตัวเองชอบคุยกับเค้า พิมพ์มาได้เลยค่ะ 💕",
    "กอดๆ นะคะคนดี เค้าพร้อมฟังตัวเองเสมอเลย 🤗"
]

@bot.event
async def on_message(message):
    global SPAM_LEVEL
    if message.author.bot:
        return

    if CHAT_CHANNEL_ID and message.channel.id == CHAT_CHANNEL_ID and not message.content.startswith('!'):
        uid = message.author.id
        user_memory[uid].append(message.content)
        if len(user_memory[uid]) > 5:
            user_memory[uid].pop(0)

        reply = random.choice(SWEET_RESPONSES)
        await message.channel.send(f"{message.author.mention} {reply}")

    user_id = message.author.id
    loop = asyncio.get_event_loop()
    current_time = loop.time()

    user_messages[user_id] = [t for t in user_messages[user_id] if current_time - t < 5]
    user_messages[user_id].append(current_time)

    if len(user_messages[user_id]) > 5:
        await message.delete()
        if SPAM_LEVEL == 1:
            await message.channel.send(f'⚠️ {message.author.mention} อย่าส่งข้อความสแปมสิคะเค้าตกใจหมดเลย!', delete_after=3)
        elif SPAM_LEVEL == 2:
            await message.author.kick(reason="สแปมข้อความ (Level 2)")
            await message.channel.send(f'🚨 เตะ {message.author.mention} ออกจากเซิร์ฟเวอร์เนื่องจากสแปม!')
        elif SPAM_LEVEL == 3:
            await message.author.ban(reason="สแปมข้อความรุนแรง (Level 3)")
            await message.channel.send(f'⛔ แบน {message.author.mention} เรียบร้อยแล้วค่ะเนื่องจากสแปมรุนแรง!')
        return

    await bot.process_commands(message)

# ================= ⚙️ 4. คำสั่งตั้งค่าสำหรับผู้ดูแล (Admin) =================
@bot.command()
@commands.has_permissions(administrator=True)
async def antispam(ctx, mode: str, level: int):
    global SPAM_LEVEL
    if mode == "level" and 1 <= level <= 3:
        SPAM_LEVEL = level
        await ctx.send(f"✅ ตั้งค่าระบบกันสแปมเป็น **Level {level}** เรียบร้อยแล้วค่ะ")

@bot.command()
@commands.has_permissions(administrator=True)
async def setannounce(ctx, channel: discord.TextChannel):
    global ANNOUNCE_CHANNEL_ID
    ANNOUNCE_CHANNEL_ID = channel.id
    await ctx.send(f"✅ ตั้งค่าห้องประกาศเป็น {channel.mention} เรียบร้อยแล้วค่ะ")

@bot.command()
@commands.has_permissions(administrator=True)
async def announce(ctx, *, message: str):
    if not ANNOUNCE_CHANNEL_ID:
        await ctx.send("❌ ยังไม่ได้ตั้งค่าห้องประกาศ กรุณาใช้คำสั่ง `!setannounce` ก่อนค่ะ")
        return
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    embed = discord.Embed(title="📢 ประกาศสำคัญ", description=message, color=0xff69b4)
    embed.set_footer(text=f"ประกาศโดย {ctx.author.display_name}")
    await channel.send(embed=embed)
    await ctx.send("✅ ส่งประกาศเรียบร้อยแล้วค่ะ")

@bot.command()
@commands.has_permissions(administrator=True)
async def setchat(ctx, channel: discord.TextChannel):
    global CHAT_CHANNEL_ID
    CHAT_CHANNEL_ID = channel.id
    await ctx.send(f"✅ ตั้งค่าห้องคุยฟีลแฟนเป็น {channel.mention} เรียบร้อยแล้วค่ะ")

@bot.command()
@commands.has_permissions(administrator=True)
async def setwelcome(ctx, channel: discord.TextChannel):
    global WELCOME_CHANNEL_ID
    WELCOME_CHANNEL_ID = channel.id
    await ctx.send(f"✅ ตั้งค่าห้องต้อนรับเป็น {channel.mention} เรียบร้อยแล้วค่ะ")

@bot.command()
@commands.has_permissions(administrator=True)
async def setlog(ctx, channel: discord.TextChannel):
    global LOG_CHANNEL_ID
    LOG_CHANNEL_ID = channel.id
    await ctx.send(f"✅ ตั้งค่าห้องบันทึกเหตุการณ์เป็น {channel.mention} เรียบร้อยแล้วค่ะ")

# ================= 🎵 5. ระบบเพลง (สมาชิกทั่วไปใช้ได้) =================
YTDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': True, 'quiet': True}
FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

@bot.command()
async def play(ctx, url: str):
    if not ctx.author.voice:
        await ctx.send("❌ ตัวเองต้องเข้าห้องเสียงก่อนนะคะเค้าถึงจะไปร้องเพลงให้ฟังได้")
        return
    channel = ctx.author.voice.channel
    if not ctx.voice_client:
        await channel.connect()

    async with ctx.typing():
        info = ytdl.extract_info(url, download=False)
        url2 = info['url']
        title = info.get('title', 'เพลง')
        source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
        ctx.voice_client.play(source)

    await ctx.send(f'🎶 กำลังเปิดเพลง: **{title}** ให้ฟังนะคะ ❤️')

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ หยุดเล่นเพลงเรียบร้อยแล้วค่ะ")

# ================= 📊 6. เช็คสถานะบอท & เมนูช่วย =================
@bot.command()
async def สถานะ(ctx):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="📊 สถานะการทำงานของบอท", color=0x00ff00)
    embed.add_field(name="🟢 ความเร็วปิง (Ping)", value=f"`{latency} ms`", inline=True)
    embed.add_field(name="🛡️ เลเวลกันสแปม", value=f"`Level {SPAM_LEVEL}`", inline=True)
    embed.add_field(name="🤖 สถานะบอท", value="`ออนไลน์พร้อมใช้งาน 24 ชม.`", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def ช่วยเหลือ(ctx):
    embed = discord.Embed(title="💖 เมนูช่วยเหลือบอทภาษาไทย", color=0xff69b4)
    embed.add_field(name="🎵 คำสั่งสำหรับสมาชิกทั่วไป", value="`!play <ลิงก์>` - เปิดเพลง\n`!stop` - หยุดเปิดเพลง\n`!สถานะ` - เช็คความเร็วบอท", inline=False)
    embed.add_field(name="⚙️ คำสั่งสำหรับผู้ดูแลระบบ (Admin)", value="`!antispam level <1-3>` - ปรับระดับกันสแปม\n`!setannounce #ห้อง` - ตั้งห้องประกาศ\n`!announce <ข้อความ>` - ส่งประกาศ\n`!setchat #ห้อง` - ตั้งห้องคุยแฟน\n`!setwelcome #ห้อง` - ตั้งห้องต้อนรับ\n`!setlog #ห้อง` - ตั้งห้องบันทึกการกระทำ", inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้วค่ะ!')

bot.run(os.getenv('DISCORD_TOKEN'))
import os
import discord
from discord.ext import commands
from discord import app_commands

# ตั้งค่า Intents และสร้างตัวแปร bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# สั่ง Sync คำสั่ง Slash Command เข้า Discord ตอนบอทออนไลน์
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    print(f'บอท {bot.user} ออนไลน์พร้อมใช้งานแล้วค่ะ!')

# ==================== คำสั่ง Slash Commands (ใช้ /) ====================

@bot.tree.command(name="สถานะ", description="เช็คสถานะการทำงานของบอท")
async def status(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(title="📊 สถานะการทำงานของบอท", color=discord.Color.green())
    embed.add_field(name="🟢 ความเร็วปิง (Ping)", value=f"{latency} ms", inline=False)
    embed.add_field(name="🛡️ เลเวลกันสแปม", value="Level 1", inline=False)
    embed.add_field(name="🤖 สถานะบอท", value="`ออนไลน์พร้อมใช้งาน 24 ชม.`", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ช่วยเหลือ", description="ดูเมนูช่วยเหลือและคำสั่งทั้งหมด")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="💖 เมนูช่วยเหลือบอท", color=discord.Color.blue())
    embed.add_field(name="🎵 คำสั่งสำหรับสมาชิกทั่วไป", value="`/สถานะ` - เช็คสถานะบอท", inline=False)
    embed.add_field(name="⚙️ คำสั่งสำหรับผู้ดูแลระบบ", value="ตั้งค่าระบบเพิ่มเติม", inline=False)
    
    await interaction.response.send_message(embed=embed)

# รันบอทด้วย Token จาก Environment Variable
bot.run(os.getenv('DISCORD_TOKEN'))
    
