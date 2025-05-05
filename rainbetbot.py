import discord
from discord.ext import commands
from discord import app_commands
import os
import psycopg2
from datetime import datetime
import requests
import random

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True  
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== Database Setup =====
DATABASE_URL = os.getenv("DATABASE_URL")  # Railway automatically sets this
API_KEY = os.getenv("API_KEY")  # Assuming you have an API key as an environment variable
# Replace with your actual allowed channel ID
ALLOWED_COMMAND_CHANNEL_ID_FOR_LINK = 1368886520412377119 # <-- deinen Channel ID hier eintragen
VERIFIED_ROLE_ID = 1368886448346107914
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
        ALLOWED_CHANNEL_ID = 1368886522912313467
        if interaction.channel_id != ALLOWED_CHANNEL_ID:
            await interaction.response.send_message(
                f"❌ This command can only be used in <#{ALLOWED_CHANNEL_ID}>.", ephemeral=True
            )
            return

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT rainbet_username FROM account_links WHERE discord_id = %s", (str(interaction.user.id),))
            result = cur.fetchone()
            if not result:
                await interaction.response.send_message("❌ You don't have a linked Rainbet account.", ephemeral=True)
                return

            rainbet_username = result[0]

            cur.execute("SELECT milestone_amount, reward_role_id, reward_text FROM milestones WHERE guild_id = %s",
                        (str(interaction.guild.id),))
            milestones = cur.fetchall()

            if not milestones:
                await interaction.response.send_message("❌ No milestones have been set by an admin.", ephemeral=True)
                return

        url = f"https://services.rainbet.com/v1/external/affiliates?start_at=2025-03-10&end_at={datetime.now().strftime('%Y-%m-%d')}&key={API_KEY}"
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
            await interaction.response.send_message("❌ Could not find your wager information.", ephemeral=True)
            return

        milestones.sort(key=lambda x: x[0])  # Sort ascending

        # Determine the highest reached and next milestone
        highest_reached = None
        next_milestone = None
        for milestone in milestones:
            if wagered >= milestone[0]:
                highest_reached = milestone
            elif not next_milestone:
                next_milestone = milestone

        # If nothing reached yet, show progress toward first milestone
        if not highest_reached:
            target_amount, target_role_id, reward_text = milestones[0]
            progress_ratio = min(wagered / target_amount, 1)
            filled = int(progress_ratio * 20)
            empty = 20 - filled
            progress_bar = f"[{'█' * filled}{'—' * empty}]"

            message = (
                f"📊 Casynetic VIP Progress for `{rainbet_username}`:\n"
                f"💰 Wagered: `{wagered:.2f}` / `{target_amount}`\n"
                f"{progress_bar} {int(progress_ratio * 100)}%\n"
                f"🎁 Upcoming Reward: {reward_text}\n"
                f"🔓 Unlocks at `{target_amount}` wagered!"
            )
            await interaction.response.send_message(message, ephemeral=True)
            return

        # If a milestone was reached
        highest_amount, highest_role_id, reward_text = highest_reached
        progress_ratio = min(wagered / highest_amount, 1)
        filled = int(progress_ratio * 20)
        empty = 20 - filled
        progress_bar = f"[{'█' * filled}{'—' * empty}]"

        message = (
            f"📊 Casynetic VIP Progress for `{rainbet_username}`:\n"
            f"💰 Wagered: `{wagered:.2f}` / `{highest_amount}`\n"
            f"{progress_bar} {int(progress_ratio * 100)}%\n"
            f"🎁 Reward: {reward_text}\n"
        )

        role = discord.utils.get(interaction.guild.roles, id=int(highest_role_id))
        if role and role not in interaction.user.roles:
            roles_to_remove = [
                discord.utils.get(interaction.guild.roles, id=int(rid))
                for amt, rid, _ in milestones if amt < highest_amount
            ]
            roles_to_remove = [r for r in roles_to_remove if r and r in interaction.user.roles]
            if roles_to_remove:
                await interaction.user.remove_roles(*roles_to_remove)

            await interaction.user.add_roles(role)
            message += (
                f"\n🎉 **Milestone reached!** You’ve been granted the role `{role.name}`.\n"
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
        url = f"https://services.rainbet.com/v1/external/affiliates?start_at=2025-03-10&end_at={datetime.now().strftime('%Y-%m-%d')}&key={API_KEY}"
        response = requests.get(url)
        if response.status_code != 200:
            await interaction.response.send_message("❌ Failed to fetch data from the Rainbet API.", ephemeral=True)
            return

        data = response.json()
        found = False
        for affiliate in data.get("affiliates", []):
            if affiliate["username"] == rainbet:
                found = True
                break

        if not found:
            await interaction.response.send_message(
                "❌ The provided Rainbet account is not under our affiliate code.", ephemeral=True
            )
            return

        role_id = 1368886447209185351  # Replace with the real role ID
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
                affiliate_role = discord.utils.get(interaction.user.roles, id=1368886447209185351)
                await interaction.user.remove_roles(affiliate_role)
                await interaction.response.send_message("✅ Your accounts have been unlinked and the **Degen Syndicate** role has been removed.", ephemeral=True)
                
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

#region tournaments
bot.tournament_state = {
    "participants": set(),
    "final_four": [],
    "hall_of_fame_message_id": None
}

# Ensure database table exists
def init_tournament_db():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tournament_winners (
                    user_id TEXT PRIMARY KEY,
                    wins INTEGER NOT NULL
                );
            """)
            conn.commit()

async def update_hall_of_fame():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id, wins FROM tournament_winners ORDER BY wins DESC LIMIT 10;")
            rows = cursor.fetchall()
    HALL_OF_FAME_CHANNEL_ID= 1368886530969702463
    channel = bot.get_channel(HALL_OF_FAME_CHANNEL_ID)
    if not channel:
        return

    description = "**🏆 Hall of Fame – Tournament Winners 🏆**\n\n"
    for i, (user_id, wins) in enumerate(rows, start=1):
        description += f"{i}. <@{user_id}> — **{wins}** wins\n"

    # Try to edit existing message, otherwise send new one
    try:
        if bot.tournament_state["hall_of_fame_message_id"]:
            msg = await channel.fetch_message(bot.tournament_state["hall_of_fame_message_id"])
            await msg.edit(content=description)
        else:
            msg = await channel.send(description)
            bot.tournament_state["hall_of_fame_message_id"] = msg.id
    except:
        msg = await channel.send(description)
        bot.tournament_state["hall_of_fame_message_id"] = msg.id



@bot.tree.command(name="tournament_start", description="Start a slot tournament (4 players).")
@app_commands.checks.has_permissions(administrator=True)
async def tournament_start(interaction: discord.Interaction):
    init_tournament_db()
    bot.tournament_state["participants"].clear()
    bot.tournament_state["final_four"] = []
    EMOJI = "🎰" 

    msg = await interaction.channel.send("🎰 **React to join the slot tournament!**\n"
    "Only 4 will be randomly selected.\n\n"
    "🏆 The winner receives a **$5 tip**!\n"
    "💰 If both bonus buys are profitable, the prize will be **doubled to $10**!")
    await msg.add_reaction(EMOJI)
    bot.tournament_state["reaction_message_id"] = msg.id

    await interaction.response.send_message("✅ Tournament registration started.", ephemeral=True)

@bot.tree.command(name="tournament_close", description="Close registration and draw 4 random players.")
@app_commands.checks.has_permissions(administrator=True)
async def tournament_close(interaction: discord.Interaction):
    participants = list(bot.tournament_state["participants"])
    if len(participants) < 4:
        await interaction.response.send_message("⚠️ Not enough participants (need at least 4).", ephemeral=True)
        return

    selected = random.sample(participants, 4)
    bot.tournament_state["final_four"] = selected

    mentions = " ".join(f"<@{uid}>" for uid in selected)
    await interaction.channel.send(
        f"🎯 **Selected participants:** {mentions}\n"
        f"Please appear in the stream within the next **5 minutes**, or you will be replaced."
    )

    await interaction.response.send_message("✅ Final four selected.", ephemeral=True)


@bot.tree.command(name="tournament_draw_backup", description="Draw a backup participant in case someone no-shows.")
@app_commands.checks.has_permissions(administrator=True)
async def tournament_draw_backup(interaction: discord.Interaction):
    remaining = list(bot.tournament_state["participants"] - set(bot.tournament_state["final_four"]))
    if not remaining:
        await interaction.response.send_message("⚠️ No remaining participants available.", ephemeral=True)
        return

    backup = random.choice(remaining)
    bot.tournament_state["final_four"].append(backup)

    await interaction.channel.send(
        f"🆕 Backup participant selected: <@{backup}>\nPlease appear in the stream within the next **5 minutes**!"
    )

    await interaction.response.send_message("✅ Backup participant selected.", ephemeral=True)

@bot.tree.command(name="tournament_winner", description="Set the winner of the tournament final.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="The winner of the final round")
async def tournament_winner(interaction: discord.Interaction, user: discord.User):
    init_tournament_db()
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO tournament_winners (user_id, wins)
                VALUES (%s, 1)
                ON CONFLICT (user_id) DO UPDATE SET wins = tournament_winners.wins + 1;
            """, (str(user.id),))
            conn.commit()

    await update_hall_of_fame()

    await interaction.response.send_message("✅ Winner recorded and Hall of Fame updated.", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload):
    EMOJI = "🎰" 
    if payload.message_id != bot.tournament_state.get("reaction_message_id"):
        return
    if str(payload.emoji) != EMOJI:
        return
    bot.tournament_state["participants"].add(payload.user_id)

#endregion

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
