import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
import os
import json
from typing import Optional

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
    # Extrahiere die Affiliates-Liste aus der API-Antwort
    affiliates = data.get("affiliates", [])
    # Sortiere nach wagered_amount als float
    try:
        sorted_data = sorted(
            affiliates, key=lambda x: float(x.get("wagered_amount", "0")), reverse=True
        )
    except Exception as e:
        raise ValueError("Unexpected data format received from API") from e

    lines = []
    for i, entry in enumerate(sorted_data[:5]):
        medal = ["🥇", "🥈", "🥉", "4.", "5."][i]
        wagered = float(entry.get("wagered_amount", "0"))
        lines.append(f"{medal} {entry['username']} – ${wagered:,.2f} wagered")
    return "\n".join(lines)

# Hilfsfunktion: Rangermittlung anhand eines Benutzernamens
def get_user_rank(data, username: str):
    affiliates = data.get("affiliates", [])
    sorted_data = sorted(
        affiliates, key=lambda x: float(x.get("wagered_amount", "0")), reverse=True
    )
    for i, entry in enumerate(sorted_data, start=1):
        if entry["username"].lower() == username.lower():
            return i, float(entry["wagered_amount"])
    return None, 0

# Asynchrone Funktion, um Daten von der API zu holen
async def fetch_api_data(params: dict):
    async with aiohttp.ClientSession() as session:
        async with session.get(API_URL, params=params) as response:
            response.raise_for_status()
            try:
                result = await response.json()
            except Exception:
                result = await response.text()
            print("DEBUG: API response:", result)  # Debug-Ausgabe; später entfernen
            return result

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
        data = await fetch_api_data(params)
        # Falls die API-Antwort nicht das erwartete Format besitzt
        if isinstance(data, str):
            raise ValueError(f"Unexpected API response: {data}")
        if not data.get("affiliates"):
            await interaction.response.send_message("❌ No leaderboard data available for the specified period.")
            return

        embed = discord.Embed(
            title=f"🏆 Rainbet Leaderboard – {current_leaderboard_start_date.strftime('%B %Y')}",
            description=format_leaderboard(data),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Updated: {datetime.datetime.now(datetime.UTC).strftime('%d %B %H:%M UTC')
}")
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
        data = await fetch_api_data(params)
        if isinstance(data, str):
            raise ValueError(f"Unexpected API response: {data}")
        users = load_users()
        # Verwende die Discord-ID, um den verknüpften Rainbet-Namen zu erhalten
        discord_id = str(interaction.user.id)
        if discord_id in users:
            rainbet_username = users[discord_id]
        else:
            # Fallback: Verwende den Discord-Namen, falls kein Link existiert
            rainbet_username = interaction.user.name

        rank, wagered = get_user_rank(data, rainbet_username)
        if rank:
            await interaction.response.send_message(
                f"🎯 {interaction.user.mention}, your rank is **#{rank}** with **${wagered:,.2f}** wagered!"
            )
        else:
            await interaction.response.send_message(
                f"😕 {interaction.user.mention}, you’re not on the leaderboard yet. Time to spin!"
            )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error fetching your rank: {e}")

# Slash Command (Admin): Setzt den Leaderboard-Zeitraum für einen benutzerdefinierten Zeitraum
@tree.command(name="setleaderboard", description="Set the leaderboard period and prizes (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def set_leaderboard(
    interaction: discord.Interaction,
    start_date: str,
    end_date: str,
    prize_1st: str,
    prize_2nd: str,
    prize_3rd: str,
    bonus_threshold: Optional[float] = None,
    bonus_reward: Optional[str] = None
):
    leaderboard_path = "leaderboard.json"

    # Create JSON if it doesn't exist
    if not os.path.exists(leaderboard_path):
        with open(leaderboard_path, "w") as f:
            json.dump({}, f)

    data = {
        "start_at": start_date,
        "end_at": end_date,
        "prizes": {
            "1st": prize_1st,
            "2nd": prize_2nd,
            "3rd": prize_3rd,
            "bonus_threshold": bonus_threshold,
            "bonus_reward": bonus_reward
        }
    }

    with open(leaderboard_path, "w") as f:
        json.dump(data, f, indent=4)

    await interaction.response.send_message(f"✅ Leaderboard set from **{start_date}** to **{end_date}** with updated prizes!")

@tree.command(name="info", description="Information about the current leaderboard")
async def info(interaction: discord.Interaction):
    leaderboard_data = {}
    if os.path.exists("leaderboard.json"):
        with open("leaderboard.json", "r") as f:
            leaderboard_data = json.load(f)

    prizes = leaderboard_data.get("prizes", {})
    prize1 = prizes.get("1st", "TBA")
    prize2 = prizes.get("2nd", "TBA")
    prize3 = prizes.get("3rd", "TBA")
    bonus_threshold = prizes.get("bonus_threshold")
    bonus_reward = prizes.get("bonus_reward")

    bonus_line = ""
    if bonus_threshold and bonus_reward:
        bonus_line = f"🎁 Bonus – {bonus_reward} for ${bonus_threshold}+ wagered"

    embed = discord.Embed(
        title="🎰 Rainbet Leaderboard Challenge",
        description="Track your wagers. Climb the leaderboard. Win real cash!",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="📝 How to join",
        value="Register with [this link](https://rainbet.com/?r=casynetic) or use **code `casynetic`**\nLink your Rainbet username using `/link`",
        inline=False
    )
    embed.add_field(
        name="🏆 Current Prizes",
        value=f"🥇 1st – {prize1}\n🥈 2nd – {prize2}\n🥉 3rd – {prize3}\n{bonus_line}",
        inline=False
    )

    if leaderboard_data.get("start_at") and leaderboard_data.get("end_at"):
        embed.add_field(
            name="🗓️ Date Range",
            value=f"{leaderboard_data['start_at']} to {leaderboard_data['end_at']}",
            inline=False
        )

    embed.set_footer(text="Use /leaderboard or /myrank to check your position!")

    await interaction.response.send_message(embed=embed)



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
    await tree.sync()  # Globaler Sync; alternativ guild-spezifisch zum Testen
    print(f"{bot.user} is online and slash commands are synced!")

bot.run(DISCORD_TOKEN)
