import discord
import os

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Bot(intents=intents)

# ←←← CHANGE THESE (or move to variables later)
WELCOME_CHANNEL_ID = 1207917070684004452
ROLE_TO_WATCH = 1217937235840598026
BIRTHDAY_FORM_LINK = "https://discord.com/channels/1205041211610501120/1435375785220243598"
# ←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←←

@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready!")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        embed = discord.Embed(title="Welcome!", description=f"Hey {member.mention}!", color=0x00ff88)
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

@bot.event
async def on_member_update(before, after):
    channel = bot.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        return

    # Boost
    if before.premium_since is None and after.premium_since is not None:
        embed = discord.Embed(title="Server Boost!", description=f"Thanks {after.mention}!", color=0xff73fa)
        await channel.send(embed=embed)

    # Role added
    new_roles = set(after.roles) - set(before.roles)
    for role in new_roles:
        if role.id == ROLE_TO_WATCH:
            embed = discord.Embed(
                title="New VIP!",
                description=f"{after.mention} just got **{role.name}**!\nAdd your birthday below 🎂",
                color=role.color or 0x2b2d31
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            view = discord.ui.View(timeout=None)
            view.add_item(discord.ui.Button(label="Add Your Birthday", style=discord.ButtonStyle.secondary, url=BIRTHDAY_FORM_LINK, emoji="cake"))
            await channel.send(embed=embed, view=view)

bot.run(os.getenv("TOKEN"))
