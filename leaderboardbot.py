import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import datetime
import os
import json
import random
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
# Neue Formatierungsfunktion mit Tickets
def format_leaderboard(data):
    affiliates = data.get("affiliates", [])
    sorted_data = sorted(
        affiliates, key=lambda x: float(x.get("wagered_amount", "0")), reverse=True
    )

    lines = []
    for i, entry in enumerate(sorted_data[:5]):
        medal = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][i]
        wagered = float(entry.get("wagered_amount", "0"))
        tickets = int(wagered // 100)
        lines.append(f"{medal} {entry['username']} – ${wagered:,.2f} wagered ({tickets} 🎟️)")
    return "\n".join(lines)

# ADMIN-ONLY leaderboard command
@tree.command(name="leaderboard", description="Admin only – show & update the leaderboard.")
@app_commands.checks.has_permissions(administrator=True)
async def leaderboard(interaction: discord.Interaction):
    await send_leaderboard_embed(interaction.channel, interaction=interaction)


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
    prize_4th: str,
    prize_5th: str,
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
            "4th": prize_4th,
            "5th": prize_5th,
            "bonus_threshold": bonus_threshold,
            "bonus_reward": bonus_reward
        }
    }

    with open(leaderboard_path, "w") as f:
        json.dump(data, f, indent=4)

    await interaction.response.send_message(
        f"✅ Leaderboard set from **{start_date}** to **{end_date}** with updated prizes!"
    )

@tree.command(
    name="pullwinners",
    description="(Admin) Draw lottery winners for the current leaderboard."
)
@app_commands.checks.has_permissions(administrator=True)
async def pullwinners(interaction: discord.Interaction):
    leaderboard_path = "leaderboard.json"
    if not os.path.exists(leaderboard_path):
        await interaction.response.send_message("❌ The leaderboard is not set yet.")
        return

    # Lade Zeitraum und Preise
    with open(leaderboard_path, "r") as f:
        lb = json.load(f)
    start_date = lb.get("start_at")
    end_date = lb.get("end_at")
    prizes = lb.get("prizes", {})
    if not start_date or not end_date:
        await interaction.response.send_message("❌ Invalid leaderboard period.")
        return

    # API-Daten holen
    params = {"start_at": start_date, "end_at": end_date, "key": API_KEY}
    try:
        data = await fetch_api_data(params)
        if isinstance(data, str) or not data.get("affiliates"):
            raise ValueError("Unexpected or empty API response")

        # Tickets pro User berechnen
        ticket_map = {}
        for entry in data["affiliates"]:
            user = entry.get("username")
            wagered = float(entry.get("wagered_amount", "0"))
            tickets = int(wagered // 100)
            if tickets > 0:
                ticket_map[user] = tickets

        if not ticket_map:
            await interaction.response.send_message("❌ No tickets have been earned. Cannot draw winners.")
            return

        # Gewinner ziehen (ohne Zurücklegen)
        candidates = list(ticket_map.keys())
        winners = []
        for _ in range(min(5, len(candidates))):
            weights = [ticket_map[u] for u in candidates]
            chosen = random.choices(candidates, weights=weights, k=1)[0]
            winners.append(chosen)
            candidates.remove(chosen)

        # Nutzer-Mapping, um ggf. Discord-Mentions auszugeben
        users = load_users()  # {discord_id: rainbet_username}
        inv_map = {v.lower(): k for k, v in users.items()}

        # Embed bauen
        embed = discord.Embed(
            title="🎉 Leaderboard Lottery Winners",
            description=f"📅 {start_date} to {end_date}",
            color=discord.Color.green()
        )
        places = ["1st", "2nd", "3rd", "4th", "5th"]
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

        for i, winner in enumerate(winners):
            medal = medals[i]
            prize = prizes.get(places[i], "TBA")
            tickets = ticket_map[winner]
            # wenn verknüpft, mention, sonst nur Username
            disc_id = inv_map.get(winner.lower())
            mention = f"<@{disc_id}>" if disc_id else winner
            embed.add_field(
                name=f"{medal} {mention}",
                value=f"🎟️ Tickets: {tickets}  •  🏆 Prize: {prize}",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error drawing winners: {e}")

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
    prize4 = prizes.get("4th", "TBA")
    prize5 = prizes.get("5th", "TBA")
    bonus_threshold = prizes.get("bonus_threshold")
    bonus_reward = prizes.get("bonus_reward")

    bonus_line = ""
    if bonus_threshold and bonus_reward:
        bonus_line = f"🎁 Bonus – {bonus_reward}$ for {bonus_threshold}$+ wagered"

    embed = discord.Embed(
        title="🎰 Rainbet Leaderboard Challenge",
        description="Track your wagers. Climb the leaderboard. Win real cash!\nNow with a **lottery system**!",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="📝 How to join",
        value="Register at [rainbet.com](https://rainbet.com/?r=casynetic) or use **code `casynetic`**.\nThen use `/linkrainbet` to link your username.",
        inline=False
    )
    embed.add_field(
        name="🎟️ Ticket System",
        value="For every **$100 wagered**, you earn **1 ticket**.\nWinners will be **randomly drawn** at the end – more tickets = higher chances.",
        inline=False
    )
    embed.add_field(
        name="🏆 Prizes",
        value=f"🥇 {prize1}\n🥈 {prize2}\n🥉 {prize3}\n4️⃣ {prize4}\n5️⃣ {prize5}\n{bonus_line}",
        inline=False
    )

    if leaderboard_data.get("start_at") and leaderboard_data.get("end_at"):
        embed.add_field(
            name="🗓️ Date Range",
            value=f"{leaderboard_data['start_at']} to {leaderboard_data['end_at']}",
            inline=False
        )

    embed.set_footer(text="Use /leaderboard (admin) to check current standings")

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

from discord.ext import tasks

async def send_leaderboard_embed(destination, interaction=None):
    leaderboard_path = "leaderboard.json"
    
    if not os.path.exists(leaderboard_path):
        message = "❌ The leaderboard is not set yet. Please contact an admin."
        if interaction:
            await interaction.response.send_message(message)
        else:
            await destination.send(message)
        return

    with open(leaderboard_path, "r") as f:
        leaderboard_data = json.load(f)

    start_date = leaderboard_data.get("start_at")
    end_date = leaderboard_data.get("end_at")
    prizes = leaderboard_data.get("prizes", {})
    prize1 = prizes.get("1st", "TBA")
    prize2 = prizes.get("2nd", "TBA")
    prize3 = prizes.get("3rd", "TBA")
    prize4 = prizes.get("4th", "TBA")
    prize5 = prizes.get("5th", "TBA")
    bonus_threshold = prizes.get("bonus_threshold")
    bonus_reward = prizes.get("bonus_reward")
    bonus_line = f"🎁 Bonus – {bonus_reward}$ for {bonus_threshold}$+ wagered" if bonus_threshold and bonus_reward else ""

    params = {
        "start_at": start_date,
        "end_at": end_date,
        "key": API_KEY
    }

    try:
        data = await fetch_api_data(params)
        if isinstance(data, str) or not data.get("affiliates"):
            msg = "❌ No leaderboard data available for the specified period."
            if interaction:
                await interaction.response.send_message(msg)
            else:
                await destination.send(msg)
            return

        total_wagered = sum(float(a.get("wagered_amount", "0")) for a in data["affiliates"])

        embed = discord.Embed(
            title=f"🏆 Rainbet Leaderboard – {start_date} to {end_date}",
            description=format_leaderboard(data),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Updated: {datetime.datetime.now(datetime.UTC).strftime('%d %B %H:%M UTC')}")
        embed.add_field(
            name="💰 Total Wagered",
            value=f"${total_wagered:,.2f}",
            inline=True
        )
        embed.add_field(
            name="🏆 Prizes",
            value=f"🥇 {prize1}\n🥈 {prize2}\n🥉 {prize3}\n4️⃣ {prize4}\n5️⃣ {prize5}\n{bonus_line}",
            inline=False
        )
        embed.add_field(
            name="🗓️ Date Range",
            value=f"{start_date} to {end_date}",
            inline=False
        )

        if interaction:
            await interaction.response.send_message(embed=embed)
        else:
            await destination.send(embed=embed)

    except Exception as e:
        error_msg = f"❌ Error fetching leaderboard: {e}"
        print(error_msg)
        if interaction:
            await interaction.response.send_message(error_msg)
        else:
            await destination.send(error_msg)


@tasks.loop(hours=24)
async def daily_leaderboard_post():
    await bot.wait_until_ready()
    channel_id = os.getenv("LEADERBOARD_CHANNEL_ID")
    if not channel_id:
        print("LEADERBOARD_CHANNEL_ID not set.")
        return
    channel = bot.get_channel(int(channel_id))
    if channel:
        await send_leaderboard_embed(channel)
    else:
        print(f"Could not find channel with ID {channel_id}")



# on_ready Event: Synchronisiert die Slash Commands bei Start
@bot.event
async def on_ready():
    await tree.sync()  # Globaler Sync; alternativ guild-spezifisch zum Testen
    print(f"{bot.user} is online and slash commands are synced!")
    daily_leaderboard_post.start()

bot.run(DISCORD_TOKEN)
