import discord
import os
import asyncio
import aiohttp  # NEW

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = discord.Bot(intents=intents)

# ────────────────────── CONFIG ──────────────────────
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "1207917070684004452"))
ROLE_TO_WATCH = int(os.getenv("ROLE_TO_WATCH", "1217937235840598026"))
BIRTHDAY_FORM_LINK = os.getenv("BIRTHDAY_FORM_LINK", "https://discord.com/channels/1205041211610501120/1435375785220243598")

WELCOME_TEXT = os.getenv("WELCOME_TEXT", "<:welcome:1435084504950640690> @{mention} just joined the server!")
BOOST_TEXT   = os.getenv("BOOST_TEXT", "<:boost:1435140623714877460> @{mention} just boosted the server!")
VIP_TEXT     = os.getenv("VIP_TEXT", "<a:pepebirthday:1296553298895310971> It's @{mention}'s birthday!\n-# @everyone")
BUTTON_LABEL = os.getenv("BUTTON_LABEL", "Add Your Birthday")

STATUS_VC_ID          = int(os.getenv("STATUS_VC_ID", "0"))
STATUS_LOG_CHANNEL_ID  = int(os.getenv("STATUS_LOG_CHANNEL_ID", "0"))
BUTTON_1_LABEL         = os.getenv("BUTTON_1_LABEL", "Showtimes")
BUTTON_1_URL           = os.getenv("BUTTON_1_URL", "https://example.com")
BUTTON_2_LABEL         = os.getenv("BUTTON_2_LABEL", "Other Movies/Shows")
BUTTON_2_URL           = os.getenv("BUTTON_2_URL", "https://example.com")
BUTTON_3_LABEL         = os.getenv("BUTTON_3_LABEL", "More")
BUTTON_3_URL           = os.getenv("BUTTON_3_URL", "https://example.com")

# ─────── TWITCH CONFIG (DIRECT VIA TWITCH API) ───────
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")

# Comma-separated list of Twitch channel names, defaulting to your two:
TWITCH_CHANNELS = [c.strip().lower() for c in os.getenv("TWITCH_CHANNELS", "treyevreux,vokulnero").split(",") if c.strip()]

# Channel where announcements are sent
TWITCH_ANNOUNCE_CHANNEL_ID = int(os.getenv("TWITCH_ANNOUNCE_CHANNEL_ID", "0"))

TWITCH_EMOJI = "<:twitch:1435152655990259773>"

# Runtime state
twitch_access_token: str | None = None
twitch_live_state: dict[str, bool] = {}  # channel_name -> is_live


# ────────────────────── /say COMMAND ──────────────────────
@bot.slash_command(name="say", description="Make the bot say something right here")
async def say(ctx, message: discord.Option(str, "Message to send", required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)
    
    await ctx.channel.send(message)
    await ctx.respond("Sent!", ephemeral=True)


# ────────────────────── EVENTS ──────────────────────
@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")
    bot.loop.create_task(status_updater())
    bot.loop.create_task(twitch_watcher())  # NEW


@bot.event
async def on_member_join(member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch:
        msg = WELCOME_TEXT.replace("{mention}", member.mention)
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label=BUTTON_LABEL, style=discord.ButtonStyle.secondary, url=BIRTHDAY_FORM_LINK))
        await ch.send(msg, view=view)


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
        embed.description = "Playing all day. Feel free to coordinate with others in chat if you want to plan a group watch later in the day."
        embed.set_footer(text=f"Updated • {discord.utils.utcnow().strftime('%b %d • %I:%M %p UTC')}")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label=BUTTON_1_LABEL, url=BUTTON_1_URL, style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label=BUTTON_2_LABEL, url=BUTTON_2_URL, style=discord.ButtonStyle.link))
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
