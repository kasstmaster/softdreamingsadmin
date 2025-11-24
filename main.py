import discord
import os
import asyncio
import aiohttp
import json
from datetime import datetime  # new

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

DEBUG_GUILD_ID = int(os.getenv("DEBUG_GUILD_ID"))

bot = discord.Bot(
    intents=intents,
    debug_guilds=[DEBUG_GUILD_ID]
)

# ────────────────────── CONFIG ──────────────────────
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID"))
ROLE_TO_WATCH = int(os.getenv("ROLE_TO_WATCH"))

WELCOME_TEXT = os.getenv("WELCOME_TEXT")
BOOST_TEXT   = os.getenv("BOOST_TEXT")
VIP_TEXT     = os.getenv("VIP_TEXT")

MEMBER_JOIN_ROLE_ID = int(os.getenv("MEMBER_JOIN_ROLE_ID"))  # role after 24h
BOT_JOIN_ROLE_ID    = int(os.getenv("BOT_JOIN_ROLE_ID"))     # role instantly for bots

# ─────── TWITCH CONFIG (DIRECT VIA TWITCH API) ───────
TWITCH_CLIENT_ID     = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")

TWITCH_CHANNELS = [c.strip().lower() for c in os.getenv("TWITCH_CHANNELS").split(",") if c.strip()]

TWITCH_ANNOUNCE_CHANNEL_ID = int(os.getenv("TWITCH_ANNOUNCE_CHANNEL_ID"))

TWITCH_EMOJI = os.getenv("TWITCH_EMOJI")

twitch_access_token: str | None = None
twitch_live_state: dict[str, bool] = {}

# ────────────────────── REACTION ROLES CONFIG (ALL FROM ENV) ──────────────────────

REACTION_ROLE_MESSAGE_ID = int(os.getenv("REACTION_ROLE_MESSAGE_ID"))

reaction_roles = {}

_raw_pairs = os.getenv("REACTION_ROLES", "")
if _raw_pairs:
    for pair in _raw_pairs.split(","):
        if ":" in pair:
            emoji, role_id = pair.split(":", 1)
            emoji = emoji.strip()
            role_id = role_id.strip()
            if role_id.isdigit():
                reaction_roles[emoji] = int(role_id)

# ────────────────────── MOD LOG THREAD ──────────────────────

MOD_LOG_THREAD_ID = int(os.getenv("MOD_LOG_THREAD_ID"))


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

# ────────────────────── DEAD CHAT CONFIG ──────────────────────

DEAD_CHAT_ROLE_ID = int(os.getenv("DEAD_CHAT_ROLE_ID", "0"))

# Comma-separated list of channel IDs to watch for dead chat
DEAD_CHAT_CHANNEL_IDS = [
    int(x.strip()) for x in os.getenv("DEAD_CHAT_CHANNEL_IDS", "").split(",")
    if x.strip().isdigit()
]

# Time with no messages before someone can steal the role (seconds)
DEAD_CHAT_IDLE_SECONDS = int(os.getenv("DEAD_CHAT_IDLE_SECONDS", "600"))  # default 10 min

# Cooldown between wins for the same user (seconds)
DEAD_CHAT_COOLDOWN_SECONDS = int(os.getenv("DEAD_CHAT_COOLDOWN_SECONDS", "0"))  # e.g. 1800 for 30 min

# Users completely ignored by Dead Chat (their messages don't reset timer and can't win)
IGNORE_MEMBER_IDS = {
    775970689525612555
}

# State
dead_last_message_time: dict[int, datetime] = {}          # per channel id
dead_current_holder_id: int | None = None
dead_last_notice_message_ids: dict[int, int | None] = {}  # per channel id
dead_last_win_time: dict[int, datetime] = {}              # per user id

# ────────────────────── /say COMMAND ──────────────────────

@bot.slash_command(name="say", description="Make the bot say something right here")
async def say(ctx, message: discord.Option(str, "Message to send", required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)
    
    await ctx.channel.send(message.replace("\\n", "\n"))
    await ctx.respond("Sent!", ephemeral=True)

# ────────────────────── /birthday_announce COMMAND ──────────────────────

@bot.slash_command(
    name="birthday_announce",
    description="Manually send the birthday message for a member"
)
async def birthday_announce(
    ctx: discord.ApplicationContext,
    member: discord.Option(discord.Member, "Member whose birthday message to send", required=True),
):
    # Only admins can run this
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator to use this.", ephemeral=True)

    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if not ch:
        return await ctx.respond("Birthday announcement channel (WELCOME_CHANNEL_ID) not found.", ephemeral=True)

    # Build the message using the same template as ROLE_TO_WATCH
    if VIP_TEXT:
        msg = VIP_TEXT.replace("{mention}", member.mention)
    else:
        msg = f"Happy birthday, {member.mention}!"

    try:
        await ch.send(msg)
    except Exception as e:
        return await ctx.respond(f"Failed to send birthday message: `{e}`", ephemeral=True)

    await ctx.respond(f"Sent birthday message for {member.mention}.", ephemeral=True)

# ────────────────────── PRIZE VIEWS ──────────────────────

class BasePrizeView(discord.ui.View):
    gift_title: str = ""
    rarity: str = ""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim Your Prize!", style=discord.ButtonStyle.primary)
    async def claim_button(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction
    ):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                "This can only be used in a server.",
                ephemeral=True
            )

        # Delete the prize message
        try:
            await interaction.message.delete()
        except Exception:
            pass

        # Get Dead Chat role mention
        dead_role = guild.get_role(DEAD_CHAT_ROLE_ID)
        role_mention = dead_role.mention if dead_role else "the Dead Chat role"

        # Winner announcement
        ch = guild.get_channel(WELCOME_CHANNEL_ID)
        if ch:
            await ch.send(
                f"<:prize:1441586959909781666> {interaction.user.mention} has won a **{self.gift_title}** "
                f"with the {role_mention} role!\n"
                f"-# *Drop Rate: {self.rarity}*"
            )

        # Ephemeral confirmation
        await interaction.response.send_message(
            f"You claimed a **{self.gift_title}**!",
            ephemeral=True
        )


class MoviePrizeView(BasePrizeView):
    gift_title = "Movie Request"
    rarity = "Common"


class NitroPrizeView(BasePrizeView):
    gift_title = "Month of Nitro Basic"
    rarity = "Uncommon"


class SteamPrizeView(BasePrizeView):
    gift_title = "Steam Gift Card"
    rarity = "Rare"

# ────────────────────── EDIT BOT MSG ──────────────────────

@bot.slash_command(
    name="editbotmsg",
    description="Edit a message previously sent by this bot (paste message link)"
)
async def editbotmsg(
    ctx: discord.ApplicationContext,
    message_link: discord.Option(
        str,
        "Message link or ID (right-click → Copy Message Link)",
        required=True,
    ),
    new_text: discord.Option(
        str,
        "New message content",
        required=True,
    ),
):
    # Admin check
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator to use this.", ephemeral=True)

    guild = ctx.guild
    if guild is None:
        return await ctx.respond("This command can only be used in a server.", ephemeral=True)

    # Try to parse link or bare ID
    channel_id = None
    message_id = None

    # Full link: https://discord.com/channels/guild_id/channel_id/message_id
    if "discord.com/channels/" in message_link:
        try:
            parts = message_link.strip().split("/")
            # ... /channels/{guild}/{channel}/{message}
            link_guild_id = int(parts[-3])
            channel_id = int(parts[-2])
            message_id = int(parts[-1])

            if link_guild_id != guild.id:
                return await ctx.respond(
                    "That message link is from a different server.",
                    ephemeral=True
                )
        except Exception:
            return await ctx.respond("I couldn't parse that message link.", ephemeral=True)
    else:
        # If they pasted just a numeric ID, fail with a helpful message
        return await ctx.respond(
            "Please paste the full **message link** (Right-click → Copy Message Link).",
            ephemeral=True
        )

    channel = guild.get_channel(channel_id)
    if channel is None:
        return await ctx.respond("I can't find that channel.", ephemeral=True)

    try:
        msg = await channel.fetch_message(message_id)
    except Exception:
        return await ctx.respond("I couldn't fetch that message. Check the link.", ephemeral=True)

    # Ensure it's from *this* bot
    if msg.author != bot.user:
        return await ctx.respond("I can only edit messages **sent by me**.", ephemeral=True)

    # Edit message
    try:
        await msg.edit(content=new_text)
    except Exception as e:
        return await ctx.respond(f"Failed to edit message: `{e}`", ephemeral=True)

    await ctx.respond("Message updated.", ephemeral=True)

# ────────────────────── PRIZE SLASH COMMANDS ──────────────────────

@bot.slash_command(name="prize_movie", description="Send a Movie Request prize message")
async def prize_movie(ctx: discord.ApplicationContext):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator to use this.", ephemeral=True)

    content = (
        "**YOU'VE FOUND A PRIZE!**\n"
        "Prize: *Movie Request*\n"
        "Drop Rate: *Common*"
    )
    await ctx.respond(content, view=MoviePrizeView())


@bot.slash_command(name="prize_nitro", description="Send a Nitro Basic prize message")
async def prize_nitro(ctx: discord.ApplicationContext):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator to use this.", ephemeral=True)

    content = (
        "**YOU'VE FOUND A PRIZE!**\n"
        "Prize: *Month of Nitro Basic*\n"
        "Drop Rate: *Uncommon*"
    )
    await ctx.respond(content, view=NitroPrizeView())


@bot.slash_command(name="prize_steam", description="Send a Steam Gift Card prize message")
async def prize_steam(ctx: discord.ApplicationContext):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator to use this.", ephemeral=True)

    content = (
        "**YOU'VE FOUND A PRIZE!**\n"
        "Prize: *Steam Gift Card*\n"
        "Drop Rate: *Rare*"
    )
    await ctx.respond(content, view=SteamPrizeView())

# ────────────────────── MANUAL PRIZE ANNOUNCE ──────────────────────

PRIZE_DEFS = {
    "Movie Request": "Common",
    "Month of Nitro Basic": "Uncommon",
    "Steam Gift Card": "Rare",
}

@bot.slash_command(
    name="prize_announce",
    description="Manually announce a predefined prize winner in this channel"
)
async def prize_announce(
    ctx: discord.ApplicationContext,
    member: discord.Option(discord.Member, "User who won the prize", required=True),
    prize: discord.Option(
        str,
        "Select a prize",
        choices=list(PRIZE_DEFS.keys()),
        required=True,
    ),
):
    # Admin check
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator to use this.", ephemeral=True)

    guild = ctx.guild
    if guild is None:
        return await ctx.respond("This command can only be used in a server.", ephemeral=True)

    # Map prize -> rarity
    gift_title = prize
    rarity = PRIZE_DEFS.get(prize, "Unknown")

    # Dead Chat role mention (if configured)
    dead_role = guild.get_role(DEAD_CHAT_ROLE_ID)
    role_mention = dead_role.mention if dead_role else "the Dead Chat role"

    # Send in the channel where the command was used
    ch = ctx.channel

    await ch.send(
        f"<:prize:1441586959909781666> {member.mention} has won a **{gift_title}** with the {role_mention} role!\n"
        f"-# *Drop Rate: {rarity}*"
    )

    await ctx.respond("Prize announcement sent.", ephemeral=True)

# ────────────────────── STICKY NOTES ──────────────────────

sticky_messages: dict[int, int] = {}
sticky_texts: dict[int, str] = {}

@bot.slash_command(name="sticky", description="Create or clear a sticky note in this channel")
async def sticky(
    ctx,
    action: discord.Option(str, "Action", choices=["set", "clear"], required=True),
    text: discord.Option(str, "Sticky note text", required=False)
):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)

    channel = ctx.channel

    # ────────── SET STICKY ──────────
    if action == "set":
        if not text:
            return await ctx.respond("You must provide text for the sticky note.", ephemeral=True)

        sticky_texts[channel.id] = text 

        existing_id = sticky_messages.get(channel.id)
        if existing_id:
            try:
                msg = await channel.fetch_message(existing_id)
                await msg.edit(content=text)
                await ctx.respond("Sticky note updated.", ephemeral=True)
            except discord.NotFound:
                # Message disappeared; create a new one
                msg = await channel.send(text)
                sticky_messages[channel.id] = msg.id
                await ctx.respond("Sticky note created.", ephemeral=True)
        else:
            msg = await channel.send(text)
            sticky_messages[channel.id] = msg.id
            await ctx.respond("Sticky note created.", ephemeral=True)

        # Save to storage
        await save_stickies()
        return

    # ────────── CLEAR STICKY ──────────
    elif action == "clear":
        existing_id = sticky_messages.get(channel.id)
        if existing_id:
            try:
                msg = await channel.fetch_message(existing_id)
                await msg.delete()
            except discord.NotFound:
                pass

        sticky_messages.pop(channel.id, None)
        sticky_texts.pop(channel.id, None)

        # Save to storage
        await save_stickies()

        return await ctx.respond("Sticky note cleared.", ephemeral=True)

# Where to store sticky data as JSON
# Set this to the SAME channel you use for birthday backups
STICKY_STORAGE_CHANNEL_ID = int(os.getenv("STICKY_STORAGE_CHANNEL_ID", "0"))

# The message in that channel that holds the JSON blob
sticky_storage_message_id: int | None = None

async def init_sticky_storage():
    """
    Find or create the sticky storage message in STICKY_STORAGE_CHANNEL_ID,
    and load sticky_texts / sticky_messages from it.
    """
    global sticky_storage_message_id, sticky_texts, sticky_messages

    if STICKY_STORAGE_CHANNEL_ID == 0:
        print("[Sticky] STICKY_STORAGE_CHANNEL_ID is 0 → persistence disabled.")
        return

    ch = bot.get_channel(STICKY_STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        print(f"[Sticky] Storage channel {STICKY_STORAGE_CHANNEL_ID} not found or not a text channel.")
        return

    # Look for an existing storage message
    storage_msg = None
    try:
        async for msg in ch.history(limit=50, oldest_first=True):
            if msg.author == bot.user and msg.content.startswith("STICKY_DATA:"):
                storage_msg = msg
                break
    except discord.Forbidden:
        print(f"[Sticky] No permission to read history in {STICKY_STORAGE_CHANNEL_ID}")
        return

    if storage_msg is None:
        # Create a new storage message
        storage_msg = await ch.send("STICKY_DATA:{}")
        print(f"[Sticky] Created new storage message in {ch.mention} (id={storage_msg.id})")
    else:
        print(f"[Sticky] Found existing storage message (id={storage_msg.id})")

    sticky_storage_message_id = storage_msg.id

    # Parse JSON
    data_str = storage_msg.content[len("STICKY_DATA:"):]
    if not data_str.strip():
        return

    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        print("[Sticky] Failed to parse storage JSON, starting fresh.")
        return

    # Expect: { channel_id_str: { "text": str, "message_id": int_or_null } }
    for chan_id_str, info in data.items():
        try:
            cid = int(chan_id_str)
        except ValueError:
            continue

        text = info.get("text")
        msg_id = info.get("message_id")

        if isinstance(text, str):
            sticky_texts[cid] = text
        if isinstance(msg_id, int):
            sticky_messages[cid] = msg_id

    print(f"[Sticky] Loaded {len(sticky_texts)} sticky entries from storage.")


async def save_stickies():
    """
    Save sticky_texts / sticky_messages to the storage message as JSON.
    """
    global sticky_storage_message_id

    if STICKY_STORAGE_CHANNEL_ID == 0 or sticky_storage_message_id is None:
        return

    ch = bot.get_channel(STICKY_STORAGE_CHANNEL_ID)
    if not isinstance(ch, discord.TextChannel):
        return

    try:
        msg = await ch.fetch_message(sticky_storage_message_id)
    except discord.NotFound:
        # Storage message vanished; re-init next time
        print("[Sticky] Storage message not found; will re-init on next startup.")
        sticky_storage_message_id = None
        return

    data = {}
    for cid, text in sticky_texts.items():
        entry = {"text": text}
        msg_id = sticky_messages.get(cid)
        if msg_id is not None:
            entry["message_id"] = msg_id
        data[str(cid)] = entry

    payload = "STICKY_DATA:" + json.dumps(data)
    try:
        await msg.edit(content=payload)
    except discord.Forbidden:
        print("[Sticky] Forbidden editing storage message.")

# ────────────────────── DEAD CHAT HELPERS ──────────────────────

async def initialize_dead_chat():
    global dead_current_holder_id

    if not DEAD_CHAT_CHANNEL_IDS or DEAD_CHAT_ROLE_ID == 0:
        print("DeadChat: not configured; skipping init.")
        return

    # Determine current holder from role membership
    for guild in bot.guilds:
        role = guild.get_role(DEAD_CHAT_ROLE_ID)
        if role:
            if role.members:
                holder = role.members[0]
                dead_current_holder_id = holder.id
                print(f"DeadChat: startup holder is {holder} ({holder.id})")
            break

    # Initialize last activity per channel
    for chan_id in DEAD_CHAT_CHANNEL_IDS:
        ch = bot.get_channel(chan_id)
        if not isinstance(ch, discord.TextChannel):
            print(f"DeadChat: channel {chan_id} not found or not text.")
            continue

        try:
            async for msg in ch.history(limit=50):
                # Ignore bots and ignored users
                if msg.author.bot:
                    continue
                if msg.author.id in IGNORE_MEMBER_IDS:
                    continue

                dead_last_message_time[chan_id] = msg.created_at
                break
        except discord.Forbidden:
            print(f"DeadChat: no permission to read history in {chan_id}")
            continue

        # If no non-bot / non-ignored message found, use now
        dead_last_message_time.setdefault(chan_id, discord.utils.utcnow())
        dead_last_notice_message_ids.setdefault(chan_id, None)

    print("DeadChat: initialization complete.")


async def handle_dead_chat_message(message: discord.Message):
    global dead_current_holder_id

    if DEAD_CHAT_ROLE_ID == 0 or not DEAD_CHAT_CHANNEL_IDS:
        return

    channel = message.channel
    if channel.id not in DEAD_CHAT_CHANNEL_IDS:
        return

    # Completely ignore certain users (their messages do NOT reset timer
    # and they can NOT win Dead Chat)
    if message.author.id in IGNORE_MEMBER_IDS:
        return

    now = discord.utils.utcnow()
    last_time = dead_last_message_time.get(channel.id)
    dead_last_message_time[channel.id] = now  # always update

    # First time after boot for this channel
    if last_time is None:
        return

    idle_seconds = (now - last_time).total_seconds()
    if idle_seconds < DEAD_CHAT_IDLE_SECONDS:
        # Not dead long enough
        return

    guild = message.guild
    if guild is None:
        return

    role = guild.get_role(DEAD_CHAT_ROLE_ID)
    if role is None:
        print("DeadChat: role not found.")
        return

    member = message.author

    # Ignore if they already have the role
    if role in member.roles:
        return

    # Cooldown between wins for same user
    if DEAD_CHAT_COOLDOWN_SECONDS > 0:
        last_win = dead_last_win_time.get(member.id)
        if last_win is not None:
            since_win = (now - last_win).total_seconds()
            if since_win < DEAD_CHAT_COOLDOWN_SECONDS:
                print(f"DeadChat: {member} is on cooldown, not granting role.")
                return

    # Remove role from previous holder
    if dead_current_holder_id is not None:
        prev = guild.get_member(dead_current_holder_id)
        if prev and role in prev.roles:
            try:
                await prev.remove_roles(role, reason="Dead Chat stolen")
            except discord.Forbidden:
                print("DeadChat: no permission to remove role from previous holder.")

    # Give role to new holder
    try:
        await member.add_roles(role, reason="Dead Chat claimed")
    except discord.Forbidden:
        print("DeadChat: no permission to add role to new holder.")
        return

    dead_current_holder_id = member.id
    dead_last_win_time[member.id] = now

    # Delete previous notices in all watched channels
    for cid, msg_id in list(dead_last_notice_message_ids.items()):
        if msg_id is None:
            continue
        ch = guild.get_channel(cid)
        if not ch:
            continue
        try:
            old_msg = await ch.fetch_message(msg_id)
            await old_msg.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        dead_last_notice_message_ids[cid] = None

    # Post new notice in current channel
    minutes = DEAD_CHAT_IDLE_SECONDS // 60
    notice = await channel.send(
    f"{member.mention} has stolen the {role.mention} role after {minutes} minutes of silence.\n"
    f"-# There's a random chance to win prizes with this role."
    )
    dead_last_notice_message_ids[channel.id] = notice.id

# ────────────────────── EVENTS ──────────────────────

@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")
    bot.loop.create_task(twitch_watcher())

    # Reaction roles: add reactions to the configured message
    found = False
    for guild in bot.guilds:
        if found:
            break
        for channel in guild.text_channels:
            try:
                msg = await channel.fetch_message(REACTION_ROLE_MESSAGE_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

            for emoji in reaction_roles.keys():
                try:
                    await msg.add_reaction(emoji)
                except discord.HTTPException:
                    pass

            print("Reaction roles: reactions added to message.")
            found = True
            break

    # Initialize Dead Chat after startup
    await initialize_dead_chat()

    # Initialize sticky storage (load persisted stickies)
    await init_sticky_storage()


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
    # Abuse control: ignore all bots
    if message.author.bot:
        return

    channel = message.channel

    # Dead Chat handler
    await handle_dead_chat_message(message)

    # Sticky note handler
    if channel.id in sticky_texts:
        old_id = sticky_messages.get(channel.id)
        if old_id:
            try:
                old_msg = await channel.fetch_message(old_id)
                await old_msg.delete()
            except discord.NotFound:
                pass

        text = sticky_texts[channel.id]
        new_msg = await channel.send(text)
        sticky_messages[channel.id] = new_msg.id

        # Persist updated message id
        await save_stickies()


@bot.event
async def on_member_join(member: discord.Member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch:
        msg = WELCOME_TEXT.replace("{mention}", member.mention)
        await ch.send(msg)

    if member.bot and BOT_JOIN_ROLE_ID:
        role = member.guild.get_role(BOT_JOIN_ROLE_ID)
        if role:
            try:
                await member.add_roles(role, reason="Bot auto-role")
            except:
                pass
        return

    if not member.bot and MEMBER_JOIN_ROLE_ID:
        async def give_delayed_role():
            await asyncio.sleep(86400)  # 24 hours
            role = member.guild.get_role(MEMBER_JOIN_ROLE_ID)
            if role and member in member.guild.members:
                try:
                    await member.add_roles(role, reason="24h join role")
                except:
                    pass

        bot.loop.create_task(give_delayed_role())

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

    try:
        async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
            if entry.target.id == member.id:
                if (now - entry.created_at).total_seconds() < 10:
                    return
    except discord.Forbidden:
        pass

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
    params = [("user_login", name) for name in TWITCH_CHANNELS]

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as resp:
            if resp.status == 401:
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

    for name in TWITCH_CHANNELS:
        twitch_live_state[name] = False

    while not bot.is_closed():
        streams = await fetch_twitch_streams()

        live_now = {name: False for name in TWITCH_CHANNELS}
        for login, s in streams.items():
            if login in live_now:
                live_now[login] = True

        for name in TWITCH_CHANNELS:
            was_live = twitch_live_state.get(name, False)
            is_live = live_now.get(name, False)

            if is_live and not was_live:
                twitch_live_state[name] = True
                url = f"https://twitch.tv/{name}"
                username = name  

                msg = f"{TWITCH_EMOJI} {username} is live ┃ {url}\n-# @everyone"
                try:
                    await announce_ch.send(msg)
                    print(f"Twitch: announced live for {name}")
                except Exception as e:
                    print(f"Twitch: failed to send message for {name}: {e}")

            if not is_live and was_live:
                twitch_live_state[name] = False
                print(f"Twitch: {name} went offline")

        await asyncio.sleep(60) 

# ────────────────────── DEAD CHAT COLOR COMMAND ──────────────────────

COLOR_NAME_MAP = {
    "red":     0xFF0000,
    "blue":    0x0000FF,
    "green":   0x00FF00,
    "purple":  0x800080,
    "pink":    0xFFC0CB,
    "yellow":  0xFFFF00,
    "orange":  0xFFA500,
    "teal":    0x008080,
    "cyan":    0x00FFFF,
    "magenta": 0xFF00FF,
    "black":   0x000000,
    "white":   0xFFFFFF,
    "gray":    0x808080,
    "grey":    0x808080,
    "maroon":  0x800000,
    "navy":    0x000080,
    "lime":    0x32CD32,
    "gold":    0xFFD700
}

@bot.slash_command(name="color", description="Change the Dead Chat role color")
async def color(
    ctx: discord.ApplicationContext,
    color: discord.Option(str, "Hex or name (e.g. #ff0000, ff0000, red, pink)", required=True),
):
    if DEAD_CHAT_ROLE_ID == 0:
        await ctx.respond("Dead Chat role is not configured.", ephemeral=True)
        return

    guild = ctx.guild
    if guild is None:
        await ctx.respond("This command can only be used in a server.", ephemeral=True)
        return

    role = guild.get_role(DEAD_CHAT_ROLE_ID)
    if role is None:
        await ctx.respond("Dead Chat role not found.", ephemeral=True)
        return

    member = ctx.author
    if role not in member.roles:
        await ctx.respond("You don't have the Dead Chat role.", ephemeral=True)
        return

    raw = color.strip().lower()

    if raw in COLOR_NAME_MAP:
        color_int = COLOR_NAME_MAP[raw]
    else:
        value = raw
        if value.startswith("#"):
            value = value[1:]
        try:
            color_int = int(value, 16)
        except ValueError:
            valid_names = ", ".join(sorted(COLOR_NAME_MAP.keys()))
            await ctx.respond(
                "Use a valid hex color like `#ff0000` / `ff0000` "
                f"or one of these names: {valid_names}.",
                ephemeral=True
            )
            return

    try:
        await role.edit(color=discord.Color(color_int), reason="Dead Chat color change")
    except discord.Forbidden:
        await ctx.respond("I don't have permission to edit that role.", ephemeral=True)
        return

    await ctx.respond(f"Updated {role.name} color.", ephemeral=True)

# ────────────────────── START BOT ──────────────────────

bot.run(os.getenv("TOKEN"))
