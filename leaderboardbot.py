import discord
from discord.ext import commands
from discord import app_commands
import requests
import datetime
import os
import json

# --- CONFIG ---
API_KEY = os.getenv("API_KEY")
API_URL = "https://services.rainbet.com/v1/external/affiliates"
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
USERS_FILE = "users.json"  # Datei zur Speicherung der Verknüpfungen

# Bot-Setup mit den notwendigen Intents
intents = discord.Intents.default()
intents.message_content = True  # Aktiviert den Zugriff auf Nachrichteninhalte
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree  # Für Slash Commands

# Globale Variablen für den Leaderboard-Zeitraum
current_leaderboard_start_date = None
current_leaderboard_end_date = None

# Funktionen zur Speicherung und zum Laden der Benutzerzuordnung
def load_users():
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w") as f:
            json.dump({}, f, indent=4)
    with open(USERS_FILE, "r") as f:
        return json.load(f)
    
def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=4)

# Funktion, um den Leaderboard-Zeitraum manuell zu setzen
def set_leaderboard_for_dates(start_date_str: str, end_date_str: str):
    global current_leaderboard_start_date, current_leaderboard_end_date
    try:
        current_leaderboard_start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        current_leaderboard_end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        if current_leaderboard_end_date < current_leaderboard_start_date:
            raise ValueError("The end date cannot be before the start date.")
    except ValueError as e:
        raise ValueError(f"Invalid date format. Please use YYYY-MM-DD. Error: {e}")

# Hilfsfunktion: Formatierung des Leaderboards
def format_leaderboard(data):
    sorted_data = sorted(data, key=lambda x: x.get("wagered", 0), reverse=True)
    lines = []
    for i, entry in enumerate(sorted_data[:5]):
        medal = ["🥇", "🥈", "🥉", "4.", "5."][i]
        lines.append(f"{medal} {entry['username']} – ${entry['wagered']:,} wagered")
    return "\n".join(lines)

# Hilfsfunktion: Rangermittlung anhand eines Benutzernamens
def get_user_rank(data, username: str):
    sorted_data = sorted(data, key=lambda x: x.get("wagered", 0), reverse=True)
    for i, entry in enumerate(sorted_data, start=1):
        if entry["username"].lower() == username.lower():
            return i, entry["wagered"]
    return None, 0

# Slash Command: Zeigt das aktuelle Leaderboard an
@tree.command(name="leaderboard", description="Show the current Rainbet leaderboard for the set period.")
async def leaderboard(interaction: discord.Interaction):
    if current_leaderboard_start_date is None or current_leaderboard_end_date is None:
        await interaction.response.send_message("❌ The leaderboard is not set yet. Please contact an admin.")
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
        embed.add_field(name="Bonus Info 💸", value=(
            "1st = 100% of my 30.04 cashout (min. $50)\n"
            "2nd = $30\n"
            "3rd = $20\n"
            "$10 for everyone over $1,000 wagered!"
        ), inline=False)

        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error fetching leaderboard: {e}")

# Slash Command: Zeigt den Rang des Users an
@tree.command(name="myrank", description="Show your current rank in the leaderboard.")
async def myrank(interaction: discord.Interaction):
    if current_leaderboard_start_date is None or current_leaderboard_end_date is None:
        await interaction.response.send_message("❌ The leaderboard is not set yet. Please contact an admin.")
        return

    params = {
        "start_at": current_leaderboard_start_date.strftime("%Y-%m-%d"),
        "end_at": current_leaderboard_end_date.strftime("%Y-%m-%d"),
        "key": API_KEY
    }
    try:
        response = requests.get(API_URL, params=params)
        data = response.json()
        users = load_users()
        # Verwende die Discord-ID, um den verknüpften Rainbet-Namen zu erhalten
        discord_id = str(interaction.user.id)
        if discord_id in users:
            rainbet_username = users[discord_id]
        else:
            # Fallback: verwende den Discord-Namen, falls kein Link existiert
            rainbet_username = interaction.user.name

        rank, wagered = get_user_rank(data, rainbet_username)
        if rank:
            await interaction.response.send_message(
                f"🎯 {interaction.user.mention}, your rank is **#{rank}** with **${wagered:,}** wagered!"
            )
        else:
            await interaction.response.send_message(
                f"😕 {interaction.user.mention}, you’re not on the leaderboard yet. Time to spin!"
            )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error fetching your rank: {e}")

# Slash Command (Admin): Setzt den Leaderboard-Zeitraum für einen benutzerdefinierten Zeitraum
@tree.command(name="set_leaderboard", description="(Admin) Set the leaderboard period with start and end date (YYYY-MM-DD).")
@app_commands.checks.has_permissions(administrator=True)
async def set_leaderboard(interaction: discord.Interaction, start_date: str, end_date: str):
    """
    Set the leaderboard date range.
    Parameters:
    - start_date (str): The start date in YYYY-MM-DD format.
    - end_date (str): The end date in YYYY-MM-DD format.
    """
    try:
        set_leaderboard_for_dates(start_date, end_date)
        await interaction.response.send_message(
            f"🎯 Leaderboard period set to: {current_leaderboard_start_date.strftime('%B %d, %Y')} - "
            f"{current_leaderboard_end_date.strftime('%B %d, %Y')}"
        )
    except ValueError as e:
        await interaction.response.send_message(f"❌ Error: {e}")

# Slash Command: Verknüpfe deinen Discord-Account mit deinem Rainbet-Benutzernamen
@tree.command(name="linkrainbet", description="Link your Discord account to your Rainbet username.")
async def linkrainbet(interaction: discord.Interaction, rainbet_username: str):
    """
    Link your Discord account with your Rainbet username.
    Parameter:
    - rainbet_username (str): Your Rainbet username.
    """
    users = load_users()
    users[str(interaction.user.id)] = rainbet_username
    save_users(users)
    await interaction.response.send_message(
        f"🔗 {interaction.user.mention}, your account is now linked to Rainbet username: **{rainbet_username}**."
    )

# on_ready Event: Synchronisiert die Slash Commands bei Start
@bot.event
async def on_ready():
    await tree.sync()
    print(f"{bot.user} is online and slash commands are synced!")

bot.run(DISCORD_TOKEN)
