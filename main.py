import discord
import os

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Bot(intents=intents)

WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "1207917070684004452"))
ROLE_TO_WATCH = int(os.getenv("ROLE_TO_WATCH", "1217937235840598026"))
BIRTHDAY_FORM_LINK = os.getenv("BIRTHDAY_FORM_LINK", "https://discord.com/channels/1205041211610501120/1435375785220243598")

WELCOME_TEXT = os.getenv("WELCOME_TEXT", "<:welcome:1435084504950640690> @{mention} just joined the server!")
BOOST_TEXT = os.getenv("BOOST_TEXT", "<:boost:1435140623714877460> @{mention} just boosted the server!")
VIP_TEXT = os.getenv("VIP_TEXT", "<:pepopartycelebrate:1435089333567619163> It's @{mention}'s birthday! @everyone")
BUTTON_LABEL = os.getenv("BUTTON_LABEL", "Add Your Birthday")

@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        msg = WELCOME_TEXT.replace("{mention}", member.mention)
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label=BUTTON_LABEL, style=discord.ButtonStyle.secondary, url=BIRTHDAY_FORM_LINK))
        await channel.send(msg, view=view)

@bot.event
async def on_member_update(before, after):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return
    if before.premium_since is None and after.premium_since is not None:
        await channel.send(BOOST_TEXT.replace("{mention}", after.mention))
    new_roles = set(after.roles) - set(before.roles)
    for role in new_roles:
        if role.id == ROLE_TO_WATCH:
            await channel.send(VIP_TEXT.replace("{mention}", after.mention))

bot.run(os.getenv("TOKEN"))
