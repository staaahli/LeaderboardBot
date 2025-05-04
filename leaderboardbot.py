import discord
from discord.ext import commands
from discord import app_commands
import requests
import sqlite3
from datetime import datetime
import os

# Initialize the bot
intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Your API key from Rainbet (use the environment variable)
API_KEY = os.getenv("API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# SQLite database setup for milestones with roles
DB_FILE = "affiliate_bot.db"

# Function to get a database connection
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    return conn

# Function to initialize the database and tables for milestones
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Create table for milestones if it doesn't exist (now with roles)
    cursor.execute('''CREATE TABLE IF NOT EXISTS milestones (
                        milestone INTEGER PRIMARY KEY,
                        reward TEXT NOT NULL,
                        role_name TEXT NOT NULL
                    )''')
    
    conn.commit()
    conn.close()

# Function to add or update a milestone with role
def set_milestone(milestone, reward, role_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO milestones (milestone, reward, role_name) VALUES (?, ?, ?)", (milestone, reward, role_name))
    conn.commit()
    conn.close()

# Function to load all milestones
def load_milestones():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT milestone, reward, role_name FROM milestones")
    milestones = cursor.fetchall()
    conn.close()
    return {milestone: {"reward": reward, "role_name": role_name} for milestone, reward, role_name in milestones}

# Function to get the wager stats from the Rainbet API
def get_wager_stats(rainbet_username, start_at, end_at):
    url = f"https://services.rainbet.com/v1/external/affiliates"
    params = {
        'start_at': start_at,
        'end_at': end_at,
        'key': API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()

    # Filter the data to match the user's Rainbet username
    for affiliate in data['affiliates']:
        if affiliate['username'] == rainbet_username:
            return affiliate['wager']  # Return the total wager amount for this affiliate
    return None

# Registering slash commands when the bot is ready
@bot.event
async def on_ready():
    # Initialize the database on bot startup
    init_db()
    # Register the commands in the application (slash commands)
    try:
        await bot.tree.sync()
        print(f'Logged in as {bot.user}')
    except Exception as e:
        print(f"Error syncing commands: {e}")

# Command to set a milestone (with a reward and role) as an admin (slash command)
@bot.tree.command(name="set_milestone", description="Set a milestone and corresponding reward and role.")
async def set_milestone_cmd(interaction: discord.Interaction, milestone: int, reward: str, role_name: str):
    """Set a milestone (wager amount), its reward (role or prize), and the role name."""
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You do not have permission to set milestones.")
        return

    set_milestone(milestone, reward, role_name)
    await interaction.response.send_message(f"Milestone {milestone}, reward '{reward}', and role '{role_name}' have been set.")

# Command to view the current milestones (slash command)
@bot.tree.command(name="view_milestones", description="View the current milestones, rewards, and roles.")
async def view_milestones(interaction: discord.Interaction):
    """View all configured milestones, rewards, and role names."""
    milestones = load_milestones()
    
    if not milestones:
        await interaction.response.send_message("No milestones have been set yet.")
        return
    
    # Format the milestones and rewards for display
    milestone_list = "\n".join([f"Milestone {milestone}: {reward['reward']} (Role: {reward['role_name']})" for milestone, reward in milestones.items()])
    
    await interaction.response.send_message(f"Current milestones:\n{milestone_list}")

# Command to get the wager stats and show the progress bar (slash command)
@bot.tree.command(name="progress", description="Check your wager progress using your Rainbet username.")
async def progress(interaction: discord.Interaction, rainbet_username: str):
    """Get the progress of a user based on wager stats."""
    # Set fixed start date (15.04.2025) and dynamic end date (current date)
    start_at = "2025-04-15"
    end_at = datetime.now().strftime("%Y-%m-%d")  # Get current date in YYYY-MM-DD format
    
    # Fetch the wager data
    wager = get_wager_stats(rainbet_username, start_at, end_at)
    
    # If the Rainbet username was not found
    if wager is None:
        dm = await interaction.user.create_dm()
        await dm.send(f"Error: We could not find any data for the Rainbet username `{rainbet_username}`. Please ensure the username is correct.")
        return
    
    # Load milestones
    milestones = load_milestones()
    
    # Find the appropriate milestone
    closest_milestone = None
    for milestone in sorted(milestones.keys(), reverse=True):
        if wager >= milestone:
            closest_milestone = milestone
            break
    
    # If a milestone was reached, assign reward and send instructions
    if closest_milestone:
        reward = milestones[closest_milestone]['reward']
        role_name = milestones[closest_milestone]['role_name']
        
        # Example: Assigning a role as a reward
        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if role:
            await interaction.user.add_roles(role)
        
        # Send the progress, reward details, and instructions via DM
        dm = await interaction.user.create_dm()
        await dm.send(f"Your wager progress: {wager}\nMilestone: {closest_milestone} (Reward: {reward}, Role: {role_name})\n\nPlease open a ticket to claim your prize: {reward}.")
    else:
        await interaction.response.send_message(f"Your wager progress is {wager}. No milestone reached yet.")

# Run the bot with your token
bot.run(DISCORD_TOKEN)
