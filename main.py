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
AUTO_DELETE_CHANNEL_IDS = [1331501272804884490, 1444194142589554841, 1444206974395748423]
DELETE_DELAY_SECONDS = 300

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
IGNORE_MEMBER_IDS = {775970689525612555}

STICKY_STORAGE_CHANNEL_ID = int(os.getenv("STICKY_STORAGE_CHANNEL_ID", "0"))

############### GLOBAL STATE / STORAGE ###############
twitch_access_token: str | None = None
twitch_live_state: dict[str, bool] = {}

dead_last_message_time: dict[int, datetime] = {}
dead_current_holder_id: int | None = None
dead_last_notice_message_ids: dict[int, int | None] = {}
dead_last_win_time: dict[int, datetime] = {}

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
    if STICKY_STORAGE_CHANNEL_ID == 0:
        return
    ch = bot.get_channel(STICKY_STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return
    storage_msg = None
    async for msg in ch.history(limit=50, oldest_first=True):
        if msg.author == bot.user and msg.content.startswith("STICKY_DATA:"):
            storage_msg = msg
            break
    if not storage_msg:
        storage_msg = await ch.send("STICKY_DATA:{}")
    sticky_storage_message_id = storage_msg.id
    data_str = storage_msg.content[len("STICKY_DATA:"):]
    if data_str.strip():
        try:
            data = json.loads(data_str)
            for cid_str, info in data.items():
                cid = int(cid_str)
                if info.get("text"):
                    sticky_texts[cid] = info["text"]
                if info.get("message_id"):
                    sticky_messages[cid] = info["message_id"]
        except:
            pass

async def save_stickies():
    if STICKY_STORAGE_CHANNEL_ID == 0 or sticky_storage_message_id is None:
        return
    ch = bot.get_channel(STICKY_STORAGE_CHANNEL_ID)
    if not ch:
        return
    try:
        msg = await ch.fetch_message(sticky_storage_message_id)
    except:
        return
    data = {}
    for cid, text in sticky_texts.items():
        entry = {"text": text}
        if cid in sticky_messages:
            entry["message_id"] = sticky_messages[cid]
        data[str(cid)] = entry
    await msg.edit(content="STICKY_DATA:" + json.dumps(data))

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
        ch = bot.get_channel(chan_id)
        if not ch or not isinstance(ch, discord.TextChannel):
            continue
        try:
            async for msg in ch.history(limit=50):
                if msg.author.bot or msg.author.id in IGNORE_MEMBER_IDS:
                    continue
                dead_last_message_time[chan_id] = msg.created_at
                break
        except:
            pass
        dead_last_message_time.setdefault(chan_id, discord.utils.utcnow())

async def handle_dead_chat_message(message: discord.Message):
    global dead_current_holder_id
    if DEAD_CHAT_ROLE_ID == 0 or message.channel.id not in DEAD_CHAT_CHANNEL_IDS or message.author.id in IGNORE_MEMBER_IDS:
        return
    now = discord.utils.utcnow()
    last_time = dead_last_message_time.get(message.channel.id)
    dead_last_message_time[message.channel.id] = now
    if not last_time or (now - last_time).total_seconds() < DEAD_CHAT_IDLE_SECONDS:
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
    for cid, mid in list(dead_last_notice_message_ids.items()):
        if mid:
            ch = message.guild.get_channel(cid)
            if ch:
                try:
                    m = await ch.fetch_message(mid)
                    await m.delete()
                except:
                    pass
    minutes = DEAD_CHAT_IDLE_SECONDS // 60
    notice = await message.channel.send(f"{message.author.mention} has stolen the {role.mention} role after {minutes}+ minutes of silence.\n-# There's a random chance to win prizes with this role.")
    dead_last_notice_message_ids[message.channel.id] = notice.id

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
            await ch.send(f"<:prize:1441586959909781666> {interaction.user.mention} has won a **{self.gift_title}** with {role_mention}!\n-# *Drop Rate: {self.rarity}*")
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
    for name in TWITCH_CHANNELS:
        twitch_live_state[name] = False
    while not bot.is_closed():
        streams = await fetch_twitch_streams()
        for name in TWITCH_CHANNELS:
            is_live = name in streams
            was_live = twitch_live_state.get(name, False)
            if is_live and not was_live:
                await ch.send(f"{TWITCH_EMOJI} {name} is live ┃ https://twitch.tv/{name}\n-# @everyone")
                twitch_live_state[name] = True
            elif not is_live and was_live:
                twitch_live_state[name] = False
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
        for channel in guild.text_channels:
            try:
                msg = await channel.fetch_message(REACTION_ROLE_MESSAGE_ID)
                for emoji in reaction_roles:
                    await msg.add_reaction(emoji)
            except:
                continue
            break
    await initialize_dead_chat()
    await init_sticky_storage()

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

@bot.slash_command(name="editbotmsg", description="Edit a message previously sent by this bot")
async def editbotmsg(ctx, message_link: discord.Option(str, "Message link", required=True), new_text: discord.Option(str, "New content", required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)
    if "discord.com/channels/" not in message_link:
        return await ctx.respond("Please provide a full message link.", ephemeral=True)
    try:
        parts = message_link.strip().split("/")
        channel_id = int(parts[-2])
        message_id = int(parts[-1])
    except Exception:
        return await ctx.respond("Invalid message link.", ephemeral=True)
    channel = ctx.guild.get_channel(channel_id)
    if not channel:
        return await ctx.respond("Channel not found.", ephemeral=True)
    try:
        msg = await channel.fetch_message(message_id)
    except Exception:
        return await ctx.respond("Message not found.", ephemeral=True)
    if msg.author != bot.user:
        return await ctx.respond("I can only edit my own messages.", ephemeral=True)
    await msg.edit(content=new_text)
    await ctx.respond("Message updated.", ephemeral=True)

@bot.slash_command(name="prize_movie")
async def prize_movie(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    await ctx.respond("**YOU'VE FOUND A PRIZE!**\nPrize: *Movie Request*\nDrop Rate: *Common*", view=MoviePrizeView())

@bot.slash_command(name="prize_nitro")
async def prize_nitro(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    await ctx.respond("**YOU'VE FOUND A PRIZE!**\nPrize: *Month of Nitro Basic*\nDrop Rate: *Uncommon*", view=NitroPrizeView())

@bot.slash_command(name="prize_steam")
async def prize_steam(ctx):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    await ctx.respond("**YOU'VE FOUND A PRIZE!**\nPrize: *Steam Gift Card*\nDrop Rate: *Rare*", view=SteamPrizeView())

PRIZE_DEFS = {"Movie Request": "Common", "Month of Nitro Basic": "Uncommon", "Steam Gift Card": "Rare"}

@bot.slash_command(name="prize_announce")
async def prize_announce(ctx, member: discord.Option(discord.Member, required=True), prize: discord.Option(str, choices=list(PRIZE_DEFS.keys()), required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("Admin only.", ephemeral=True)
    dead_role = ctx.guild.get_role(DEAD_CHAT_ROLE_ID)
    role_mention = dead_role.mention if dead_role else "the Dead Chat role"
    rarity = PRIZE_DEFS[prize]
    await ctx.channel.send(f"<:prize:1441586959909781666> {member.mention} has won a **{prize}** with {role_mention}!\n-# *Drop Rate: {rarity}*")
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
