# ============================================================
# Grok & ChatGPT RULES FOR THIS FILE (DO NOT VIOLATE)
#
# • Use ONLY these sections, in this exact order:
#   ############### IMPORTS ###############
#   ############### CONSTANTS & CONFIG ###############
#   ############### GLOBAL STATE / STORAGE ###############
#   ############### HELPER FUNCTIONS ###############
#   ############### VIEWS / UI COMPONENTS ###############
#   ############### AUTOCOMPLETE FUNCTIONS ###############
#   ############### BACKGROUND TASKS & SCHEDULERS ###############
#   ############### EVENT HANDLERS ###############
#   ############### COMMAND GROUPS ###############
#   ############### ON_READY & BOT START ###############
# 
# • Do NOT add any other sections.
# • Do NOT add comments, notes, or explanations inside the code.
# ============================================================

############### IMPORTS ###############
import discord
import os
import asyncio
import aiohttp
import json
from datetime import datetime
from discord import TextChannel

############### CONSTANTS & CONFIG ###############
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

DEBUG_GUILD_ID = int(os.getenv("DEBUG_GUILD_ID"))
bot = discord.Bot(intents=intents, debug_guilds=[DEBUG_GUILD_ID])

WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID"))
ROLE_TO_WATCH = int(os.getenv("ROLE_TO_WATCH"))
WELCOME_TEXT = os.getenv("WELCOME_TEXT")
BOOST_TEXT = os.getenv("BOOST_TEXT")
VIP_TEXT = os.getenv("VIP_TEXT")
MEMBER_JOIN_ROLE_ID = int(os.getenv("MEMBER_JOIN_ROLE_ID"))
BOT_JOIN_ROLE_ID = int(os.getenv("BOT_JOIN_ROLE_ID"))
AUTO_DELETE_CHANNEL_IDS = [int(x.strip()) for x in os.getenv("AUTO_DELETE_CHANNEL_IDS", "").split(",") if x.strip().isdigit()]
DELETE_DELAY_SECONDS = int(os.getenv("DELETE_DELAY_SECONDS"))

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
TWITCH_CHANNELS = [c.strip().lower() for c in os.getenv("TWITCH_CHANNELS", "").split(",") if c.strip()]
TWITCH_ANNOUNCE_CHANNEL_ID = int(os.getenv("TWITCH_ANNOUNCE_CHANNEL_ID"))
TWITCH_EMOJI = os.getenv("TWITCH_EMOJI")

REACTION_ROLE_MESSAGE_ID = int(os.getenv("REACTION_ROLE_MESSAGE_ID"))
reaction_roles = {}
_raw_pairs = os.getenv("REACTION_ROLES", "")
if _raw_pairs:
    for pair in _raw_pairs.split(","):
        if ":" in pair:
            emoji_raw, role_id = pair.split(":", 1)
            emoji_raw = emoji_raw.strip()
            role_id = role_id.strip()

            if emoji_raw.startswith("<") and emoji_raw.endswith(">"):
                try:
                    parts = emoji_raw.strip("<>").split(":")
                    name = parts[-2]
                    key = name
                except:
                    key = emoji_raw
            else:
                key = emoji_raw

            reaction_roles[key] = int(role_id)

MOD_LOG_THREAD_ID = int(os.getenv("MOD_LOG_THREAD_ID"))
BOT_LOG_CHANNEL_ID = int(os.getenv("BOT_LOG_CHANNEL_ID", "0"))

DEAD_CHAT_ROLE_ID = int(os.getenv("DEAD_CHAT_ROLE_ID", "0"))
DEAD_CHAT_CHANNEL_IDS = [int(x.strip()) for x in os.getenv("DEAD_CHAT_CHANNEL_IDS", "").split(",") if x.strip().isdigit()]
DEAD_CHAT_IDLE_SECONDS = int(os.getenv("DEAD_CHAT_IDLE_SECONDS", "600"))
DEAD_CHAT_COOLDOWN_SECONDS = int(os.getenv("DEAD_CHAT_COOLDOWN_SECONDS", "0"))
IGNORE_MEMBER_IDS = {int(x.strip()) for x in os.getenv("IGNORE_MEMBER_IDS", "").split(",") if x.strip().isdigit()}
MONTH_CHOICES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
MONTH_TO_NUM = {name: i for i, name in enumerate(MONTH_CHOICES, start=1)}

STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "0"))

PRIZE_EMOJI = os.getenv("PRIZE_EMOJI", "")
_raw_prize_defs = os.getenv("PRIZE_DEFS", "")
if _raw_prize_defs:
    PRIZE_DEFS = json.loads(_raw_prize_defs)
else:
    PRIZE_DEFS = {}

############### GLOBAL STATE / STORAGE ###############
twitch_access_token: str | None = None
twitch_live_state: dict[str, bool] = {}
twitch_state_storage_message_id: int | None = None

dead_current_holder_id: int | None = None
dead_last_notice_message_ids: dict[int, int | None] = {}
dead_last_win_time: dict[int, datetime] = {}
deadchat_last_times: dict[int, str] = {}
deadchat_storage_message_id: int | None = None
deadchat_state_storage_message_id: int | None = None
movie_prize_storage_message_id: int | None = None
nitro_prize_storage_message_id: int | None = None
steam_prize_storage_message_id: int | None = None
movie_scheduled_prizes: list[dict] = []
nitro_scheduled_prizes: list[dict] = []
steam_scheduled_prizes: list[dict] = []

sticky_messages: dict[int, int] = {}
sticky_texts: dict[int, str] = {}
sticky_storage_message_id: int | None = None


############### HELPER FUNCTIONS ###############
async def log_to_thread(content: str):
    channel = bot.get_channel(MOD_LOG_THREAD_ID)
    if not channel:
        return
    try:
        await channel.send(content)
    except Exception:
        pass

async def log_to_bot_channel(content: str):
    if BOT_LOG_CHANNEL_ID == 0:
        return await log_to_thread(f"[BOT] {content}")
    channel = bot.get_channel(BOT_LOG_CHANNEL_ID)
    if not channel:
        return
    try:
        await channel.send(content)
    except Exception:
        pass

async def init_sticky_storage():
    global sticky_storage_message_id
    if STORAGE_CHANNEL_ID == 0:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return
    storage_msg = None
    async for msg in ch.history(limit=50, oldest_first=True):
        if msg.author == bot.user and msg.content.startswith("STICKY_DATA:"):
            storage_msg = msg
            break
    if not storage_msg:
        await log_to_bot_channel("Sticky storage message not found → Run /sticky_init first")
        return
    sticky_storage_message_id = storage_msg.id
    data_str = storage_msg.content[len("STICKY_DATA:"):]
    if not data_str.strip():
        return
    try:
        data = json.loads(data_str)
        sticky_texts.clear()
        sticky_messages.clear()
        for cid_str, info in data.items():
            try:
                cid = int(cid_str)
                if info.get("text"):
                    sticky_texts[cid] = info["text"]
                if info.get("message_id"):
                    sticky_messages[cid] = info["message_id"]
            except:
                continue
    except Exception as e:
        await log_to_bot_channel(f"Failed to load sticky data: {e}")

async def save_stickies():
    if STORAGE_CHANNEL_ID == 0 or sticky_storage_message_id is None:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not ch or not isinstance(ch, TextChannel):
        return
    try:
        msg = await ch.fetch_message(sticky_storage_message_id)
        data = {}
        for cid, text in sticky_texts.items():
            entry = {"text": text}
            if cid in sticky_messages:
                entry["message_id"] = sticky_messages[cid]
            data[str(cid)] = entry
        await msg.edit(content="STICKY_DATA:" + json.dumps(data))
    except:
        pass

def parse_schedule_datetime(when: str) -> datetime | None:
    try:
        return datetime.strptime(when, "%Y-%m-%d %H:%M")
    except ValueError:
        return None

async def init_prize_storage():
    global movie_prize_storage_message_id, nitro_prize_storage_message_id, steam_prize_storage_message_id
    global movie_scheduled_prizes, nitro_scheduled_prizes, steam_scheduled_prizes
    if STORAGE_CHANNEL_ID == 0:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return
    movie_msg = nitro_msg = steam_msg = None
    async for msg in ch.history(limit=100, oldest_first=True):
        if msg.author != bot.user:
            continue
        content = msg.content
        if content.startswith("PRIZE_MOVIE_DATA:"):
            movie_msg = msg
        elif content.startswith("PRIZE_NITRO_DATA:"):
            nitro_msg = msg
        elif content.startswith("PRIZE_STEAM_DATA:"):
            steam_msg = msg
        if movie_msg and nitro_msg and steam_msg:
            break
    if not (movie_msg and nitro_msg and steam_msg):
        await log_to_bot_channel("Prize storage messages missing → Run /prize_init first")
        return
    movie_prize_storage_message_id = movie_msg.id
    nitro_prize_storage_message_id = nitro_msg.id
    steam_prize_storage_message_id = steam_msg.id
    def safe_load(content, prefix):
        try:
            return json.loads(content[len(prefix):]) if content.startswith(prefix) else []
        except:
            return []
    movie_scheduled_prizes = safe_load(movie_msg.content, "PRIZE_MOVIE_DATA:")
    nitro_scheduled_prizes = safe_load(nitro_msg.content, "PRIZE_NITRO_DATA:")
    steam_scheduled_prizes = safe_load(steam_msg.content, "PRIZE_STEAM_DATA:")

async def save_prize_storage():
    if STORAGE_CHANNEL_ID == 0:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not ch or not isinstance(ch, TextChannel):
        return
    for msg_id, data, prefix in [
        (movie_prize_storage_message_id, movie_scheduled_prizes, "PRIZE_MOVIE_DATA:"),
        (nitro_prize_storage_message_id, nitro_scheduled_prizes, "PRIZE_NITRO_DATA:"),
        (steam_prize_storage_message_id, steam_scheduled_prizes, "PRIZE_STEAM_DATA:"),
    ]:
        if msg_id:
            try:
                msg = await ch.fetch_message(msg_id)
                await msg.edit(content=prefix + json.dumps(data))
            except:
                pass

def get_prize_list_and_entries(prize_type: str):
    if prize_type == "movie":
        return movie_scheduled_prizes
    if prize_type == "nitro":
        return nitro_scheduled_prizes
    if prize_type == "steam":
        return steam_scheduled_prizes
    return None

async def run_scheduled_prize(prize_type: str, prize_id: int):
    if prize_type == "movie":
        entries = movie_scheduled_prizes
        view_cls = MoviePrizeView
    elif prize_type == "nitro":
        entries = nitro_scheduled_prizes
        view_cls = NitroPrizeView
    elif prize_type == "steam":
        entries = steam_scheduled_prizes
        view_cls = SteamPrizeView
    else:
        return
    record = None
    for p in entries:
        if p.get("id") == prize_id:
            record = p
            break
    if not record:
        return
    send_at = parse_schedule_datetime(record.get("send_at", ""))
    if not send_at:
        return
    now = datetime.utcnow()
    delay = (send_at - now).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    channel_id = record.get("channel_id")
    content = record.get("content")
    if not channel_id or not content:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return
    view = view_cls()
    await channel.send(content, view=view)
    entries[:] = [p for p in entries if p.get("id") != prize_id]
    await save_prize_storage()

async def add_scheduled_prize(prize_type: str, channel_id: int, content: str, send_at: datetime):
    if prize_type == "movie":
        entries = movie_scheduled_prizes
    elif prize_type == "nitro":
        entries = nitro_scheduled_prizes
    elif prize_type == "steam":
        entries = steam_scheduled_prizes
    else:
        return
    existing_ids = [p.get("id", 0) for p in entries]
    new_id = max(existing_ids) + 1 if existing_ids else 1
    entries.append(
        {
            "id": new_id,
            "channel_id": channel_id,
            "content": content,
            "send_at": send_at.strftime("%Y-%m-%d %H:%M"),
        }
    )
    await save_prize_storage()
    bot.loop.create_task(run_scheduled_prize(prize_type, new_id))

async def initialize_dead_chat():
    global dead_current_holder_id
    if not DEAD_CHAT_CHANNEL_IDS or DEAD_CHAT_ROLE_ID == 0:
        return
    for guild in bot.guilds:
        role = guild.get_role(DEAD_CHAT_ROLE_ID)
        if role and role.members:
            dead_current_holder_id = role.members[0].id
            break
    for chan_id in DEAD_CHAT_CHANNEL_IDS:
        if chan_id in deadchat_last_times:
            continue
        deadchat_last_times[chan_id] = discord.utils.utcnow().isoformat() + "Z"
    await save_deadchat_storage()

async def handle_dead_chat_message(message: discord.Message):
    global dead_current_holder_id
    if DEAD_CHAT_ROLE_ID == 0 or message.channel.id not in DEAD_CHAT_CHANNEL_IDS or message.author.id in IGNORE_MEMBER_IDS:
        return
    now = discord.utils.utcnow()
    cid = message.channel.id
    now_s = now.isoformat() + "Z"
    last_raw = deadchat_last_times.get(cid)
    deadchat_last_times[cid] = now_s
    await save_deadchat_storage()
    if not last_raw:
        return
    try:
        last_time = datetime.fromisoformat(last_raw.replace("Z", ""))
    except:
        return
    if (now - last_time).total_seconds() < DEAD_CHAT_IDLE_SECONDS:
        return
    role = message.guild.get_role(DEAD_CHAT_ROLE_ID)
    if not role or role in message.author.roles:
        return
    if DEAD_CHAT_COOLDOWN_SECONDS > 0:
        last_win = dead_last_win_time.get(message.author.id)
        if last_win and (now - last_win).total_seconds() < DEAD_CHAT_COOLDOWN_SECONDS:
            return
    for member in list(role.members):
        if member.id != message.author.id:
            await member.remove_roles(role, reason="Dead Chat stolen")
    await message.author.add_roles(role, reason="Dead Chat claimed")
    dead_current_holder_id = message.author.id
    dead_last_win_time[message.author.id] = now
    for old_cid, mid in list(dead_last_notice_message_ids.items()):
        if mid:
            ch = message.guild.get_channel(old_cid)
            if ch:
                try:
                    m = await ch.fetch_message(mid)
                    await m.delete()
                except:
                    pass
    minutes = DEAD_CHAT_IDLE_SECONDS // 60
    notice = await message.channel.send(
        f"{message.author.mention} has stolen the {role.mention} role after {minutes}+ minutes of silence.\n"
        "-# There's a random chance to win prizes with this role."
    )
    dead_last_notice_message_ids[message.channel.id] = notice.id
    await save_deadchat_state()

async def init_deadchat_storage():
    global deadchat_storage_message_id, deadchat_last_times
    if STORAGE_CHANNEL_ID == 0:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return
    storage_msg = None
    async for msg in ch.history(limit=50, oldest_first=True):
        if msg.author == bot.user and msg.content.startswith("DEADCHAT_DATA:"):
            storage_msg = msg
            break
    if not storage_msg:
        await log_to_bot_channel("init_deadchat_storage: DEADCHAT_DATA message not found. Run /deadchat_init first.")
        return
    deadchat_storage_message_id = storage_msg.id
    raw = storage_msg.content[len("DEADCHAT_DATA:"):]
    try:
        data = json.loads(raw or "{}")
        deadchat_last_times.clear()
        for cid_str, ts in data.items():
            try:
                deadchat_last_times[int(cid_str)] = ts
            except:
                pass
    except:
        pass

async def save_deadchat_storage():
    global deadchat_storage_message_id
    if STORAGE_CHANNEL_ID == 0 or deadchat_storage_message_id is None:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not ch or not isinstance(ch, TextChannel):
        return
    try:
        msg = await ch.fetch_message(deadchat_storage_message_id)
        await msg.edit(content="DEADCHAT_DATA:" + json.dumps(deadchat_last_times))
    except discord.Forbidden:
        await log_to_bot_channel("DEADCHAT_DATA: Bot missing 'Manage Messages' in storage channel")
    except discord.NotFound:
        await log_to_bot_channel("DEADCHAT_DATA message deleted — Run /deadchat_init")
        deadchat_storage_message_id = None
    except Exception as e:
        await log_to_bot_channel(f"Deadchat save failed: {e}")

async def init_deadchat_state_storage():
    global deadchat_state_storage_message_id
    if STORAGE_CHANNEL_ID == 0:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return
    storage_msg = None
    async for msg in ch.history(limit=50, oldest_first=True):
        if msg.author == bot.user and msg.content.startswith("DEADCHAT_STATE:"):
            storage_msg = msg
            break
    if not storage_msg:
        await log_to_bot_channel("DEADCHAT_STATE message missing → Run /deadchat_state_init")
        return
    deadchat_state_storage_message_id = storage_msg.id
    await load_deadchat_state()  # load the data immediately

async def load_deadchat_state():
    global dead_current_holder_id, dead_last_win_time, dead_last_notice_message_ids
    if not deadchat_state_storage_message_id or STORAGE_CHANNEL_ID == 0:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    try:
        msg = await ch.fetch_message(deadchat_state_storage_message_id)
        data = json.loads(msg.content[len("DEADCHAT_STATE:"):])
        dead_current_holder_id = data.get("current_holder")
        dead_last_win_time = {int(k): datetime.fromisoformat(v.replace("Z", "")) for k, v in data.get("last_win_times", {}).items()}
        dead_last_notice_message_ids = {int(k): v for k, v in data.get("notice_msg_ids", {}).items()}
        # Give the role back if someone had it
        if dead_current_holder_id:
            for guild in bot.guilds:
                member = guild.get_member(dead_current_holder_id)
                role = guild.get_role(DEAD_CHAT_ROLE_ID)
                if member and role and role not in member.roles:
                    await member.add_roles(role, reason="Restoring Dead Chat role after restart")
    except Exception as e:
        await log_to_bot_channel(f"Failed to load DEADCHAT_STATE: {e}")

async def save_deadchat_state():
    if STORAGE_CHANNEL_ID == 0 or deadchat_state_storage_message_id is None:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, TextChannel):
        return
    data = {
        "current_holder": dead_current_holder_id,
        "last_win_times": {str(k): v.isoformat() + "Z" for k, v in dead_last_win_time.items()},
        "notice_msg_ids": dead_last_notice_message_ids
    }
    try:
        try:
            msg = await ch.fetch_message(deadchat_state_storage_message_id)
        await msg.edit(content="DEADCHAT_STATE:" + json.dumps(data))
    except Exception as e:
        await log_to_bot_channel(f"Deadchat state save failed: {e}")

# Twitch state -------------------------------------------------
async def init_twitch_state_storage():
    global twitch_state_storage_message_id
    if STORAGE_CHANNEL_ID == 0:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return
    storage_msg = None
    async for msg in ch.history(limit=50, oldest_first=True):
        if msg.author == bot.user and msg.content.startswith("TWITCH_STATE:"):
            storage_msg = msg
            break
    if not storage_msg:
        await log_to_bot_channel("TWITCH_STATE message missing → Run /twitch_state_init")
        return
    twitch_state_storage_message_id = storage_msg.id
    await load_twitch_state()

async def load_twitch_state():
    global twitch_live_state
    if not twitch_state_storage_message_id:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    try:
        msg = await ch.fetch_message(twitch_state_storage_message_id)
        loaded = json.loads(msg.content[len("TWITCH_STATE:"):])
        twitch_live_state = {k.lower(): bool(v) for k, v in loaded.items()}
    except:
        twitch_live_state = {name: False for name in TWITCH_CHANNELS}

async def save_twitch_state():
    if STORAGE_CHANNEL_ID == 0 or twitch_state_storage_message_id is None:
        return
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not ch:
        return
    try:
        msg = await ch.fetch_message(twitch_state_storage_message_id)
        await msg.edit(content="TWITCH_STATE:" + json.dumps(twitch_live_state))
    except:
        pass

async def get_twitch_token():
    global twitch_access_token
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return None
    url = "https://id.twitch.tv/oauth2/token"
    params = {"client_id": TWITCH_CLIENT_ID, "client_secret": TWITCH_CLIENT_SECRET, "grant_type": "client_credentials"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                twitch_access_token = data["access_token"]
                return twitch_access_token
    return None

async def fetch_twitch_streams():
    global twitch_access_token
    if not twitch_access_token:
        await get_twitch_token()
    if not twitch_access_token:
        return {}
    headers = {"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {twitch_access_token}"}
    params = [("user_login", name) for name in TWITCH_CHANNELS]
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.twitch.tv/helix/streams", headers=headers, params=params) as resp:
            if resp.status == 401:
                twitch_access_token = None
                await get_twitch_token()
                headers["Authorization"] = f"Bearer {twitch_access_token}"
                async with session.get("https://api.twitch.tv/helix/streams", headers=headers, params=params) as resp2:
                    data = await resp2.json()
            elif resp.status == 200:
                data = await resp.json()
            else:
                return {}
    result = {s["user_login"].lower(): s for s in data.get("data", [])}
    return result


############### VIEWS / UI COMPONENTS ###############
class BasePrizeView(discord.ui.View):
    gift_title: str = ""
    rarity: str = ""
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Claim Your Prize!", style=discord.ButtonStyle.primary)
    async def claim_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        try:
            await interaction.message.delete()
        except:
            pass
        dead_role = guild.get_role(DEAD_CHAT_ROLE_ID)
        role_mention = dead_role.mention if dead_role else "the Dead Chat role"
        ch = guild.get_channel(WELCOME_CHANNEL_ID)
        if ch:
            await ch.send(f"{PRIZE_EMOJI} {interaction.user.mention} has won a **{self.gift_title}** with {role_mention}!\n-# *Drop Rate: {self.rarity}*")
        await interaction.response.send_message(f"You claimed a **{self.gift_title}**!", ephemeral=True)

class MoviePrizeView(BasePrizeView):
    gift_title = "Movie Request"
    rarity = "Common"
class NitroPrizeView(BasePrizeView):
    gift_title = "Month of Nitro Basic"
    rarity = "Uncommon"
class SteamPrizeView(BasePrizeView):
    gift_title = "Steam Gift Card"
    rarity = "Rare"


############### AUTOCOMPLETE FUNCTIONS ###############


############### BACKGROUND TASKS & SCHEDULERS ###############
async def twitch_watcher():
    await bot.wait_until_ready()
    if not TWITCH_ANNOUNCE_CHANNEL_ID or not TWITCH_CHANNELS:
        return
    ch = bot.get_channel(TWITCH_ANNOUNCE_CHANNEL_ID)
    if not ch:
        return
    while not bot.is_closed():
        streams = await fetch_twitch_streams()
        for name in TWITCH_CHANNELS:
            is_live = name in streams
            was_live = twitch_live_state.get(name, False)
            if is_live and not was_live:
                await ch.send(
                    f"{TWITCH_EMOJI} {name} is live ┃ https://twitch.tv/{name}\n-# @everyone"
                )
                twitch_live_state[name] = True
                await save_twitch_state()
            elif not is_live and was_live:
                twitch_live_state[name] = False
                await save_twitch_state()
        await asyncio.sleep(60)


############### EVENT HANDLERS ###############
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    bot.loop.create_task(twitch_watcher())
    bot.add_view(MoviePrizeView())
    bot.add_view(NitroPrizeView())
    bot.add_view(SteamPrizeView())
    for guild in bot.guilds:
        found = False
        for channel in guild.text_channels:
            try:
                msg = await channel.fetch_message(REACTION_ROLE_MESSAGE_ID)
            except discord.NotFound:
                continue
            except discord.Forbidden:
                continue
            except discord.HTTPException:
                continue
            else:
                for emoji in reaction_roles:
                    try:
                        await msg.add_reaction(emoji)
                    except:
                        pass
                found = True
                break
        if found:
            break
    await init_sticky_storage()
    await init_prize_storage()
    await init_deadchat_storage()
    await init_deadchat_state_storage()
    await init_twitch_state_storage()
    if sticky_storage_message_id is None:
        print("STORAGE NOT INITIALIZED — Run /sticky_init, /prize_init and /deadchat_init")
    else:
        await initialize_dead_chat()
        for prize_list, prize_type in [
            (movie_scheduled_prizes, "movie"),
            (nitro_scheduled_prizes,  "nitro"),
            (steam_scheduled_prizes,  "steam")
        ]:
            for p in prize_list:
                pid = p.get("id")
                if pid is not None:
                    bot.loop.create_task(run_scheduled_prize(prize_type, pid))

@bot.event
async def on_member_update(before, after):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if not ch:
        return
    if before.premium_since is None and after.premium_since:
        if BOOST_TEXT:  # Added check
            await ch.send(BOOST_TEXT.replace("{mention}", after.mention))
    new_roles = set(after.roles) - set(before.roles)
    for role in new_roles:
        if role.id == ROLE_TO_WATCH:
            if VIP_TEXT:  # Added check
                await ch.send(VIP_TEXT.replace("{mention}", after.mention))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await handle_dead_chat_message(message)
    if message.channel.id in sticky_texts:
        old_id = sticky_messages.get(message.channel.id)
        if old_id:
            try:
                old = await message.channel.fetch_message(old_id)
                await old.delete()
            except discord.NotFound:
                pass
        new_msg = await message.channel.send(sticky_texts[message.channel.id])
        sticky_messages[message.channel.id] = new_msg.id
        await save_stickies()
    if message.channel.id in AUTO_DELETE_CHANNEL_IDS:
        content = message.content.lower()
        if not (
            "happy birthday" in content
            or "happy bday" in content
            or "happy b-day" in content
        ):
            async def delete_later():
                await asyncio.sleep(DELETE_DELAY_SECONDS)
                try:
                    await message.delete()
                except:
                    pass
            bot.loop.create_task(delete_later())
    await bot.process_commands(message)

@bot.event
async def on_member_join(member: discord.Member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if member.bot:
        await log_to_bot_channel(f"Bot joined: {member.mention}")
        if BOT_JOIN_ROLE_ID:
            role = member.guild.get_role(BOT_JOIN_ROLE_ID)
            if role:
                await member.add_roles(role)
        return
    if ch and WELCOME_TEXT:
        await ch.send(WELCOME_TEXT.replace("{mention}", member.mention))
    if MEMBER_JOIN_ROLE_ID:
        async def delayed_role():
            await asyncio.sleep(86400)
            if member in member.guild.members:
                role = member.guild.get_role(MEMBER_JOIN_ROLE_ID)
                if role:
                    await member.add_roles(role)
        bot.loop.create_task(delayed_role())

@bot.event
async def on_member_ban(guild, user):
    moderator = None
    async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
        if entry.target.id == user.id:
            moderator = entry.user
            break
    text = f"{user.mention} was banned by {moderator.mention if moderator else 'Unknown'}"
    if user.bot:
        await log_to_bot_channel(text)
    else:
        await log_to_thread(text)

@bot.event
async def on_member_remove(member: discord.Member):
    now = discord.utils.utcnow()
    async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
        if entry.target.id == member.id and (now - entry.created_at).total_seconds() < 10:
            return
    kicked = False
    moderator = None
    async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id and (now - entry.created_at).total_seconds() < 10:
            moderator = entry.user
            kicked = True
            break
    log_fn = log_to_bot_channel if member.bot else log_to_thread
    if kicked:
        await log_fn(f"{member.mention} was kicked by {moderator.mention if moderator else 'Unknown'}")
    else:
        await log_fn(f"{member.mention} has left the server")

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.message_id != REACTION_ROLE_MESSAGE_ID:
        return
    if payload.emoji.is_custom_emoji():
        key = payload.emoji.name
    else:
        key = str(payload.emoji)
    role_id = reaction_roles.get(key)
    if not role_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    role = guild.get_role(role_id)
    member = guild.get_member(payload.user_id)
    if role and member and not member.bot:
        await member.add_roles(role)

@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id != REACTION_ROLE_MESSAGE_ID:
        return
    if payload.emoji.is_custom_emoji():
        key = payload.emoji.name
    else:
        key = str(payload.emoji)
    role_id = reaction_roles.get(key)
    if not role_id:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    role = guild.get_role(role_id)
    member = guild.get_member(payload.user_id)
    if role and member and not member.bot:
        await member.remove_roles(role)


############### COMMAND GROUPS ###############
@bot.slash_command(name="deadchat_rescan", description="Force-scan all dead-chat channels for latest message timestamps")
async def deadchat_rescan(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    count = 0
    async with ctx.typing():
        for channel_id in DEAD_CHAT_CHANNEL_IDS:
            channel = bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                continue
            try:
                async for message in channel.history(limit=1, oldest_first=False):
                    if message.author.bot:
                        continue
                    deadchat_last_times[channel_id] = message.created_at.isoformat() + "Z"
                    count += 1
                    break
            except:
                pass
        await save_deadchat_storage()
    await ctx.respond(f"Rescan complete — found latest message in {count}/{len(DEAD_CHAT_CHANNEL_IDS)} dead-chat channels and saved timestamps.", ephemeral=True)

@bot.slash_command(name="deadchat_state_init", description="Create DEADCHAT_STATE storage message")
async def deadchat_state_init(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only", ephemeral=True)
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return await ctx.respond("Invalid storage channel", ephemeral=True)
    msg = await ch.send("DEADCHAT_STATE:{\"current_holder\":null,\"last_win_times\":{},\"notice_msg_ids\":{}}")
    await ctx.respond(f"Created DEADCHAT_STATE message: {msg.id}", ephemeral=True)

@bot.slash_command(name="twitch_state_init", description="Create TWITCH_STATE storage message")
async def twitch_state_init(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only", ephemeral=True)
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return await ctx.respond("Invalid storage channel", ephemeral=True)
    msg = await ch.send("TWITCH_STATE:{}")
    await ctx.respond(f"Created TWITCH_STATE message: {msg.id}", ephemeral=True)
    
@bot.slash_command(name="prize_init", description="Manually create prize storage messages")
async def prize_init(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return await ctx.respond("Storage channel invalid.", ephemeral=True)
    movie_msg = await ch.send("PRIZE_MOVIE_DATA:[]")
    nitro_msg = await ch.send("PRIZE_NITRO_DATA:[]")
    steam_msg = await ch.send("PRIZE_STEAM_DATA:[]")
    global movie_prize_storage_message_id, nitro_prize_storage_message_id, steam_prize_storage_message_id
    movie_prize_storage_message_id = movie_msg.id
    nitro_prize_storage_message_id = nitro_msg.id
    steam_prize_storage_message_id = steam_msg.id
    await ctx.respond(f"Prize storage messages created:\nMovie: {movie_msg.id}\nNitro: {nitro_msg.id}\nSteam: {steam_msg.id}", ephemeral=True)

@bot.slash_command(name="sticky_init", description="Manually create sticky storage message")
async def sticky_init(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return await ctx.respond("Storage channel invalid.", ephemeral=True)
    msg = await ch.send("STICKY_DATA:{}")
    global sticky_storage_message_id
    sticky_storage_message_id = msg.id
    await ctx.respond(f"Sticky storage message created: {msg.id}", ephemeral=True)

@bot.slash_command(name="deadchat_init", description="Manually create deadchat storage message")
async def deadchat_init(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    ch = bot.get_channel(STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return await ctx.respond("Storage channel invalid.", ephemeral=True)
    msg = await ch.send("DEADCHAT_DATA:{}")
    global deadchat_storage_message_id
    deadchat_storage_message_id = msg.id
    await ctx.respond(f"Deadchat storage message created: {msg.id}", ephemeral=True)
    
@bot.slash_command(name="say", description="Make the bot say something right here")
async def say(ctx, message: discord.Option(str, "Message to send", required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)
    await ctx.channel.send(message.replace("\\n", "\n"))
    await ctx.respond("Sent!", ephemeral=True)

@bot.slash_command(name="birthday_announce", description="Manually send the birthday message for a member")
async def birthday_announce(ctx, member: discord.Option(discord.Member, "Member", required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if not ch:
        return await ctx.respond("Welcome channel not found.", ephemeral=True)
    msg = VIP_TEXT.replace("{mention}", member.mention) if VIP_TEXT else f"Happy birthday, {member.mention}!"
    await ch.send(msg)
    await ctx.respond(f"Sent birthday message for {member.mention}.", ephemeral=True)

@bot.slash_command(name="editbotmsg", description="Edit a bot message in this channel with 4 lines")
async def editbotmsg(ctx, message_id: str, line1: str, line2: str, line3: str, line4: str,):
    if not (ctx.author.guild_permissions.administrator or ctx.guild.owner_id == ctx.author.id):
        return await ctx.respond("Admin only.", ephemeral=True)
    try:
        msg_id_int = int(message_id)
    except ValueError:
        return await ctx.respond("Invalid message ID.", ephemeral=True)
    try:
        msg = await ctx.channel.fetch_message(msg_id_int)
    except discord.NotFound:
        return await ctx.respond("Message not found in this channel.", ephemeral=True)
    except discord.Forbidden:
        return await ctx.respond("I cannot access that message.", ephemeral=True)
    except discord.HTTPException:
        return await ctx.respond("Error fetching that message.", ephemeral=True)
    if msg.author.id != bot.user.id:
        return await ctx.respond("That message was not sent by me.", ephemeral=True)
    new_content = "\n".join([line1, line2, line3, line4])
    await msg.edit(content=new_content)
    await ctx.respond("Message updated.", ephemeral=True)

@bot.slash_command(name="prize_list", description="List scheduled prizes")
async def prize_list(
    ctx,
    prize_type: discord.Option(str, choices=["movie", "nitro", "steam"], required=True),
):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    entries = get_prize_list_and_entries(prize_type)
    if not entries:
        return await ctx.respond("No scheduled prizes.", ephemeral=True)
    if len(entries) == 0:
        return await ctx.respond("No scheduled prizes.", ephemeral=True)
    lines = []
    for p in entries:
        lines.append(f"ID {p['id']} ┃ {p['send_at']} UTC ┃ <#{p['channel_id']}>")
    text = "\n".join(lines)
    await ctx.respond(f"Scheduled {prize_type} prizes:\n{text}", ephemeral=True)

@bot.slash_command(name="prize_delete", description="Delete a scheduled prize")
async def prize_delete(
    ctx,
    prize_type: discord.Option(str, choices=["movie", "nitro", "steam"], required=True),
    prize_id: discord.Option(int, "ID from /prize_list", required=True),
):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    entries = get_prize_list_and_entries(prize_type)
    if entries is None:
        return await ctx.respond("Invalid prize type.", ephemeral=True)
    before = len(entries)
    entries[:] = [p for p in entries if p.get("id") != prize_id]
    after = len(entries)
    if before == after:
        return await ctx.respond("No prize with that ID.", ephemeral=True)
    await save_prize_storage()
    await ctx.respond(f"Deleted scheduled {prize_type} prize ID {prize_id}.", ephemeral=True)

@bot.slash_command(name="prize_movie")
async def prize_movie(
    ctx,
    month: discord.Option(str, "Month (UTC date)", required=False, choices=MONTH_CHOICES),
    day: discord.Option(int, "Day of month", required=False),
    hour: discord.Option(int, "Hour (0-23, UTC)", required=False),
):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    content = "**YOU'VE FOUND A PRIZE!**\nPrize: *Movie Request*\nDrop Rate: *Common*"
    if month is None and day is None and hour is None:
        return await ctx.respond(content, view=MoviePrizeView())
    if month is None or day is None or hour is None:
        return await ctx.respond("Provide month, day, and hour, or leave all blank.", ephemeral=True)
    month_num = MONTH_TO_NUM.get(month)
    if not month_num:
        return await ctx.respond("Invalid month.", ephemeral=True)
    now = datetime.utcnow()
    try:
        send_at = datetime(now.year, month_num, day, hour, 0)
    except ValueError:
        return await ctx.respond("Invalid date.", ephemeral=True)
    if send_at <= now:
        try:
            send_at = datetime(now.year + 1, month_num, day, hour, 0)
        except ValueError:
            return await ctx.respond("Invalid date.", ephemeral=True)
    await add_scheduled_prize("movie", ctx.channel.id, content, send_at)
    await ctx.respond(f"Scheduled for {send_at.strftime('%Y-%m-%d %H:%M')} UTC.", ephemeral=True)
    
@bot.slash_command(name="prize_nitro")
async def prize_nitro(
    ctx,
    month: discord.Option(str, "Month (UTC date)", required=False, choices=MONTH_CHOICES),
    day: discord.Option(int, "Day of month", required=False),
    hour: discord.Option(int, "Hour (0-23, UTC)", required=False),
):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    content = "**YOU'VE FOUND A PRIZE!**\nPrize: *Month of Nitro Basic*\nDrop Rate: *Uncommon*"
    if month is None and day is None and hour is None:
        return await ctx.respond(content, view=NitroPrizeView())
    if month is None or day is None or hour is None:
        return await ctx.respond("Provide month, day, and hour, or leave all blank.", ephemeral=True)
    month_num = MONTH_TO_NUM.get(month)
    if not month_num:
        return await ctx.respond("Invalid month.", ephemeral=True)
    now = datetime.utcnow()
    try:
        send_at = datetime(now.year, month_num, day, hour, 0)
    except ValueError:
        return await ctx.respond("Invalid date.", ephemeral=True)
    if send_at <= now:
        try:
            send_at = datetime(now.year + 1, month_num, day, hour, 0)
        except ValueError:
            return await ctx.respond("Invalid date.", ephemeral=True)
    await add_scheduled_prize("nitro", ctx.channel.id, content, send_at)
    await ctx.respond(f"Scheduled for {send_at.strftime('%Y-%m-%d %H:%M')} UTC.", ephemeral=True)

@bot.slash_command(name="prize_steam")
async def prize_steam(
    ctx,
    month: discord.Option(str, "Month (UTC date)", required=False, choices=MONTH_CHOICES),
    day: discord.Option(int, "Day of month", required=False),
    hour: discord.Option(int, "Hour (0-23, UTC)", required=False),
):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    content = "**YOU'VE FOUND A PRIZE!**\nPrize: *Steam Gift Card*\nDrop Rate: *Rare*"
    if month is None and day is None and hour is None:
        return await ctx.respond(content, view=SteamPrizeView())
    if month is None or day is None or hour is None:
        return await ctx.respond("Provide month, day, and hour, or leave all blank.", ephemeral=True)
    month_num = MONTH_TO_NUM.get(month)
    if not month_num:
        return await ctx.respond("Invalid month.", ephemeral=True)
    now = datetime.utcnow()
    try:
        send_at = datetime(now.year, month_num, day, hour, 0)
    except ValueError:
        return await ctx.respond("Invalid date.", ephemeral=True)
    if send_at <= now:
        try:
            send_at = datetime(now.year + 1, month_num, day, hour, 0)
        except ValueError:
            return await ctx.respond("Invalid date.", ephemeral=True)
    await add_scheduled_prize("steam", ctx.channel.id, content, send_at)
    await ctx.respond(f"Scheduled for {send_at.strftime('%Y-%m-%d %H:%M')} UTC.", ephemeral=True)

@bot.slash_command(name="prize_announce")
async def prize_announce(ctx, member: discord.Option(discord.Member, required=True), prize: discord.Option(str, choices=list(PRIZE_DEFS.keys()), required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    dead_role = ctx.guild.get_role(DEAD_CHAT_ROLE_ID)
    role_mention = dead_role.mention if dead_role else "the Dead Chat role"
    rarity = PRIZE_DEFS[prize]
    await ctx.channel.send(f"{PRIZE_EMOJI} {member.mention} has won a **{prize}** with {role_mention}!\n-# *Drop Rate: {rarity}*")
    await ctx.respond("Announcement sent.", ephemeral=True)

@bot.slash_command(name="sticky")
async def sticky(ctx, action: discord.Option(str, choices=["set", "clear"], required=True), text: discord.Option(str, required=False)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    if action == "set":
        if not text:
            return await ctx.respond("Text required.", ephemeral=True)
        sticky_texts[ctx.channel.id] = text
        old_id = sticky_messages.get(ctx.channel.id)
        if old_id:
            try:
                msg = await ctx.channel.fetch_message(old_id)
                await msg.edit(content=text)
                await ctx.respond("Sticky updated.", ephemeral=True)
            except discord.NotFound:
                msg = await ctx.channel.send(text)
                sticky_messages[ctx.channel.id] = msg.id
                await ctx.respond("Sticky created.", ephemeral=True)
        else:
            msg = await ctx.channel.send(text)
            sticky_messages[ctx.channel.id] = msg.id
            await ctx.respond("Sticky created.", ephemeral=True)
        await save_stickies()
    else:
        old_id = sticky_messages.pop(ctx.channel.id, None)
        sticky_texts.pop(ctx.channel.id, None)
        if old_id:
            try:
                msg = await ctx.channel.fetch_message(old_id)
                await msg.delete()
            except discord.NotFound:
                pass
        await save_stickies()
        await ctx.respond("Sticky cleared.", ephemeral=True)


############### ON_READY & BOT START ###############
bot.run(os.getenv("TOKEN"))
