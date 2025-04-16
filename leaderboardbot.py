import discord
from discord.ext import commands, tasks
import requests
import datetime
import os

# --- CONFIG ---
API_KEY = os.getenv("API_KEY")
API_URL = "https://services.rainbet.com/v1/external/affiliates"
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Bot setup
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

# Variables to store the leaderboard period and linked users
current_leaderboard_start_date = None
current_leaderboard_end_date = None
linked_users = {}  # To store the mapping between Discord users and Rainbet usernames

def set_leaderboard_for_dates(start_date_str, end_date_str):
    """Set the leaderboard period for a custom date range."""
    global current_leaderboard_start_date, current_leaderboard_end_date
    
    try:
        current_leaderboard_start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        current_leaderboard_end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()

        # Ensure that the end date is not before the start date
        if current_leaderboard_end_date < current_leaderboard_start_date:
            raise ValueError("The end date cannot be before the start date.")
    
    except ValueError as e:
        raise ValueError(f"Invalid date format. Please use 'YYYY-MM-DD'. Error: {e}")

# Format for leaderboard entry
def format_leaderboard(data):
    sorted_data = sorted(data, key=lambda x: x.get("wagered", 0), reverse=True)
    lines = []
    for i, entry in enumerate(sorted_data[:5]):
        medal = ["🥇", "🥈", "🥉", "4.", "5."][i]
        lines.append(f"{medal} {entry['username']} – ${entry['wagered']:,} wagered")
    return "\n".join(lines)

# Find rank by Discord username
def get_user_rank(data, username):
    sorted_data = sorted(data, key=lambda x: x.get("wagered", 0), reverse=True)
    for i, entry in enumerate(sorted_data, start=1):
        if entry["username"].lower() == username.lower():
            return i, entry["wagered"]
    return None, 0

# Command to fetch leaderboard
@bot.command()
async def leaderboard(ctx):
    if current_leaderboard_start_date is None or current_leaderboard_end_date is None:
        await ctx.send("❌ The leaderboard is not set yet. Please contact the admin.")
        return

    params = {
        "start_at": current_leaderboard_start_date.strftime("%Y-%m-%d"),
        "end_at": current_leaderboard_end_date.strftime("%Y-%m-%d"),
        "key": API_KEY
    }

    try:
        response = requests.get(API_URL, params=params)
        data = response.json()

        embed = discord.Embed(
            title=f"🏆 Rainbet Leaderboard – {current_leaderboard_start_date.strftime('%B %Y')}",
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
    if current_leaderboard_start_date is None or current_leaderboard_end_date is None:
        await ctx.send("❌ The leaderboard is not set yet. Please contact the admin.")
        return

    params = {
        "start_at": current_leaderboard_start_date.strftime("%Y-%m-%d"),
        "end_at": current_leaderboard_end_date.strftime("%Y-%m-%d"),
        "key": API_KEY
    }

    try:
        response = requests.get(API_URL, params=params)
        data = response.json()

        # Get Discord username to find their Rainbet rank
        username = str(ctx.author).split("#")[0]  # Match based on username only
        rank, wagered = get_user_rank(data, username)

        if rank:
            await ctx.send(f"🎯 {ctx.author.mention}, you are currently ranked **#{rank}** with **${wagered:,}** wagered!")
        else:
            await ctx.send(f"😕 {ctx.author.mention}, you’re not on the leaderboard yet. Time to spin!")

    except Exception as e:
        await ctx.send(f"❌ Error fetching your rank: {e}")

# Admin command to set leaderboard for custom date range
@bot.command()
@commands.has_permissions(administrator=True)
async def set_leaderboard(ctx, start_date: str, end_date: str):
    """Admin command to set the leaderboard for a custom date range."""
    try:
        set_leaderboard_for_dates(start_date, end_date)
        await ctx.send(f"🎯 Leaderboard period set to: {current_leaderboard_start_date.strftime('%B %d, %Y')} - {current_leaderboard_end_date.strftime('%B %d, %Y')}")
    except ValueError as e:
        await ctx.send(f"❌ Error: {e}")

# Command to link Discord username to Rainbet account
@bot.command()
async def link(ctx, rainbet_username: str):
    """Link your Discord account to your Rainbet username."""
    linked_users[ctx.author.id] = rainbet_username
    await ctx.send(f"🔗 {ctx.author.mention}, your Discord account is now linked to Rainbet username: **{rainbet_username}**.")

# Run bot
bot.run(DISCORD_TOKEN)
