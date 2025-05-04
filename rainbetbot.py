import discord
from discord.ext import commands
from discord import app_commands
import os
import psycopg2
from datetime import datetime
import requests

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Database Setup =====
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway automatically sets this
API_KEY = os.getenv("API_KEY")  # Assuming you have an API key as an environment variable
# Replace with your actual allowed channel ID
ALLOWED_COMMAND_CHANNEL_ID_FOR_LINK = 1368529085994893372  # <-- deinen Channel ID hier eintragen
VERIFIED_ROLE_ID = 1368532802555088956
def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_links (
                    discord_id TEXT PRIMARY KEY,
                    rainbet_username TEXT NOT NULL,
                    kick_username TEXT NOT NULL
                );
            """)
            conn.commit()

def link_accounts(discord_id: str, rainbet_username: str, kick_username: str):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO account_links (discord_id, rainbet_username, kick_username)
                VALUES (%s, %s, %s)
                ON CONFLICT (discord_id) DO UPDATE SET
                    rainbet_username = EXCLUDED.rainbet_username,
                    kick_username = EXCLUDED.kick_username;
            """, (discord_id, rainbet_username, kick_username))
            conn.commit()

def get_linked_accounts(discord_id: str):
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT rainbet_username, kick_username FROM account_links WHERE discord_id = %s;", (discord_id,))
            return cursor.fetchone()
    


# ===== Events =====
@bot.event
async def on_ready():
    init_db()
    await bot.tree.sync()
    print(f"✅ Bot is online as {bot.user}")

# ===== Commands =====
@bot.tree.command(name="set_milestone", description="Admin only – set wager milestone, reward role and prize description.")
@app_commands.describe(amount="Wager amount to reach milestone", role="Reward role to assign", prize="Description of the reward")
@app_commands.checks.has_permissions(administrator=True)
async def set_milestone(interaction: discord.Interaction, amount: float, role: discord.Role, prize: str):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            # Ensure table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS milestones (
                    guild_id TEXT PRIMARY KEY,
                    milestone_amount REAL,
                    reward_role_id TEXT,
                    reward_text TEXT
                );
            """)
            # Insert or update milestone data
            cur.execute("""
                INSERT INTO milestones (guild_id, milestone_amount, reward_role_id, reward_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (guild_id) DO UPDATE
                SET milestone_amount = EXCLUDED.milestone_amount,
                    reward_role_id = EXCLUDED.reward_role_id,
                    reward_text = EXCLUDED.reward_text;
            """, (str(interaction.guild.id), amount, str(role.id), prize))
            conn.commit()

        await interaction.response.send_message(
            f"✅ Milestone set to `{amount}` wager.\n🎖️ Role: `{role.name}`\n🎁 Reward: `{prize}`",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error setting milestone: {str(e)}", ephemeral=True)

@bot.tree.command(name="progress", description="Check your current wager progress.")
async def progress(interaction: discord.Interaction):
    try:
        # Channel restriction
        ALLOWED_CHANNEL_ID = 1368529610072916078  # Replace with your actual channel ID
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            channel_mention = f"<#{ALLOWED_CHANNEL_ID}>"
            await interaction.response.send_message(
                f"❌ This command can only be used in {channel_mention}.", ephemeral=True
            )
            return


        # Get linked Rainbet username from DB
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT rainbet FROM accounts WHERE discord_id = %s", (str(interaction.user.id),))
            result = cur.fetchone()
            rainbet_username = result[0]
            # Get milestone data
            cur.execute("SELECT milestone_amount, reward_role_id, reward_text FROM milestones WHERE guild_id = %s",
                        (str(interaction.guild.id),))
            milestone_data = cur.fetchone()

            if not milestone_data:
                await interaction.response.send_message("❌ No milestone has been set by an admin.", ephemeral=True)
                return

            milestone_amount, reward_role_id, reward_text = milestone_data

        # Call Rainbet API
        url = f"https://services.rainbet.com/v1/external/affiliates?start_at=2025-04-15&end_at={datetime.now().strftime('%Y-%m-%d')}&key={API_KEY}"
        response = requests.get(url)
        if response.status_code != 200:
            await interaction.response.send_message("❌ Failed to fetch data from the Rainbet API.", ephemeral=True)
            return

        data = response.json()
        wagered = None
        for affiliate in data.get("affiliates", []):
            if affiliate["username"] == rainbet_username:
                wagered = float(affiliate["wagered_amount"])
                break

        # Calculate progress
        progress_ratio = min(wagered / milestone_amount, 1)
        filled = int(progress_ratio * 20)
        empty = 20 - filled
        progress_bar = f"[{'█' * filled}{'—' * empty}]"

        # Compose message
        message = (
            f"📊 Casynetic VIP Progress for `{rainbet_username}`:\n"
            f"💰 Wagered: `{wagered:.2f}` / `{milestone_amount}`\n"
            f"{progress_bar} {int(progress_ratio * 100)}%\n"
        )

        # Milestone reached
        if wagered >= milestone_amount:
            role = discord.utils.get(interaction.guild.roles, id=int(reward_role_id))
            if role and role not in member.roles:
                await member.add_roles(role)
                message += (
                    f"\n🎉 **Milestone reached!** You’ve been granted the role `{role.name}`.\n"
                    f"🎁 **Reward:** {reward_text}\n"
                    f"📩 Please open a ticket to claim your reward!"
                )

        await interaction.response.send_message(message, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)


@bot.tree.command(name="link", description="Link your Rainbet and Kick accounts.")
@app_commands.describe(rainbet="Your Rainbet username", kick="Your Kick username")
async def link(interaction: discord.Interaction, rainbet: str, kick: str):
    if interaction.channel.id != ALLOWED_COMMAND_CHANNEL_ID_FOR_LINK:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{ALLOWED_COMMAND_CHANNEL_ID_FOR_LINK}>.",
            ephemeral=True
        )
        return
    
    verified_role = discord.utils.get(interaction.user.roles, id=VERIFIED_ROLE_ID)
    if not verified_role:
        await interaction.response.send_message(
            "❌ You must have the **Verified** role to use this command.",
            ephemeral=True
        )
        return

    try:
        url = f"https://services.rainbet.com/v1/external/affiliates?start_at=2025-04-15&end_at={datetime.now().strftime('%Y-%m-%d')}&key={API_KEY}"
        response = requests.get(url)
        if response.status_code != 200:
            await interaction.response.send_message("❌ Failed to fetch data from the Rainbet API.", ephemeral=True)
            return

        data = response.json()
        found = False
        for affiliate in data.get("affiliates", []):
            if affiliate["username"].lower() == rainbet.lower():
                found = True
                break

        if not found:
            await interaction.response.send_message(
                "❌ The provided Rainbet account is not under our affiliate code.", ephemeral=True
            )
            return

        role_id = 1368532715246452806  # Replace with the real role ID
        role = discord.utils.get(interaction.guild.roles, id=role_id)
        if role:
            await interaction.user.add_roles(role)

        link_accounts(str(interaction.user.id), rainbet, kick)

        await interaction.response.send_message(
            f"✅ Successfully linked your accounts!\nRainbet: `{rainbet}`\nKick: `{kick}`\nRole `{role.name}` assigned.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)



@bot.tree.command(name="unlink", description="Unlink your Rainbet and Kick accounts.")
async def unlink(interaction: discord.Interaction):
    if interaction.channel.id != ALLOWED_COMMAND_CHANNEL_ID_FOR_LINK:
        await interaction.response.send_message(
            f"❌ This command can only be used in <#{ALLOWED_COMMAND_CHANNEL_ID_FOR_LINK}>.",
            ephemeral=True
        )
        return
    
    verified_role = discord.utils.get(interaction.user.roles, id=VERIFIED_ROLE_ID)
    if not verified_role:
        await interaction.response.send_message(
            "❌ You must have the **Verified** role to use this command.",
            ephemeral=True
        )
        return
    
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM account_links WHERE discord_id = %s;", (str(interaction.user.id),))
            if cursor.rowcount == 0:
                await interaction.response.send_message("⚠️ No linked account found to unlink.", ephemeral=True)
            else:
                conn.commit()
                await interaction.response.send_message("✅ Your accounts have been unlinked.", ephemeral=True)

@bot.tree.command(name="accinfo", description="Admin only – show linked account info for a user.")
@app_commands.describe(user="The user you want to query.")
@app_commands.checks.has_permissions(administrator=True)
async def accinfo(interaction: discord.Interaction, user: discord.User):
    data = get_linked_accounts(str(user.id))
    if not data:
        await interaction.response.send_message(f"❌ No account links found for {user.mention}.", ephemeral=True)
    else:
        rainbet, kick = data
        await interaction.response.send_message(
            f"👤 Linked accounts for {user.mention}:\nRainbet: `{rainbet}`\nKick: `{kick}`", ephemeral=True
        )

# ===== Error Handling =====
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("⛔ You do not have permission to use this command.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
        raise error

# ===== Start Bot =====
bot.run(os.getenv("DISCORD_TOKEN"))
