import discord
from discord.ext import commands, tasks
import requests
import datetime
import os
import json

# --- CONFIG ---
API_KEY = os.getenv("API_KEY")
API_URL = "https://services.rainbet.com/v1/external/affiliates"
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
USERS_FILE = "users.json"  # File to store user mappings

# Bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# Load user data from file
def load_users():
    # Check if the file exists, if not, create it
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({}, f, indent=4)  # Create an empty dictionary if file doesn't exist
    with open(USERS_FILE, "r") as f:
        return json.load(f)

# Save user data to file
def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

# Format for leaderboard entry
def format_leaderboard(data):
    sorted_data = sorted(data, key=lambda x: x.get("wagered", 0), reverse=True)
    lines = []
    for i, entry in enumerate(sorted_data[:5]):
        medal = ["🥇", "🥈", "🥉", "4.", "5."][i]
        lines.append(f"{medal} {entry['username']} – ${entry['wagered']:,} wagered")
    return "\n".join(lines)

# Find rank by Rainbet username
def get_user_rank(data, username):
    sorted_data = sorted(data, key=lambda x: x.get("wagered", 0), reverse=True)
    for i, entry in enumerate(sorted_data, start=1):
        if entry["username"].lower() == username.lower():
            return i, entry["wagered"]
    return None, 0

# Command to fetch leaderboard
@bot.command()
async def leaderboard(ctx):
    today = datetime.date.today()
    start_at = today.replace(day=1).strftime("%Y-%m-%d")
    end_at = today.strftime("%Y-%m-%d")

    params = {
        "start_at": start_at,
        "end_at": end_at,
        "key": API_KEY
    }

    try:
        response = requests.get(API_URL, params=params)
        data = response.json()

        embed = discord.Embed(
            title="🏆 Rainbet Leaderboard – April Challenge",
            description=format_leaderboard(data),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Updated: {datetime.datetime.utcnow().strftime('%d %B %H:%M UTC')}")
        embed.add_field(name="Bonus Info 💸", value="1st = 100% of my 30.04 cashout (min. $50)\n2nd = $30\n3rd = $20\n$10 for everyone over $1,000 wagered!", inline=False)

        await ctx.send(embed=embed)

    except Exception as e:
        await ctx.send(f"❌ Error fetching leaderboard: {e}")

# Command to fetch user's own rank
@bot.command()
async def myrank(ctx):
    today = datetime.date.today()
    start_at = today.replace(day=1).strftime("%Y-%m-%d")
    end_at = today.strftime("%Y-%m-%d")

    params = {
        "start_at": start_at,
        "end_at": end_at,
        "key": API_KEY
    }

    try:
        response = requests.get(API_URL, params=params)
        data = response.json()

        # Check if user has linked Rainbet account
        users = load_users()
        discord_username = str(ctx.author).split("#")[0]
        if discord_username not in users:
            await ctx.send(f"❌ {ctx.author.mention}, you haven't linked your Rainbet account yet. Use `/linkrainbet <your_rainbet_name>` to link.")
            return
        username = users[discord_username]  # Get the Rainbet username from the mapping

        rank, wagered = get_user_rank(data, username)

        if rank:
            await ctx.send(f"🎯 {ctx.author.mention}, you are currently ranked **#{rank}** with **${wagered:,}** wagered!")
        else:
            await ctx.send(f"😕 {ctx.author.mention}, you’re not on the leaderboard yet. Time to spin!")

    except Exception as e:
        await ctx.send(f"❌ Error fetching your rank: {e}")

# Command to link Rainbet account to Discord
@bot.command()
async def linkrainbet(ctx, rainbet_username: str):
    users = load_users()
    discord_username = str(ctx.author).split("#")[0]

    if discord_username in users:
        await ctx.send(f"⚠️ {ctx.author.mention}, you have already linked your Rainbet account to {users[discord_username]}. If you want to update it, use `/unlinkrainbet`.")
    else:
        users[discord_username] = rainbet_username
        save_users(users)
        await ctx.send(f"✅ {ctx.author.mention}, your Rainbet account **{rainbet_username}** has been linked successfully!")

# Command to unlink Rainbet account
@bot.command()
async def unlinkrainbet(ctx):
    users = load_users()
    discord_username = str(ctx.author).split("#")[0]

    if discord_username in users:
        del users[discord_username]
        save_users(users)
        await ctx.send(f"❌ {ctx.author.mention}, your Rainbet account has been unlinked.")
    else:
        await ctx.send(f"❌ {ctx.author.mention}, you haven't linked your Rainbet account yet.")

# Run bot
bot.run(DISCORD_TOKEN)
