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

# ────────────────────── COMMANDS & EVENTS ──────────────────────
@bot.slash_command(name="say", description="Send a message to any channel or thread")
async def say(
    ctx,
    destination: discord.Option(
        str,
        "Channel or thread to send to",
        required=True,
        autocomplete=discord.utils.basic_autocomplete([
            discord.OptionChoice("Choose a channel/thread...", "0")
        ])
    ),  # We'll handle it manually below
    message: discord.Option(str, "Message to send", required=True),
    reply_to: discord.Option(str, "Message link to reply to (optional)", required=False, default="")
):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("No permission.", ephemeral=True)

    # Find the destination (channel or thread)
    dest = None
    try:
        channel_id = int(destination.split("/")[-1])  # works for links
        dest = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
    except:
        pass

    if not dest:
        return await ctx.respond("Could not find that channel/thread.", ephemeral=True)

    if not isinstance(dest, (discord.TextChannel, discord.Thread)):
        return await ctx.respond("That’s not a text channel or thread.", ephemeral=True)

    # Optional: reply to a message
    reply_msg = None
    if reply_to:
        try:
            msg_id = int(reply_to.split("/")[-1])
            reply_msg = await dest.fetch_message(msg_id)
        except:
            pass

    await dest.send(message, reference=reply_msg)
    await ctx.respond(f"Sent to {dest.mention}!", ephemeral=True)

# ────────────────────── FINAL STATUS UPDATER (YOUR EXACT LAYOUT) ──────────────────────
async def status_updater():
    await bot.wait_until_ready()
    print("Channel Status updater STARTED — checking every 10 seconds")
    last_status = None

    while not bot.is_closed():
        await asyncio.sleep(10)

        if STATUS_VC_ID_ == 0 or STATUS_LOG_CHANNEL_ID == 0:
            continue

        vc = bot.get_channel(STATUS_VC_ID_)
        log_ch = bot.get_channel(STATUS_LOG_CHANNEL_ID)
        if not vc or not log_ch or not isinstance(vc, discord.VoiceChannel):
            continue

        current_status = (vc.status or "").strip() or "Channel Status"

        if current_status == last_status:
            continue

        embed = discord.Embed(color=0x00ffae)
        embed.title = current_status
        embed.description = "Playing all day. Feel free to coordinate with others in chat if you want to plan a group watch later in the day."
        embed.set_footer(text=f"Updated • {discord.utils.utcnow().strftime('%b %d • %I:%M %p UTC')}")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label=BUTTON_1_LABEL, url=BUTTON_1_URL, style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label=BUTTON_2_LABEL, url=BUTTON_2_URL, style=discord.ButtonStyle.link))

        await log_ch.send(embed=embed, view=view)
        last_status = current_status

bot.run(os.getenv("TOKEN"))
