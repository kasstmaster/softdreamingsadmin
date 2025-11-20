import discord
import os
import asyncio
import aiohttp

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = discord.Bot(
    intents=intents,
    debug_guilds=[1205041211610501120]  # your server ID
)

# ────────────────────── CONFIG ──────────────────────
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID"))
ROLE_TO_WATCH = int(os.getenv("ROLE_TO_WATCH"))

WELCOME_TEXT = os.getenv("WELCOME_TEXT")
BOOST_TEXT   = os.getenv("BOOST_TEXT")
VIP_TEXT     = os.getenv("VIP_TEXT")

STATUS_VC_ID = int(os.getenv("STATUS_VC_ID"))
STATUS_LOG_CHANNEL_ID = int(os.getenv("STATUS_LOG_CHANNEL_ID"))
BUTTON_1_LABEL = os.getenv("BUTTON_1_LABEL")
BUTTON_1_URL   = os.getenv("BUTTON_1_URL")
BUTTON_3_LABEL = os.getenv("BUTTON_3_LABEL")
BUTTON_3_URL   = os.getenv("BUTTON_3_URL")

# ─────── TWITCH CONFIG (DIRECT VIA TWITCH API) ───────
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

# Comma-separated list of Twitch channel names
TWITCH_CHANNELS = [c.strip().lower() for c in os.getenv("TWITCH_CHANNELS").split(",") if c.strip()]

# Channel where announcements are sent
TWITCH_ANNOUNCE_CHANNEL_ID = int(os.getenv("TWITCH_ANNOUNCE_CHANNEL_ID"))

TWITCH_EMOJI = os.getenv("TWITCH_EMOJI")

# Runtime state
twitch_access_token: str | None = None
twitch_live_state: dict[str, bool] = {}  # channel_name -> is_live

# ────────────────────── REACTION ROLES CONFIG ──────────────────────

REACTION_ROLE_MESSAGE_ID = 1441144067479310376

reaction_roles: dict[str, int] = {
    "◀️": 1352405080703504384,  # :arrow_backward:
    "🔼": 1406868589893652520,  # :arrow_up_small:
    "▶️": 1406868685225725976,  # :arrow_forward:
    "🔽": 1342246913663303702,  # :arrow_down_small:
}

# ────────────────────── MOD LOG THREAD ──────────────────────

MOD_LOG_THREAD_ID = 1295173391099363361  # all ban/kick/leave logs go here


async def log_to_thread(content: str):
    """Send a log message to the configured moderation log thread."""
    channel = bot.get_channel(MOD_LOG_THREAD_ID)
    if not channel:
        print("Mod log thread not found.")
        return
    try:
        await channel.send(content)
    except Exception as e:
        print(f"Failed to send log message: {e}")


# ────────────────────── /say COMMAND ──────────────────────
@bot.slash_command(name="say", description="Make the bot say something right here")
async def say(ctx, message: discord.Option(str, "Message to send", required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)
    
    await ctx.channel.send(message)
    await ctx.respond("Sent!", ephemeral=True)

# ────────────────────── STICKY NOTES ──────────────────────

# channel_id -> message_id
sticky_messages: dict[int, int] = {}
# channel_id -> sticky text
sticky_texts: dict[int, str] = {}

@bot.slash_command(name="sticky", description="Create or clear a sticky note in this channel")
async def sticky(
    ctx,
    action: discord.Option(str, "Action", choices=["set", "clear"], required=True),
    text: discord.Option(str, "Sticky note text", required=False)
):
    # Admin check
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)

    channel = ctx.channel

    # ────────── SET STICKY ──────────
    if action == "set":
        if not text:
            return await ctx.respond("You must provide text for the sticky note.", ephemeral=True)

        sticky_texts[channel.id] = text  # remember the text

        existing_id = sticky_messages.get(channel.id)
        if existing_id:
            try:
                msg = await channel.fetch_message(existing_id)
                await msg.edit(content=text)
                return await ctx.respond("Sticky note updated.", ephemeral=True)
            except discord.NotFound:
                pass  # message got deleted

        # Create new sticky
        msg = await channel.send(text)
        sticky_messages[channel.id] = msg.id
        return await ctx.respond("Sticky note created.", ephemeral=True)

    # ────────── CLEAR STICKY ──────────
    elif action == "clear":
        existing_id = sticky_messages.get(channel.id)
        if not existing_id:
            return await ctx.respond("There is no sticky note in this channel.", ephemeral=True)

        try:
            msg = await channel.fetch_message(existing_id)
            await msg.delete()
        except discord.NotFound:
            pass

        sticky_messages.pop(channel.id, None)
        sticky_texts.pop(channel.id, None)
        return await ctx.respond("Sticky note cleared.", ephemeral=True)

# ────────────────────── EVENTS ──────────────────────
@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")
    bot.loop.create_task(status_updater())
    bot.loop.create_task(twitch_watcher())

    # Try to add reactions to the reaction-role message
    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                msg = await channel.fetch_message(REACTION_ROLE_MESSAGE_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

            # Add all reaction emojis
            for emoji in reaction_roles.keys():
                try:
                    await msg.add_reaction(emoji)
                except discord.HTTPException:
                    pass

            print("Reaction roles: reactions added to message.")
            return  # stop after first match

@bot.event
async def on_member_join(member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch:
        msg = WELCOME_TEXT.replace("{mention}", member.mention)
        await ch.send(msg)


@bot.event
async def on_member_update(before, after):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if not ch:
        return
    if before.premium_since is None and after.premium_since is not None:
        await ch.send(BOOST_TEXT.replace("{mention}", after.mention))
    new_roles = set(after.roles) - set(before.roles)
    for role in new_roles:
        if role.id == ROLE_TO_WATCH:
            await ch.send(VIP_TEXT.replace("{mention}", after.mention))


@bot.event
async def on_message(message: discord.Message):
    # Ignore bot messages (including this bot)
    if message.author.bot:
        return

    channel = message.channel

    # Only do sticky behavior if this channel has one configured
    if channel.id not in sticky_texts:
        return

    # Delete old sticky if it exists
    old_id = sticky_messages.get(channel.id)
    if old_id:
        try:
            old_msg = await channel.fetch_message(old_id)
            await old_msg.delete()
        except discord.NotFound:
            pass

    # Re-send sticky at the bottom
    text = sticky_texts[channel.id]
    new_msg = await channel.send(text)
    sticky_messages[channel.id] = new_msg.id

# ────────────────────── MODERATION LOG EVENTS ──────────────────────

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    """Log bans with moderator if possible."""
    moderator = None
    try:
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:
                moderator = entry.user
                break
    except discord.Forbidden:
        pass

    mod_text = moderator.mention if moderator else "Unknown"
    await log_to_thread(f"{user.mention} was banned by {mod_text}")


@bot.event
async def on_member_remove(member: discord.Member):
    """Distinguish between kick and leave; skip bans (handled in on_member_ban)."""
    guild = member.guild
    now = discord.utils.utcnow()

    # Check if this was a recent ban; if so, skip (on_member_ban already logged it)
    try:
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if entry.target.id == member.id:
                if (now - entry.created_at).total_seconds() < 10:
                    return
    except discord.Forbidden:
        pass

    # Check for recent kick
    moderator = None
    is_kick = False
    try:
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id:
                if (now - entry.created_at).total_seconds() < 10:
                    moderator = entry.user
                    is_kick = True
                    break
    except discord.Forbidden:
        pass

    if is_kick:
        mod_text = moderator.mention if moderator else "Unknown"
        await log_to_thread(f"{member.mention} was kicked by {mod_text}")
    else:
        await log_to_thread(f"{member.mention} has left the server")

# ────────────────────── REACTION ROLE EVENTS ──────────────────────

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.message_id != REACTION_ROLE_MESSAGE_ID:
        return

    emoji_name = payload.emoji.name
    if emoji_name not in reaction_roles:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    role_id = reaction_roles[emoji_name]
    role = guild.get_role(role_id)
    if role is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    try:
        await member.add_roles(role, reason="Reaction role")
    except discord.HTTPException:
        pass


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.message_id != REACTION_ROLE_MESSAGE_ID:
        return

    emoji_name = payload.emoji.name
    if emoji_name not in reaction_roles:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    role_id = reaction_roles[emoji_name]
    role = guild.get_role(role_id)
    if role is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None or member.bot:
        return

    try:
        await member.remove_roles(role, reason="Reaction role removed")
    except discord.HTTPException:
        pass

# ────────────────────── STATUS UPDATE MSG ──────────────────────
async def status_updater():
    await bot.wait_until_ready()
    print("Channel Status updater STARTED — no spam on restart, silent when empty")

    # Read current status on startup so we don't announce it again
    vc = bot.get_channel(STATUS_VC_ID)
    initial_status = None
    if vc and isinstance(vc, discord.VoiceChannel):
        initial_status = str(vc.status or "").strip()
        if initial_status:
            print(f"Bot started → current status is '{initial_status}' → no auto-message")
        else:
            print("Bot started → status is empty → staying silent")
    last_status = initial_status if initial_status else None

    while not bot.is_closed():
        await asyncio.sleep(10)

        if STATUS_VC_ID == 0 or STATUS_LOG_CHANNEL_ID == 0:
            continue

        vc = bot.get_channel(STATUS_VC_ID)
        log_ch = bot.get_channel(STATUS_LOG_CHANNEL_ID)
        if not vc or not log_ch or not isinstance(vc, discord.VoiceChannel):
            continue

        raw_status = str(vc.status or "").strip()

        # Empty status → do nothing
        if not raw_status:
            if last_status is not None:
                print("Status cleared → staying silent")
                last_status = None
            continue

        # Same as last announced → stay silent
        if raw_status == last_status:
            continue

        # ←←← NEW STATUS → send fresh message ←←←
        embed = discord.Embed(color=0x2e2f33)
        embed.title = raw_status
        embed.description = (
            "Playing all day. Feel free to coordinate with others in chat "
            "if you want to plan a group watch later in the day."
        )
        embed.set_footer(text=f"Updated • {discord.utils.utcnow().strftime('%b %d • %I:%M %p UTC')}")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label=BUTTON_1_LABEL, url=BUTTON_1_URL, style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label=BUTTON_3_LABEL, url=BUTTON_3_URL, style=discord.ButtonStyle.link, emoji="🎟️"))

        await log_ch.send(embed=embed, view=view)
        print(f"New status → '{raw_status}' → fresh message sent")

        last_status = raw_status


# ────────────────────── TWITCH API HELPERS ──────────────────────

async def get_twitch_token():
    """
    Get an app access token from Twitch using client credentials.
    """
    global twitch_access_token

    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        print("Twitch: CLIENT_ID or CLIENT_SECRET not set; skipping Twitch checks.")
        return None

    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as resp:
            if resp.status != 200:
                print(f"Twitch token error: HTTP {resp.status}")
                twitch_access_token = None
                return None
            data = await resp.json()
            twitch_access_token = data.get("access_token")
            print("Twitch: obtained new access token")
            return twitch_access_token


async def fetch_twitch_streams():
    """
    Fetch live stream data for all configured Twitch channels.
    Returns a mapping: login_name -> stream_data
    """
    global twitch_access_token

    if not TWITCH_CHANNELS:
        return {}

    if not twitch_access_token:
        token = await get_twitch_token()
        if not token:
            return {}

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {twitch_access_token}",
    }

    url = "https://api.twitch.tv/helix/streams"
    # multiple user_login params: ?user_login=a&user_login=b
    params = [("user_login", name) for name in TWITCH_CHANNELS]

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 401:
                # token expired, retry once
                print("Twitch: token expired, refreshing")
                twitch_access_token = None
                token = await get_twitch_token()
                if not token:
                    return {}
                headers["Authorization"] = f"Bearer {twitch_access_token}"
                async with session.get(url, headers=headers, params=params) as resp2:
                    if resp2.status != 200:
                        print(f"Twitch fetch error after refresh: HTTP {resp2.status}")
                        return {}
                    data = await resp2.json()
            elif resp.status != 200:
                print(f"Twitch fetch error: HTTP {resp.status}")
                return {}
            else:
                data = await resp.json()

    streams = data.get("data", [])
    result = {}
    for s in streams:
        login = s.get("user_login", "").lower()
        if login:
            result[login] = s
    return result


# ────────────────────── TWITCH WATCHER TASK ──────────────────────

async def twitch_watcher():
    """
    Periodically checks Twitch for the configured channels and sends
    a message when they go live.

    Message format:
    <:twitch:...> {username} is live ┃ {url}
    -# @everyone
    """
    await bot.wait_until_ready()
    print("Twitch watcher started")

    if TWITCH_ANNOUNCE_CHANNEL_ID == 0:
        print("Twitch: TWITCH_ANNOUNCE_CHANNEL_ID is 0; watcher is idle.")
        return

    announce_ch = bot.get_channel(TWITCH_ANNOUNCE_CHANNEL_ID)
    if not announce_ch:
        print("Twitch: announce channel not found; watcher is idle.")
        return

    # initialize state
    for name in TWITCH_CHANNELS:
        twitch_live_state[name] = False

    while not bot.is_closed():
        streams = await fetch_twitch_streams()

        # mark which are live this check
        live_now = {name: False for name in TWITCH_CHANNELS}
        for login, s in streams.items():
            if login in live_now:
                live_now[login] = True

        # for each tracked channel, compare previous state and announce transitions
        for name in TWITCH_CHANNELS:
            was_live = twitch_live_state.get(name, False)
            is_live = live_now.get(name, False)

            # went live
            if is_live and not was_live:
                twitch_live_state[name] = True
                url = f"https://twitch.tv/{name}"
                username = name  # or customize display names here

                msg = f"{TWITCH_EMOJI} {username} is live ┃ {url}\n-# @everyone"
                try:
                    await announce_ch.send(msg)
                    print(f"Twitch: announced live for {name}")
                except Exception as e:
                    print(f"Twitch: failed to send message for {name}: {e}")

            # went offline
            if not is_live and was_live:
                twitch_live_state[name] = False
                print(f"Twitch: {name} went offline")

        # wait before next check
        await asyncio.sleep(60)  # 60 seconds
        

# ────────────────────── START BOT ──────────────────────
bot.run(os.getenv("TOKEN"))
