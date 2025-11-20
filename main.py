import discord
import os
import asyncio
import json
from datetime import datetime

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = discord.Bot(intents=intents)

BIRTHDAY_FILE = "birthdays.json"

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
BUTTON_3_LABEL         = os.getenv("BUTTON_3_LABEL", "More")
BUTTON_3_URL           = os.getenv("BUTTON_3_URL", "https://example.com")

# birthday role (default to the ID you gave)
BIRTHDAY_ROLE_ID = int(os.getenv("BIRTHDAY_ROLE_ID", "1217937235840598026"))

# ────────────────────── BIRTHDAY STORAGE ──────────────────────
def load_birthdays():
    try:
        with open(BIRTHDAY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_birthdays(data):
    with open(BIRTHDAY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def normalize_date(date_str: str):
    # Expect MM-DD
    try:
        dt = datetime.strptime(date_str, "%m-%d")
        return dt.strftime("%m-%d")
    except ValueError:
        return None

def set_birthday(guild_id: int, user_id: int, mm_dd: str):
    data = load_birthdays()
    gid = str(guild_id)
    if gid not in data:
        data[gid] = {}
    data[gid][str(user_id)] = mm_dd
    save_birthdays(data)

def get_guild_birthdays(guild_id: int):
    data = load_birthdays()
    return data.get(str(guild_id), {})

def build_birthday_embed(guild: discord.Guild):
    birthdays = get_guild_birthdays(guild.id)
    embed = discord.Embed(title="Server Birthdays", color=0x2e2f33)

    if not birthdays:
        embed.description = "No birthdays have been set yet."
        return embed

    items = []
    for user_id, mm_dd in birthdays.items():
        member = guild.get_member(int(user_id))
        name = member.display_name if member else f"User {user_id}"
        items.append((mm_dd, name))

    # sort by month-day string
    items.sort(key=lambda x: x[0])

    lines = [f"`{mm_dd}` — {name}" for mm_dd, name in items]
    embed.description = "\n".join(lines)
    return embed

# ────────────────────── REFRESH VIEW ──────────────────────
class BirthdayListView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=None)
        self.guild = guild

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def refresh(self, button: discord.ui.Button, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != self.guild.id:
            return await interaction.response.send_message("Wrong server.", ephemeral=True)

        embed = build_birthday_embed(self.guild)
        await interaction.response.edit_message(embed=embed, view=self)

# ────────────────────── /say COMMAND ──────────────────────
@bot.slash_command(name="say", description="Make the bot say something right here")
async def say(ctx, message: discord.Option(str, "Message to send", required=True)):
    if not ctx.author.guild_permissions.administrator:
        return await ctx.respond("You need Administrator.", ephemeral=True)
    
    await ctx.channel.send(message)
    await ctx.respond("Sent!", ephemeral=True)

# ────────────────────── BIRTHDAY COMMANDS ──────────────────────
@bot.slash_command(name="set", description="Set your birthday (MM-DD)")
async def set_birthday_self(ctx, date: discord.Option(str, "Format: MM-DD (e.g. 03-14)", required=True)):
    mm_dd = normalize_date(date)
    if not mm_dd:
        return await ctx.respond("Invalid date. Use MM-DD like `03-14`.", ephemeral=True)

    set_birthday(ctx.guild.id, ctx.author.id, mm_dd)
    await ctx.respond(f"Your birthday has been set to `{mm_dd}`.", ephemeral=True)

@bot.slash_command(name="set_for", description="Set a birthday for another member (MM-DD)")
async def set_birthday_for(
    ctx,
    member: discord.Option(discord.Member, "Member to set birthday for", required=True),
    date: discord.Option(str, "Format: MM-DD (e.g. 03-14)", required=True)
):
    if not ctx.author.guild_permissions.administrator and ctx.guild.owner_id != ctx.author.id:
        return await ctx.respond("You need Administrator or to be the server owner.", ephemeral=True)

    mm_dd = normalize_date(date)
    if not mm_dd:
        return await ctx.respond("Invalid date. Use MM-DD like `03-14`.", ephemeral=True)

    set_birthday(ctx.guild.id, member.id, mm_dd)
    await ctx.respond(f"Set birthday for {member.mention} to `{mm_dd}`.", ephemeral=True)

@bot.slash_command(name="birthdays", description="Show all server birthdays")
async def birthdays_cmd(ctx):
    embed = build_birthday_embed(ctx.guild)
    view = BirthdayListView(ctx.guild)
    await ctx.respond(embed=embed, view=view)

# ────────────────────── EVENTS ──────────────────────
@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")
    bot.loop.create_task(status_updater())
    bot.loop.create_task(birthday_checker())

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

    vc = bot.get_channel(STATUS_VC_ID_)
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

        if STATUS_VC_ID_ == 0 or STATUS_LOG_CHANNEL_ID == 0:
            continue

        vc = bot.get_channel(STATUS_VC_ID_)
        log_ch = bot.get_channel(STATUS_LOG_CHANNEL_ID)
        if not vc or not log_ch or not isinstance(vc, discord.VoiceChannel):
            continue

        raw_status = str(vc.status or "").strip()

        if not raw_status:
            if last_status is not None:
                print("Status cleared → staying silent")
                last_status = None
            continue

        if raw_status == last_status:
            continue

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

# ────────────────────── BIRTHDAY CHECKER ──────────────────────
async def birthday_checker():
    await bot.wait_until_ready()
    print("Birthday checker started")

    while not bot.is_closed():
        today = datetime.utcnow().date()
        today_mm_dd = today.strftime("%m-%d")

        for guild in bot.guilds:
            role = guild.get_role(BIRTHDAY_ROLE_ID)
            if not role:
                continue

            birthdays = get_guild_birthdays(guild.id)

            # add/remove role based on today
            for member in guild.members:
                user_id_str = str(member.id)
                user_bday = birthdays.get(user_id_str)

                if user_bday == today_mm_dd:
                    if role not in member.roles:
                        try:
                            await member.add_roles(role, reason="Birthday")
                        except discord.Forbidden:
                            pass
                else:
                    if role in member.roles and user_bday != today_mm_dd:
                        try:
                            await member.remove_roles(role, reason="Not their birthday")
                        except discord.Forbidden:
                            pass

        await asyncio.sleep(3600)  # check once per hour

# ────────────────────── START BOT ──────────────────────
bot.run(os.getenv("TOKEN"))
