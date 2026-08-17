import os
import time
import asyncio
import discord

from collections import defaultdict, deque
from discord.ext import commands

# ============================================================
# CONFIG
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# จำนวนข้อความสูงสุดที่ส่งได้ภายในช่วงเวลา
SPAM_MESSAGE_LIMIT = 5
SPAM_TIME_WINDOW = 5

# จำนวนครั้งที่เตือนก่อน Timeout
MAX_WARNINGS = 2

# Timeout คนที่สแปม
TIMEOUT_SECONDS = 60

# กันข้อความซ้ำ
DUPLICATE_LIMIT = 3

# กัน Mention @everyone / @here
MAX_MENTIONS = 5

# กัน Raid สมาชิกเข้าเซิร์ฟเวอร์จำนวนมาก
RAID_JOIN_LIMIT = 8
RAID_TIME_WINDOW = 10


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# MEMORY
# ============================================================

# เก็บเวลาที่แต่ละคนส่งข้อความ
message_history = defaultdict(deque)

# เก็บข้อความล่าสุดของแต่ละคน
last_messages = defaultdict(deque)

# จำนวน Warning
warnings = defaultdict(int)

# เก็บเวลาสมาชิกเข้าเซิร์ฟเวอร์
join_history = defaultdict(deque)


# ============================================================
# CHECK ADMIN
# ============================================================

def is_staff(member: discord.Member):

    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_messages
    )


# ============================================================
# DELETE MESSAGE
# ============================================================

async def delete_message(message):

    try:
        await message.delete()
    except (
        discord.NotFound,
        discord.Forbidden,
        discord.HTTPException
    ):
        pass


# ============================================================
# TIMEOUT USER
# ============================================================

async def timeout_user(member):

    try:

        until = discord.utils.utcnow() + discord.timedelta(
            seconds=TIMEOUT_SECONDS
        )

        await member.timeout(
            until,
            reason="Anti-Spam"
        )

    except (
        discord.Forbidden,
        discord.HTTPException
    ):
        pass


# ============================================================
# ANTI SPAM
# ============================================================

async def anti_spam(message):

    if message.author.bot:
        return False

    if not message.guild:
        return False

    member = message.author

    # Admin / Staff ไม่โดนระบบ
    if is_staff(member):
        return False

    user_id = member.id
    now = time.monotonic()

    history = message_history[user_id]

    # ลบข้อมูลเก่าที่เกินช่วงเวลา
    while history and now - history[0] > SPAM_TIME_WINDOW:
        history.popleft()

    history.append(now)

    # ========================================================
    # ตรวจจับส่งข้อความรัว
    # ========================================================

    if len(history) > SPAM_MESSAGE_LIMIT:

        await delete_message(message)

        warnings[user_id] += 1

        try:
            await message.channel.send(
                f"⚠️ {member.mention} ส่งข้อความเร็วเกินไป",
                delete_after=5
            )
        except:
            pass

        # ถึงจำนวน Warning ที่กำหนด
        if warnings[user_id] >= MAX_WARNINGS:

            await timeout_user(member)

            warnings[user_id] = 0

        return True

    # ========================================================
    # ตรวจข้อความซ้ำ
    # ========================================================

    content = message.content.strip().lower()

    if content:

        messages = last_messages[user_id]

        messages.append(content)

        while len(messages) > DUPLICATE_LIMIT:
            messages.popleft()

        if (
            len(messages) == DUPLICATE_LIMIT
            and len(set(messages)) == 1
        ):

            await delete_message(message)

            warnings[user_id] += 1

            try:
                await message.channel.send(
                    f"⚠️ {member.mention} ห้ามส่งข้อความซ้ำ",
                    delete_after=5
                )
            except:
                pass

            if warnings[user_id] >= MAX_WARNINGS:

                await timeout_user(member)

                warnings[user_id] = 0

            return True

    # ========================================================
    # ตรวจ Mention จำนวนมาก
    # ========================================================

    total_mentions = (
        len(message.mentions)
        + len(message.role_mentions)
    )

    if message.mention_everyone:
        total_mentions += 2

    if total_mentions >= MAX_MENTIONS:

        await delete_message(message)

        warnings[user_id] += 1

        if warnings[user_id] >= MAX_WARNINGS:

            await timeout_user(member)

            warnings[user_id] = 0

        return True

    return False


# ============================================================
# ANTI RAID
# ============================================================

async def anti_raid(member):

    if member.bot:
        return

    guild_id = member.guild.id

    now = time.monotonic()

    history = join_history[guild_id]

    # ลบข้อมูลเก่า
    while history and now - history[0] > RAID_TIME_WINDOW:
        history.popleft()

    history.append(now)

    # ========================================================
    # ตรวจสมาชิกเข้าเยอะผิดปกติ
    # ========================================================

    if len(history) >= RAID_JOIN_LIMIT:

        # แจ้งเจ้าของ / ผู้ดูแลเซิร์ฟเวอร์
        try:

            owner = member.guild.owner

            if owner:

                await owner.send(
                    f"🚨 **ตรวจพบความเสี่ยง Raid**\n"
                    f"เซิร์ฟเวอร์: {member.guild.name}\n"
                    f"มีสมาชิกเข้า {len(history)} คน "
                    f"ภายใน {RAID_TIME_WINDOW} วินาที"
                )

        except:
            pass

        # ====================================================
        # เปิดโหมด Raid Protection
        # ====================================================

        try:

            for channel in member.guild.text_channels:

                if channel.permissions_for(
                    member.guild.me
                ).manage_messages:

                    # ไม่ปิดห้องโดยอัตโนมัติ
                    # เพื่อป้องกันการล็อกเซิร์ฟเวอร์ผิดพลาด
                    pass

        except:
            pass


# ============================================================
# MESSAGE EVENT
# ============================================================

@bot.event
async def on_message(message):

    try:

        blocked = await anti_spam(message)

        if blocked:
            return

        await bot.process_commands(message)

    except Exception as error:

        print(
            f"[Anti-Spam Error] {error}"
        )


# ============================================================
# MEMBER JOIN EVENT
# ============================================================

@bot.event
async def on_member_join(member):

    try:

        await anti_raid(member)

    except Exception as error:

        print(
            f"[Anti-Raid Error] {error}"
        )


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print("=" * 50)

    print(
        f"✅ Bot Online: {bot.user}"
    )

    print(
        f"🛡️ Anti-Spam: ON"
    )

    print(
        f"🛡️ Anti-Raid: ON"
    )

    print(
        f"📡 Servers: {len(bot.guilds)}"
    )

    print("=" * 50)


# ============================================================
# STATUS COMMAND
# ============================================================

@bot.command()
@commands.has_permissions(administrator=True)
async def security(ctx):

    embed = discord.Embed(
        title="🛡️ ระบบรักษาความปลอดภัย",
        description=(
            "ระบบป้องกันของบอทกำลังทำงาน\n\n"
            "🟢 Anti-Spam: เปิด\n"
            "🟢 Anti-Raid: เปิด\n"
            "🟢 Duplicate Protection: เปิด\n"
            "🟢 Mention Protection: เปิด"
        ),
        color=discord.Color.green()
    )

    await ctx.send(embed=embed)


# ============================================================
# ERROR HANDLER
# ============================================================

@bot.event
async def on_error(event, *args, **kwargs):

    print(
        f"[Discord Error] {event}"
    )


# ============================================================
# START BOT
# ============================================================

if not DISCORD_TOKEN:

    raise RuntimeError(
        "ไม่พบ DISCORD_TOKEN ใน Environment Variables"
    )


bot.run(DISCORD_TOKEN)
