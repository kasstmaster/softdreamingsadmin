import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# CHANGE THESE THREE THINGS
1207917070684004452 = 123456789012345678   # Your welcome/announcements channel
1217937235840598026 = 987654321098765432       # The role that triggers the button message
https://discord.com/channels/1205041211610501120/1435375785220243598 = "https://example.com/add-birthday"  # Put your actual birthday form link here

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

# 1. Welcome new members
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(1207917070684004452)
    if channel:
        embed = discord.Embed(
            title="Welcome to the server! 🎉",
            description=f"Hey {member.mention}! We're thrilled to have you here!",
            color=0x00ff88
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(embed=embed)

# 2. Server boost thank-you
@bot.event
async def on_member_update(before, after):
    channel = bot.get_channel(1207917070684004452)
    if not channel:
        return

    # Boost detection
    if before.premium_since is None and after.premium_since is not None:
        embed = discord.Embed(
            title="Server Boost! 🚀",
            description=f"Big thank you to {after.mention} for boosting the server! 💜",
            color=0xff73fa
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        await channel.send(embed=embed)

    # 3. Special role + button
    roles_added = set(after.roles) - set(before.roles)
    for role in roles_added:
        if role.id == 1217937235840598026:
            embed = discord.Embed(
                title="New VIP Alert! 👑",
                description=f"{after.mention} just unlocked **{role.name}**!\nPlease add your birthday below so we can celebrate with you 🎂",
                color=role.color or 0x2b2d31
            )
            embed.set_thumbnail(url=after.display_avatar.url)

            # The exact button style you showed in the screenshot
            view = discord.ui.View(timeout=None)
            button = discord.ui.Button(
                label="Add Your Birthday",
                style=discord.ButtonStyle.secondary,
                url=https://discord.com/channels/1205041211610501120/1435375785220243598,
                emoji="🎂"
            )
            view.add_item(button)

            await channel.send(embed=embed, view=view)

bot.run("YOUR_TOKEN_WILL_BE_ADDED_LATER_ON_RAILWAY")
