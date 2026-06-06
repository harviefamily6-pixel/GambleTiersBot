import discord
from discord import app_commands
from discord.ext import commands
import os
import requests
import urllib3
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE = "https://gamble-tiers--sightary.replit.app/api"

GUILDS = {
    1300582189561544795: {"name": "Coinflip",  "results_channel": 1300582189561544795},
    1487623155295064084: {"name": "RPS",       "results_channel": 1487623156368801888},
    1487835726270824704: {"name": "Blackjack", "results_channel": 1487835727789297801},
    1511639644792684544: {"name": "Testing",   "results_channel": 1511639644792684547},
}

GUILD_GAMEMODE = {
    1300582189561544795: "Coinflip",
    1487623155295064084: "Rock Paper Scissors",
    1487835726270824704: "Blackjack",
    1511639644792684544: "Testing",
}

TIER_ROLES = ["HT1","LT1","HT2","LT2","HT3","LT3","HT4","LT4","HT5","LT5"]
RETIRED_ROLES = ["RHT1","RLT1","RHT2","RLT2","RHT3","RLT3","RHT4","RLT4","RHT5","RLT5"]
ALLOWED_ROLES = ["Verified Tester", "Helper", "Discord Mod", "Regulator", "Tierlist Admin", "Manager", "Organizer"]

TIER_POINTS = {
    "HT1": 60, "LT1": 45,
    "HT2": 30, "LT2": 20,
    "HT3": 10, "LT3": 6,
    "HT4": 4,  "LT4": 3,
    "HT5": 2,  "LT5": 1,
}

TIER_DISPLAY = {
    "HT1": "High Tier 1", "LT1": "Low Tier 1",
    "HT2": "High Tier 2", "LT2": "Low Tier 2",
    "HT3": "High Tier 3", "LT3": "Low Tier 3",
    "HT4": "High Tier 4", "LT4": "Low Tier 4",
    "HT5": "High Tier 5", "LT5": "Low Tier 5",
}

def get_member_tier(member):
    member_role_names = [r.name for r in member.roles]
    active_tier = None
    retired_tier = None
    for tier in TIER_ROLES:
        if tier in member_role_names:
            active_tier = tier
            break
    for tier in RETIRED_ROLES:
        if tier in member_role_names:
            retired_tier = tier.replace("R", "", 1)
            break
    return active_tier, retired_tier

def has_permission(interaction):
    user_roles = [r.name for r in interaction.user.roles]
    return any(role in user_roles for role in ALLOWED_ROLES)

def update_player_tier(username, gamemode, tier, retired=False):
    try:
        res = requests.post(
            f"{API_BASE}/players/{username}",
            json={"gamemode": gamemode, "tier": tier, "retired": retired},
            timeout=5,
            verify=False
        )
        print(f"Updated {username} -> {tier} in {gamemode} | Status: {res.status_code}")
    except Exception as e:
        print(f"Failed to update {username}: {e}")

def retire_player_api(username, gamemode):
    try:
        requests.post(
            f"{API_BASE}/players/{username}/retire",
            json={"gamemode": gamemode},
            timeout=5,
            verify=False
        )
    except Exception as e:
        print(f"Failed to retire {username}: {e}")

def delete_player_tier(username, gamemode):
    try:
        requests.delete(
            f"{API_BASE}/players/{username}/gamemode",
            json={"gamemode": gamemode},
            timeout=5,
            verify=False
        )
        print(f"Deleted {username} from {gamemode}")
    except Exception as e:
        print(f"Failed to delete {username}: {e}")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await tree.sync()
    print("Slash commands synced")
    for guild in bot.guilds:
        await scan_guild(guild)

async def scan_guild(guild):
    if guild.id not in GUILDS:
        print(f"Unknown guild {guild.id}, skipping")
        return
    gamemode = GUILD_GAMEMODE.get(guild.id, "Coinflip")
    count = 0
    print(f"Scanning {guild.name} for tier roles...")
    async for member in guild.fetch_members(limit=None):
        if member.bot:
            continue
        active_tier, retired_tier = get_member_tier(member)
        if active_tier:
            update_player_tier(member.name, gamemode, active_tier, retired=False)
            count += 1
        if retired_tier:
            update_player_tier(member.name, gamemode, retired_tier, retired=True)
            count += 1
    print(f"Scanned {guild.name}: pushed {count} players to API")

@bot.event
async def on_guild_join(guild):
    print(f"Joined guild: {guild.name} ({guild.id})")
    await scan_guild(guild)

@bot.event
async def on_member_update(before, after):
    if after.guild.id not in GUILDS:
        return
    before_active, before_retired = get_member_tier(before)
    after_active, after_retired = get_member_tier(after)
    gamemode = GUILD_GAMEMODE.get(after.guild.id, "Coinflip")
    if after_active:
        update_player_tier(after.name, gamemode, after_active, retired=False)
    elif after_retired:
        update_player_tier(after.name, gamemode, after_retired, retired=True)
    elif before_active or before_retired:
        delete_player_tier(after.name, gamemode)

@tree.command(name="results", description="Post a player's test results")
@app_commands.describe(
    tester="The tester who ran the test",
    tier_earned="Tier earned (e.g. HT3, LT2)",
    discord_user="The player being tested"
)
async def results(
    interaction: discord.Interaction,
    tester: discord.Member,
    tier_earned: str,
    discord_user: discord.Member
):
    guild_id = interaction.guild_id
    if guild_id not in GUILDS:
        await interaction.response.send_message("This command can't be used in this server.", ephemeral=True)
        return
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    tier_earned = tier_earned.upper().strip()
    if tier_earned not in TIER_ROLES:
        await interaction.response.send_message(
            f"Invalid tier. Use one of: {', '.join(TIER_ROLES)}",
            ephemeral=True
        )
        return
    gamemode = GUILD_GAMEMODE.get(guild_id, "Coinflip")
    guild_config = GUILDS[guild_id]
    previous_active, previous_retired = get_member_tier(discord_user)
    previous_tier_display = TIER_DISPLAY.get(previous_active, "Unranked") if previous_active else "Unranked"
    update_player_tier(discord_user.name, gamemode, tier_earned)
    roles_to_remove = [r for r in discord_user.roles if r.name in TIER_ROLES]
    for role in roles_to_remove:
        await discord_user.remove_roles(role)
    new_role = discord.utils.get(interaction.guild.roles, name=tier_earned)
    if new_role:
        await discord_user.add_roles(new_role)
    else:
        print(f"Role {tier_earned} not found in guild")
    embed = discord.Embed(
        title=f"{discord_user.name}'s Test Results 🏆",
        color=0xFFD700
    )
    embed.add_field(name="Tester:", value=tester.mention, inline=False)
    embed.add_field(name="Previous Tier:", value=previous_tier_display, inline=False)
    embed.add_field(name="Tier Earned:", value=TIER_DISPLAY.get(tier_earned, tier_earned), inline=False)
    results_channel_id = guild_config["results_channel"]
    results_channel = interaction.guild.get_channel(results_channel_id)
    if results_channel:
        await results_channel.send(content=discord_user.mention, embed=embed)
        await interaction.response.send_message("Results posted!", ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed)

@tree.command(name="retire", description="Mark a player as retired in a gamemode")
@app_commands.describe(discord_user="The player to retire")
async def retire(interaction: discord.Interaction, discord_user: discord.Member):
    guild_id = interaction.guild_id
    if guild_id not in GUILDS:
        await interaction.response.send_message("This command can't be used in this server.", ephemeral=True)
        return
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    gamemode = GUILD_GAMEMODE.get(guild_id, "Coinflip")
    retire_player_api(discord_user.name, gamemode)
    await interaction.response.send_message(
        f"{discord_user.name} has been marked as retired in {gamemode}.",
        ephemeral=True
    )

@tree.command(name="peaktier", description="Add or remove a player's peak tier visibility")
@app_commands.describe(
    action="add or remove",
    discord_user="The player"
)
@app_commands.choices(action=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
])
async def peaktier(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    discord_user: discord.Member
):
    guild_id = interaction.guild_id
    if guild_id not in GUILDS:
        await interaction.response.send_message("This command can't be used in this server.", ephemeral=True)
        return
    if not has_permission(interaction):
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    gamemode = GUILD_GAMEMODE.get(guild_id, "Coinflip")
    try:
        res = requests.post(
            f"{API_BASE}/players/{discord_user.name}/peaktier",
            json={"gamemode": gamemode, "action": action.value},
            timeout=5,
            verify=False
        )
        if res.status_code == 200:
            await interaction.response.send_message(
                f"Peak tier {'added' if action.value == 'add' else 'removed'} for {discord_user.name}.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message("Failed — player may not have a tier in this gamemode.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}", ephemeral=True)

class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, format, *args):
        pass

Thread(target=lambda: HTTPServer(("0.0.0.0", 8080), PingHandler).serve_forever(), daemon=True).start()

TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    print("ERROR: DISCORD_TOKEN environment variable not set")
else:
    bot.run(TOKEN)
