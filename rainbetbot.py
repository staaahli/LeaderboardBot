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
@bot.tree.command(name="set_milestone", description="Admin only – add a new wager milestone.")
@app_commands.describe(amount="Wager amount to reach milestone", role="Reward role to assign", prize="Description of the reward")
@app_commands.checks.has_permissions(administrator=True)
async def set_milestone(interaction: discord.Interaction, amount: float, role: discord.Role, prize: str):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS milestones (
                    id SERIAL PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    milestone_amount REAL NOT NULL,
                    reward_role_id TEXT NOT NULL,
                    reward_text TEXT NOT NULL
                );
            """)
            cur.execute("""
                INSERT INTO milestones (guild_id, milestone_amount, reward_role_id, reward_text)
                VALUES (%s, %s, %s, %s);
            """, (str(interaction.guild.id), amount, str(role.id), prize))
            conn.commit()

        await interaction.response.send_message(
            f"✅ Milestone of `{amount}` added!\n🎖️ Role: `{role.name}`\n🎁 Reward: {prize}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)


@bot.tree.command(name="edit_milestone", description="Admin only – edit an existing milestone.")
@app_commands.describe(
    old_amount="The existing milestone amount to edit",
    new_amount="New wager amount (or leave the same)",
    new_role="New role to assign (or leave the same)",
    new_prize="New reward description (or leave the same)"
)
@app_commands.checks.has_permissions(administrator=True)
async def edit_milestone(
    interaction: discord.Interaction,
    old_amount: float,
    new_amount: float,
    new_role: discord.Role,
    new_prize: str
):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE milestones
                SET milestone_amount = %s,
                    reward_role_id = %s,
                    reward_text = %s
                WHERE guild_id = %s AND milestone_amount = %s;
            """, (
                new_amount,
                str(new_role.id),
                new_prize,
                str(interaction.guild.id),
                old_amount
            ))
            if cur.rowcount == 0:
                await interaction.response.send_message("❌ No milestone found with that amount.", ephemeral=True)
                return
            conn.commit()
        await interaction.response.send_message(
            f"✅ Milestone `{old_amount}` updated to `{new_amount}`.\n🎖️ Role: `{new_role.name}`\n🎁 Reward: {new_prize}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Error editing milestone: {str(e)}", ephemeral=True)
        
@bot.tree.command(name="list_milestones", description="Admin only – list all current milestones.")
@app_commands.checks.has_permissions(administrator=True)
async def list_milestones(interaction: discord.Interaction):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT milestone_amount, reward_role_id, reward_text
                FROM milestones
                WHERE guild_id = %s
                ORDER BY milestone_amount ASC;
            """, (str(interaction.guild.id),))
            rows = cur.fetchall()

        if not rows:
            await interaction.response.send_message("ℹ️ No milestones set for this server.", ephemeral=True)
            return

        message = "**🎯 Current Milestones:**\n"
        for amount, role_id, reward in rows:
            role = discord.utils.get(interaction.guild.roles, id=int(role_id))
            role_name = role.name if role else f"(Role ID: {role_id})"
            message += f"• `{amount}` → 🎖️ `{role_name}` | 🎁 {reward}\n"

        await interaction.response.send_message(message, ephemeral=True)

    except Exception as e:
        await interaction.response.send_message(f"❌ Error listing milestones: {str(e)}", ephemeral=True)



@bot.tree.command(name="delete_milestone", description="Admin only – delete a milestone.")
@app_commands.describe(amount="The milestone amount to delete")
@app_commands.checks.has_permissions(administrator=True)
async def delete_milestone(interaction: discord.Interaction, amount: float):
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM milestones
                WHERE guild_id = %s AND milestone_amount = %s;
            """, (str(interaction.guild.id), amount))
            if cur.rowcount == 0:
                await interaction.response.send_message("⚠️ No milestone with that amount found.", ephemeral=True)
            else:
                conn.commit()
                await interaction.response.send_message(f"🗑️ Milestone `{amount}` deleted.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error deleting milestone: {str(e)}", ephemeral=True)


@bot.tree.command(name="progress", description="Check your current wager progress.")
async def progress(interaction: discord.Interaction):
    try:
        # Channel restriction
        ALLOWED_CHANNEL_ID = 1368529610072916078
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            channel_mention = f"<#{ALLOWED_CHANNEL_ID}>"
            await interaction.response.send_message(
                f"❌ This command can only be used in {channel_mention}.", ephemeral=True
            )
            return

        # Get linked Rainbet username from DB
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT rainbet_username FROM account_links WHERE discord_id = %s", (str(interaction.user.id),))
            result = cur.fetchone()

            if not result:
                await interaction.response.send_message("❌ You have not linked a Rainbet account.", ephemeral=True)
                return

            rainbet_username = result[0]

            # Get all milestones for this guild, ordered by amount
            cur.execute("""
                SELECT milestone_amount, reward_role_id, reward_text
                FROM milestones
                WHERE guild_id = %s
                ORDER BY milestone_amount ASC;
            """, (str(interaction.guild.id),))
            milestones = cur.fetchall()

            if not milestones:
                await interaction.response.send_message("❌ No milestones have been set by an admin.", ephemeral=True)
                return

        # Call Rainbet API
        url = f"https://services.rainbet.com/v1/external/affiliates?start_at=2025-04-15&end_at={datetime.now().strftime('%Y-%m-%d')}&key={API_KEY}"
        response = requests.get(url)
        if response.status_code != 200:
            await interaction.response.send_message("❌ Failed to fetch data from the Rainbet API.", ephemeral=True)
            return

        data = response.json()
        wagered = None
        for affiliate in data.get("affiliates", []):
            if affiliate["username"].lower() == rainbet_username.lower():
                wagered = float(affiliate["wagered_amount"])
                break

        if wagered is None:
            await interaction.response.send_message("❌ No wagering data found for your account.", ephemeral=True)
            return

        # Find the next milestone
        next_milestone = None
        for milestone in milestones:
            if wagered < milestone[0]:  # milestone_amount
                next_milestone = milestone
                break

        if next_milestone:
            milestone_amount, reward_role_id, reward_text = next_milestone
            progress_ratio = min(wagered / milestone_amount, 1)
            filled = int(progress_ratio * 20)
            empty = 20 - filled
            progress_bar = f"[{'█' * filled}{'—' * empty}]"

            message = (
                f"📊 Casynetic VIP Progress for `{rainbet_username}`:\n"
                f"💰 Wagered: `{wagered:.2f}` / `{milestone_amount}`\n"
                f"{progress_bar} {int(progress_ratio * 100)}%\n"
            )

            if wagered >= milestone_amount:
                role = discord.utils.get(interaction.guild.roles, id=int(reward_role_id))
                if role:
                    await interaction.user.add_roles(role)
                    message += (
                        f"\n🎉 **Milestone reached!** You’ve been granted the role `{role.name}`.\n"
                        f"🎁 **Reward:** {reward_text}\n"
                        f"📩 Please open a ticket to claim your reward!"
                    )

        else:
            # All milestones achieved
            message = (
                f"🏆 `{rainbet_username}`, you have reached the **maximum VIP status**!\n"
                f"💰 Total Wagered: `{wagered:.2f}`\n"
                f"🎉 There are no further milestones to achieve – amazing work!\n"
                f"📩 If you haven't yet claimed your final reward, please open a ticket."
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
