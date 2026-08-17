# ตัวอย่าง Discord anti-raid/anti-spam bot (Python, discord.py / py-cord)
# ติดตั้ง: pip install -U "discord.py"  หรือ pip install -U py-cord
# ตั้งค่า: แก้ค่าใน CONFIG ก่อนรัน

import discord
from discord.ext import commands, tasks
import asyncio
import re
import time
from collections import defaultdict, deque

# ========== CONFIG ==========
TOKEN = "YOUR_BOT_TOKEN_HERE"  # อย่าแชร์ token
MOD_LOG_CHANNEL = "mod-log"    # channel name สำหรับบันทึกเหตุการณ์
MUTE_ROLE_NAME = "Muted"       # role ที่มิวท์ผู้ใช้
ANTI_RAID_WINDOW = 20          # วินาที สำหรับนับการเข้าพร้อมกัน
ANTI_RAID_THRESHOLD = 5        # ถ้ามีสมาชิกเข้ามากกว่าเท่านี้ภายใน window => แจ้ง/แบน
SPAM_MESSAGE_LIMIT = 5         # ข้อความเกินภายใน SPAM_SECONDS ถือว่าเป็นสแปม
SPAM_SECONDS = 7
SPAM_MUTE_SECONDS = 300        # มิวท์เป็นเวลา (วินาที)
MASS_MENTION_THRESHOLD = 5     # ถ้ามี mentions มากกว่านี้ => ลบ/แบน
BLOCK_INVITES = True           # ลบข้อความที่มีลิงก์ invite discord
# ============================

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True  # ต้องเปิดใน dev portal ถ้าต้องอ่านเนื้อหาข้อความ

bot = commands.Bot(command_prefix="!", intents=intents)

# In-memory stores (สำหรับตัวอย่าง) — ถ้าต้องการเก็บถาวรใช้ DB
recent_joins = deque()  # list of (timestamp, member.id)
user_messages = defaultdict(lambda: deque())  # user_id -> deque of timestamps
last_message_content = {}  # user_id -> last message content
muted_timers = {}  # user_id -> unmute_time

INVITE_REGEX = re.compile(r"(discord(?:\.gg|app\.com\/invite)\/\S+)", re.IGNORECASE)

# Helpers
async def log_guild(guild: discord.Guild, msg: str):
    # หา channel ที่ตั้งชื่อไว้ แล้วส่ง log
    for ch in guild.text_channels:
        if ch.name == MOD_LOG_CHANNEL:
            try:
                await ch.send(msg)
            except Exception:
                pass
            return
    # ถ้าไม่เจอ channel ให้พิมพ์ใน console
    print(f"[{guild.name}] {msg}")

async def ensure_mute_role(guild: discord.Guild):
    role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
    if role:
        return role
    try:
        perms = discord.Permissions(send_messages=False, speak=False)
        role = await guild.create_role(name=MUTE_ROLE_NAME, permissions=perms, reason="Create mute role for anti-spam bot")
        # ปรับ channel overrides
        for ch in guild.channels:
            try:
                await ch.set_permissions(role, send_messages=False, speak=False)
            except Exception:
                pass
        return role
    except Exception as e:
        print("Failed to create mute role:", e)
        return None

async def mute_member(guild: discord.Guild, member: discord.Member, duration: int, reason: str = ""):
    role = await ensure_mute_role(guild)
    if role is None:
        return False
    try:
        await member.add_roles(role, reason=reason)
        unmute_time = time.time() + duration if duration else None
        if unmute_time:
            muted_timers[member.id] = unmute_time
        await log_guild(guild, f"Muted {member.mention} for {duration}s. Reason: {reason}")
        return True
    except Exception as e:
        print("mute error:", e)
        return False

async def unmute_member(guild: discord.Guild, member: discord.Member):
    role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
    if role and role in member.roles:
        try:
            await member.remove_roles(role, reason="Auto unmute by anti-spam bot")
            await log_guild(guild, f"Unmuted {member.mention}")
        except Exception as e:
            print("unmute error:", e)

# Background task to check unmutes
@tasks.loop(seconds=15)
async def check_unmutes():
    now = time.time()
    to_unmute = [uid for uid, t in muted_timers.items() if t <= now]
    for uid in to_unmute:
        try:
            for guild in bot.guilds:
                member = guild.get_member(uid)
                if member:
                    await unmute_member(guild, member)
        except Exception:
            pass
        muted_timers.pop(uid, None)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    check_unmutes.start()

# Anti-raid: track joins
@bot.event
async def on_member_join(member: discord.Member):
    ts = time.time()
    recent_joins.append((ts, member.id))
    # ลบ entry เก่าๆ
    while recent_joins and recent_joins[0][0] < ts - ANTI_RAID_WINDOW:
        recent_joins.popleft()
    # Check threshold
    if len(recent_joins) >= ANTI_RAID_THRESHOLD:
        # ตัวอย่างการตอบโต้: แจ้งแอดมิน, ปิดชั่วคราว (ต้องการสิทธิ์ manage_guild)
        guild = member.guild
        await log_guild(guild, f"Potential raid detected: {len(recent_joins)} joins within {ANTI_RAID_WINDOW}s.")
        # ตัวอย่าง: หา role ที่มี permission manage_guild (admins) แล้ว mention
        msg = f"⚠️ Potential raid detected: {len(recent_joins)} new joins within {ANTI_RAID_WINDOW}s. Consider enabling verifications or locking invites."
        await log_guild(guild, msg)
        # คุณอาจเพิ่มการตั้งให้ kick/ban ทุกคนที่เข้าล่าสุด — ระวังผลกระทบ false positive

# Anti-spam: rate-limit per user and mass mention protection
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    guild = message.guild
    author_id = message.author.id
    now = time.time()

    # 1) Mass mention / everyone
    if message.mention_everyone or len(message.mentions) >= MASS_MENTION_THRESHOLD:
        try:
            await message.delete()
            await log_guild(guild, f"Deleted mass-mention by {message.author.mention} in {message.channel.mention}")
            await message.channel.send(f"{message.author.mention}, mass mentions are not allowed.", delete_after=6)
            # Optionally mute/ban
            await mute_member(guild, message.author, SPAM_MUTE_SECONDS, reason="Mass mention")
        except Exception:
            pass
        return

    # 2) Block invite links
    if BLOCK_INVITES and INVITE_REGEX.search(message.content):
        try:
            await message.delete()
            await log_guild(guild, f"Deleted invite link from {message.author.mention}")
            await message.channel.send(f"{message.author.mention}, posting invite links is not allowed.", delete_after=6)
        except Exception:
            pass
        return

    # 3) Repeated content
    last = last_message_content.get(author_id)
    if last and last == message.content and len(message.content) > 5:
        # duplicate message => warn/mute
        try:
            await message.delete()
            await log_guild(guild, f"Deleted repeated message from {message.author.mention}")
            await mute_member(guild, message.author, SPAM_MUTE_SECONDS, reason="Repeated messages")
        except Exception:
            pass
        last_message_content[author_id] = message.content
        return
    last_message_content[author_id] = message.content

    # 4) Rate limit checks
    dq = user_messages[author_id]
    dq.append(now)
    # remove old
    while dq and dq[0] < now - SPAM_SECONDS:
        dq.popleft()
    if len(dq) > SPAM_MESSAGE_LIMIT:
        # action: delete recent messages from user in channel (best-effort), mute
        try:
            # ลบข้อความล่าสุดของ user ใน channel (fetch messages)
            def is_from_author(m):
                return m.author.id == author_id
            deleted = await message.channel.purge(limit=50, check=is_from_author, bulk=True)
        except Exception:
            deleted = []
        await log_guild(guild, f"Detected spam from {message.author.mention}. Deleted {len(deleted)} messages.")
        await mute_member(guild, message.author, SPAM_MUTE_SECONDS, reason="Spam rate limit exceeded")
        try:
            await message.channel.send(f"{message.author.mention}, you have been muted for spamming.", delete_after=8)
        except Exception:
            pass
        # Reset user's message queue
        user_messages[author_id].clear()
        return

    # allow commands to still work
    await bot.process_commands(message)

# Admin commands (requires manage_guild permission)
@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def setmodlog(ctx, channel_name: str):
    global MOD_LOG_CHANNEL
    MOD_LOG_CHANNEL = channel_name
    await ctx.send(f"Set mod log channel name to `{channel_name}`")

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def mute(ctx, member: discord.Member, seconds: int = SPAM_MUTE_SECONDS):
    await mute_member(ctx.guild, member, seconds, reason=f"Manual mute by {ctx.author}")
    await ctx.send(f"Muted {member.mention} for {seconds}s")

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def unmute(ctx, member: discord.Member):
    await unmute_member(ctx.guild, member)
    await ctx.send(f"Unmuted {member.mention}")

@bot.command()
@commands.has_guild_permissions(manage_guild=True)
async def status(ctx):
    await ctx.send("Anti-raid/anti-spam bot running.")

# Error handlers
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("คุณไม่มีสิทธิ์เรียกคำสั่งนี้")
    else:
        print("Command error:", error)

if __name__ == "__main__":
    bot.run(TOKEN)
