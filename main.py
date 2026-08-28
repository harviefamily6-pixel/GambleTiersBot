import discord
from discord import app_commands
from discord.ext import commands
import os
import aiohttp
import asyncio
import urllib3
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_BASE = "https://gamble-tiers--sightary.replit.app/api"

GUILDS = {
    1300582189561544795: {
        "name": "Coinflip",
        "results_channel": 1300582970419183679
    },
    1487623155295064084: {
        "name": "RPS",
        "results_channel": 1487623156368801888
    },
    1487835726270824704: {
        "name": "Blackjack",
        "results_channel": 1487835727789297801
    },
    1511639644792684544: {
        "name": "Testing",
        "results_channel": 1511639644792684547
    },
}

GUILD_GAMEMODE = {
    1300582189561544795: "Coinflip",
    1487623155295064084: "Rock Paper Scissors",
    1487835726270824704: "Blackjack",
    1511639644792684544: "Testing",
}

TIER_ROLES = [
    "HT1", "LT1",
    "HT2", "LT2",
    "HT3", "LT3",
    "HT4", "LT4",
    "HT5", "LT5"
]

RETIRED_ROLES = [
    "RHT1", "RLT1",
    "RHT2", "RLT2",
    "RHT3", "RLT3",
    "RHT4", "RLT4",
    "RHT5", "RLT5"
]

ALLOWED_ROLES = [
    "Verified Tester",
    "Helper",
    "Discord Mod",
    "Regulator",
    "Tierlist Admin",
    "Manager",
    "Organizer"
]

TIER_POINTS = {
    "HT1": 60,
    "LT1": 45,
    "HT2": 30,
    "LT2": 20,
    "HT3": 10,
    "LT3": 6,
    "HT4": 4,
    "LT4": 3,
    "HT5": 2,
    "LT5": 1,
}

TIER_DISPLAY = {
    "HT1": "High Tier 1",
    "LT1": "Low Tier 1",
    "HT2": "High Tier 2",
    "LT2": "Low Tier 2",
    "HT3": "High Tier 3",
    "LT3": "Low Tier 3",
    "HT4": "High Tier 4",
    "LT4": "Low Tier 4",
    "HT5": "High Tier 5",
    "LT5": "Low Tier 5",
}


def get_member_tier(member):
    member_role_names = [role.name for role in member.roles]

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
    user_roles = [role.name for role in interaction.user.roles]

    return any(
        role in user_roles
        for role in ALLOWED_ROLES
    )


async def update_player_tier(
    username,
    gamemode,
    tier,
    retired=False
):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE}/players/{username}",
                json={
                    "gamemode": gamemode,
                    "tier": tier,
                    "retired": retired
                },
                ssl=False
            ) as res:

                print(
                    f"Updated {username} -> {tier} "
                    f"in {gamemode} | Status: {res.status}",
                    flush=True
                )

    except Exception as e:
        print(
            f"Failed to update {username}: {e}",
            flush=True
        )


async def retire_player_api(username, gamemode):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE}/players/{username}/retire",
                json={
                    "gamemode": gamemode
                },
                ssl=False
            ) as res:

                print(
                    f"Retired {username} in {gamemode} "
                    f"| Status: {res.status}",
                    flush=True
                )

    except Exception as e:
        print(
            f"Failed to retire {username}: {e}",
            flush=True
        )


async def delete_player_tier(username, gamemode):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(
                f"{API_BASE}/players/{username}/gamemode",
                json={
                    "gamemode": gamemode
                },
                ssl=False
            ) as res:

                print(
                    f"Deleted {username} from {gamemode} "
                    f"| Status: {res.status}",
                    flush=True
                )

    except Exception as e:
        print(
            f"Failed to delete {username}: {e}",
            flush=True
        )


async def post_peaktier(
    username,
    gamemode,
    action
):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE}/players/{username}/peaktier",
                json={
                    "gamemode": gamemode,
                    "action": action
                },
                ssl=False
            ) as res:

                return res.status

    except Exception as e:
        print(
            f"Failed to set peak tier for {username}: {e}",
            flush=True
        )

        return 500


intents = discord.Intents.default()

intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

tree = bot.tree


async def scan_guild(guild):

    if guild.id not in GUILDS:
        print(
            f"Unknown guild {guild.id}, skipping",
            flush=True
        )
        return

    gamemode = GUILD_GAMEMODE.get(
        guild.id,
        "Coinflip"
    )

    count = 0

    print(
        f"Scanning {guild.name} for tier roles...",
        flush=True
    )

    async for member in guild.fetch_members(limit=None):

        if member.bot:
            continue

        active_tier, retired_tier = get_member_tier(member)

        if active_tier:
            await update_player_tier(
                member.name,
                gamemode,
                active_tier,
                retired=False
            )

            count += 1

        if retired_tier:
            await update_player_tier(
                member.name,
                gamemode,
                retired_tier,
                retired=True
            )

            count += 1

    print(
        f"Scanned {guild.name}: "
        f"pushed {count} players to API",
        flush=True
    )


async def scan_all_guilds():

    print(
        "Running scheduled scan of all guilds...",
        flush=True
    )

    for guild in bot.guilds:
        await scan_guild(guild)

    print(
        "Scheduled scan complete.",
        flush=True
    )


async def hourly_scan_loop():

    await bot.wait_until_ready()

    while not bot.is_closed():

        await asyncio.sleep(3600)

        await scan_all_guilds()


@bot.event
async def on_ready():

    print(
        f"Logged in as {bot.user}",
        flush=True
    )

    print(
        f"Connected to {len(bot.guilds)} guilds",
        flush=True
    )

    for guild in bot.guilds:
        print(
            f"  - {guild.name} ({guild.id})",
            flush=True
        )

    await tree.sync()

    print(
        "Slash commands synced",
        flush=True
    )

    # Initial scan when bot starts
    for guild in bot.guilds:
        await scan_guild(guild)

    # Start hourly scan loop
    bot.loop.create_task(
        hourly_scan_loop()
    )

    print(
        "Hourly scan loop started.",
        flush=True
    )


@bot.event
async def on_guild_join(guild):

    print(
        f"Joined guild: {guild.name} ({guild.id})",
        flush=True
    )

    await scan_guild(guild)


@bot.event
async def on_member_update(before, after):

    if after.guild.id not in GUILDS:
        return

    before_active, before_retired = get_member_tier(before)

    after_active, after_retired = get_member_tier(after)

    gamemode = GUILD_GAMEMODE.get(
        after.guild.id,
        "Coinflip"
    )

    if after_active:

        await update_player_tier(
            after.name,
            gamemode,
            after_active,
            retired=False
        )

    elif after_retired:

        await update_player_tier(
            after.name,
            gamemode,
            after_retired,
            retired=True
        )

    elif before_active or before_retired:

        await delete_player_tier(
            after.name,
            gamemode
        )


# ============================================================
# /result COMMAND
#
# Usage:
# /result [tier] [testee]
#
# Tester is automatically whoever runs the command.
# ============================================================

@tree.command(
    name="result",
    description="Post a player's test results"
)
@app_commands.describe(
    tier="Tier earned (e.g. HT3, LT2)",
    testee="The player being tested"
)
async def result(
    interaction: discord.Interaction,
    tier: str,
    testee: discord.Member
):

    guild_id = interaction.guild_id

    if guild_id not in GUILDS:

        await interaction.response.send_message(
            "This command can't be used in this server.",
            ephemeral=True
        )

        return

    if not has_permission(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this command.",
            ephemeral=True
        )

        return

    tier = tier.upper().strip()

    if tier not in TIER_ROLES:

        await interaction.response.send_message(
            f"Invalid tier. Use one of: {', '.join(TIER_ROLES)}",
            ephemeral=True
        )

        return

    # Person who used /result
    tester = interaction.user

    gamemode = GUILD_GAMEMODE.get(
        guild_id,
        "Coinflip"
    )

    guild_config = GUILDS[guild_id]

    previous_active, previous_retired = get_member_tier(
        testee
    )

    if previous_active:

        previous_tier_display = TIER_DISPLAY.get(
            previous_active,
            previous_active
        )

    elif previous_retired:

        previous_tier_display = (
            f"{TIER_DISPLAY.get(previous_retired, previous_retired)} "
            "(Retired)"
        )

    else:

        previous_tier_display = "Unranked"

    # Update website/API
    await update_player_tier(
        testee.name,
        gamemode,
        tier,
        retired=False
    )

    # Remove active tier roles
    roles_to_remove = [
        role
        for role in testee.roles
        if role.name in TIER_ROLES
    ]

    for role in roles_to_remove:

        await testee.remove_roles(
            role
        )

    # Add new tier role
    new_role = discord.utils.get(
        interaction.guild.roles,
        name=tier
    )

    if new_role:

        await testee.add_roles(
            new_role
        )

    else:

        print(
            f"Role {tier} not found in guild",
            flush=True
        )

    # Build result embed
    embed = discord.Embed(
        title=f"{testee.name}'s Test Results 🏆",
        color=0xFFD700
    )

    embed.add_field(
        name="Tester:",
        value=tester.mention,
        inline=False
    )

    embed.add_field(
        name="Previous Tier:",
        value=previous_tier_display,
        inline=False
    )

    embed.add_field(
        name="Tier Earned:",
        value=TIER_DISPLAY.get(
            tier,
            tier
        ),
        inline=False
    )

    results_channel_id = guild_config[
        "results_channel"
    ]

    results_channel = interaction.guild.get_channel(
        results_channel_id
    )

    if results_channel:

        await results_channel.send(
            content=testee.mention,
            embed=embed
        )

        await interaction.response.send_message(
            "Results posted!",
            ephemeral=True
        )

    else:

        await interaction.response.send_message(
            "Results channel couldn't be found.",
            ephemeral=True
        )


# ============================================================
# /retire COMMAND
# ============================================================

@tree.command(
    name="retire",
    description="Mark a player as retired in a gamemode"
)
@app_commands.describe(
    discord_user="The player to retire"
)
async def retire(
    interaction: discord.Interaction,
    discord_user: discord.Member
):

    guild_id = interaction.guild_id

    if guild_id not in GUILDS:

        await interaction.response.send_message(
            "This command can't be used in this server.",
            ephemeral=True
        )

        return

    if not has_permission(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this command.",
            ephemeral=True
        )

        return

    gamemode = GUILD_GAMEMODE.get(
        guild_id,
        "Coinflip"
    )

    await retire_player_api(
        discord_user.name,
        gamemode
    )

    await interaction.response.send_message(
        f"{discord_user.name} has been marked as retired in {gamemode}.",
        ephemeral=True
    )


# ============================================================
# /peaktier COMMAND
# ============================================================

@tree.command(
    name="peaktier",
    description="Add or remove a player's peak tier visibility"
)
@app_commands.describe(
    action="Add or remove",
    discord_user="The player"
)
@app_commands.choices(
    action=[
        app_commands.Choice(
            name="add",
            value="add"
        ),
        app_commands.Choice(
            name="remove",
            value="remove"
        ),
    ]
)
async def peaktier(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    discord_user: discord.Member
):

    guild_id = interaction.guild_id

    if guild_id not in GUILDS:

        await interaction.response.send_message(
            "This command can't be used in this server.",
            ephemeral=True
        )

        return

    if not has_permission(interaction):

        await interaction.response.send_message(
            "You don't have permission to use this command.",
            ephemeral=True
        )

        return

    gamemode = GUILD_GAMEMODE.get(
        guild_id,
        "Coinflip"
    )

    status = await post_peaktier(
        discord_user.name,
        gamemode,
        action.value
    )

    if status == 200:

        action_text = (
            "added"
            if action.value == "add"
            else "removed"
        )

        await interaction.response.send_message(
            f"Peak tier {action_text} for {discord_user.name}.",
            ephemeral=True
        )

    else:

        await interaction.response.send_message(
            "Failed — player may not have a tier in this gamemode.",
            ephemeral=True
        )


# ============================================================
# KEEP-ALIVE HTTP SERVER
# ============================================================

class PingHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.end_headers()

        self.wfile.write(
            b"OK"
        )

    def do_HEAD(self):

        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):

        pass


Thread(
    target=lambda: HTTPServer(
        ("0.0.0.0", 8080),
        PingHandler
    ).serve_forever(),
    daemon=True
).start()

print(
    "Ping server started on port 8080",
    flush=True
)


# ============================================================
# START BOT
# ============================================================

TOKEN = os.environ.get(
    "DISCORD_TOKEN"
)

if not TOKEN:

    print(
        "ERROR: DISCORD_TOKEN environment variable not set",
        flush=True
    )

else:

    print(
        "Starting bot...",
        flush=True
    )

    bot.run(
        TOKEN
    )
