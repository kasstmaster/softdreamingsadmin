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

# ←←← YOUR EXACT VARIABLE NAMES ←←←
STATUS_VC_ID_          = int(os.getenv("STATUS_VC_ID_", "0"))
STATUS_LOG_CHANNEL_ID  = int(os.getenv("STATUS_LOG_CHANNEL_ID", "0"))
BUTTON_1_LABEL         = os.getenv("BUTTON_1_LABEL", "Showtimes")
BUTTON_1_URL           = os.getenv("BUTTON_1_URL", "https://example.com")
BUTTON_2_LABEL         = os.getenv("BUTTON_2_LABEL", "Other Movies/Shows")
BUTTON_2_URL           = os.getenv("BUTTON_2_URL", "https://example.com")

# ────────────────────── COMMANDS & EVENTS ──────────────────────
@bot.slash_command(name="say")
async def say(ctx, channel: discord.Option(discord.TextChannel), message: str):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("No permission.", ephemeral=True)
    await channel.send(message)
    await ctx.respond("Sent!", ephemeral=True)

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

# ────────────────────── FINAL WORKING STATUS UPDATER (uses .status, not .topic) ──────────────────────
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

        current_status = (vc.status or "").strip() or "*No status set*"

        if current_status == last_status:
            continue

        print(f"STATUS CHANGED → '{current_status}' — posting/updating embed")

        embed = discord.Embed(title="Channel Status", description=current_status, color=0x00ffae)
        embed.set_footer(text=f"Updated • {discord.utils.utcnow().strftime('%b %d • %I:%M %p UTC')}")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label=BUTTON_1_LABEL, url=BUTTON_1_URL, style=discord.ButtonStyle.link))
        view.add_item(discord.ui.Button(label=BUTTON_2_LABEL, url=BUTTON_2_URL, style=discord.ButtonStyle.link))

        await log_ch.send(embed=embed, view=view)
        last_status = current_status

bot.run(os.getenv("TOKEN"))
