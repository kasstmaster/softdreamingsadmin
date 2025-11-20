import discord
import os
import asyncio

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
VIP_TEXT     = os.getenv("VIP_TEXT", "<a:pepebirthday:1296553298895310971> It's @{mention}'s birthday! @everyone")
BUTTON_LABEL = os.getenv("BUTTON_LABEL", "Add Your Birthday")

STATUS_VC_ID_          = int(os.getenv("STATUS_VC_ID_", "0"))
STATUS_LOG_CHANNEL_ID  = int(os.getenv("STATUS_LOG_CHANNEL_ID", "0"))
BUTTON_1_LABEL         = os.getenv("BUTTON_1_LABEL", "Showtimes")
BUTTON_1_URL           = os.getenv("BUTTON_1_URL", "https://example.com")
BUTTON_2_LABEL         = os.getenv("BUTTON_2_LABEL", "Other Movies/Shows")
BUTTON_2_URL           = os.getenv("BUTTON_2_URL", "https://example.com")

# ────────────────────── WORKING /say FOR CHANNELS + THREADS ──────────────────────
@bot.slash_command(name="say", description="Send a message to any channel or thread")
async def say(
    ctx,
    destination: discord.Option(str, "Channel or thread (paste link or mention)", required=True),
    message: discord.Option(str, "Message to send", required=True)
):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator to use this.", ephemeral=True)

    # Extract ID from mention or link
    match = discord.utils.find(lambda m: m.isdigit(), destination.split())
    if not match:
        return await ctx.respond("Couldn't find a channel/thread ID. Mention it or paste a link.", ephemeral=True)

    channel_id = int(match)
    channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)

    if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread, discord.ForumChannel)):
        return await ctx.respond("That's not a valid text channel or thread.", ephemeral=True)

    if not channel.permissions_for(ctx.guild.me).send_messages:
        return await ctx.respond("I don't have permission to send messages there.", ephemeral=True)

    await channel.send(message)
    await ctx.respond(f"Sent to {channel.mention}!", ephemeral=True)

# ────────────────────── REST OF YOUR CODE (unchanged) ──────────────────────
@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")
    bot.loop.create_task(status_updater())

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
    if not ch: return
    if before.premium_since is None and after.premium_since is not None:
        await ch.send(BOOST_TEXT.replace("{mention}", after.mention))
    new_roles = set(after.roles) - set(before.roles)
    for role in new_roles:
        if role.id == ROLE_TO_WATCH:
            await ch.send(VIP_TEXT.replace("{mention}", after.mention))

async def status_updater():
    await bot.wait_until_ready()
    print("Channel Status updater STARTED — one permanent message")
    last_status = None          # will be None or actual string (including empty)
    message = None

    while not bot.is_closed():
        await asyncio.sleep(10)

        if STATUS_VC_ID_ == 0 or STATUS_LOG_CHANNEL_ID == 0:
            continue

        vc = bot.get_channel(STATUS_VC_ID_)
        log_ch = bot.get_channel(STATUS_LOG_CHANNEL_ID)
        if not vc or not log_ch or not isinstance(vc, discord.VoiceChannel):
            continue

        current_status = vc.status or ""        # ← keep empty string as-is, don't fallback yet

        # Only trigger when it actually changes
        if current_status == last_status:
            continue

        # Build title — only show "Channel Status" when truly empty
        title = current_status if current_status else "Channel Status"

        embed = discord.Embed(color=0x00ffae)
        embed.title = title
        embed.description = "Playing all day. Feel free to coordinate with others in chat if you want to plan a group watch later in the day."
        embed.set_footer(text=f"Updated • {discord.utils.utcnow().strftime('%b %d • %I:%M %p UTC')}")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label=BUTTON_1_LABEL, url=BUTTON_1_URL, style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label=BUTTON_2_LABEL, url=BUTTON_2_URL, style=discord.ButtonStyle.link))

        if message is None:
            message = await log_ch.send(embed=embed, view=view)
            print(f"Channel Status message created → {message.id}")
        else:
            await message.edit(embed=embed, view=view)

        last_status = current_status          # ← store the real value (can be empty string)
        

bot.run(os.getenv("TOKEN"))
