import asyncio
import json
import os
import re
import traceback
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import quote

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks


# ============================================================
# SERVER CONFIG
# ============================================================

GUILD_CONFIGS = {
    # ========================================================
    # BLACKJACK
    # ========================================================
    1487835726270824704: {
        "name": "Blackjack",

        # IMPORTANT:
        # This is the exact gamemode name sent to the API
        "api_gamemode": "Blackjack",

        "results_channel": 1487835727789297801,

        "ticket_panel_channel": 1487835728002945096,

        # Unranked -> HT4
        "low_test_category": 1487835728585949400,

        # LT3 -> HT1
        "high_test_category": 1487835728875491359,
    },

    # ========================================================
    # CONNECT FOUR
    # ========================================================
    1512966499953020928: {
        "name": "ConnectFour",

        # IMPORTANT:
        # Exact API name requested
        "api_gamemode": "ConnectFour",

        "results_channel": 1543080533469298708,

        "ticket_panel_channel": 1543080546614116433,

        # Unranked -> HT4
        "low_test_category": 1543080486627446865,

        # LT3 -> HT1
        "high_test_category": 1543080488141459597,
    },
}


GUILD_OBJECTS = [
    discord.Object(id=guild_id)
    for guild_id in GUILD_CONFIGS
]


API_BASE = "https://gamble-tiers--sightary.replit.app/api"

STATE_FILE = os.environ.get(
    "TICKET_STATE_FILE",
    "ticket_state.json"
)


# ============================================================
# TIERS
# ============================================================

TIER_ROLES = [
    "HT1",
    "LT1",
    "HT2",
    "LT2",
    "HT3",
    "LT3",
    "HT4",
    "LT4",
    "HT5",
    "LT5",
]


RETIRED_ROLES = [
    "RHT1",
    "RLT1",
    "RHT2",
    "RLT2",
    "RHT3",
    "RLT3",
    "RHT4",
    "RLT4",
    "RHT5",
    "RLT5",
]


ALLOWED_ROLES = [
    "Verified Tester",
    "Helper",
    "Discord Mod",
    "Regulator",
    "Tierlist Admin",
    "Manager",
    "Organizer",
]


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


# ============================================================
# TEST GROUPS
# ============================================================

# Normal testing
# Unranked -> HT4
LOW_TEST_TIERS = {
    "UNRANKED",
    "LT5",
    "HT5",
    "LT4",
    "HT4",
}


# High testing
# LT3 -> HT1
HIGH_TEST_TIERS = {
    "LT3",
    "HT3",
    "LT2",
    "HT2",
    "LT1",
    "HT1",
}


# LT2+ gets 7 days.
# Everyone else gets 5 days.
SEVEN_DAY_TIERS = {
    "LT2",
    "HT2",
    "LT1",
    "HT1",
}


TIER_CHOICES = [
    app_commands.Choice(
        name=tier,
        value=tier
    )
    for tier in TIER_ROLES
]


# ============================================================
# CONFIG HELPERS
# ============================================================

def get_guild_config(guild_id):
    return GUILD_CONFIGS.get(guild_id)


def get_api_gamemode(guild_id):

    config = get_guild_config(guild_id)

    if not config:
        return None

    return config["api_gamemode"]


# ============================================================
# STATE / COOLDOWN STORAGE
#
# Cooldowns are stored PER SERVER.
#
# This means:
#
# Blackjack cooldown != ConnectFour cooldown
#
# ============================================================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {
            "cooldowns": {}
        }

    try:

        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

        if not isinstance(data, dict):
            data = {}

        data.setdefault(
            "cooldowns",
            {}
        )

        return data

    except Exception as exc:

        print(
            f"Failed to load {STATE_FILE}: {exc}",
            flush=True
        )

        return {
            "cooldowns": {}
        }


STATE = load_state()


def save_state():

    try:

        temp_file = f"{STATE_FILE}.tmp"

        with open(
            temp_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                STATE,
                file,
                indent=2
            )

        os.replace(
            temp_file,
            STATE_FILE
        )

    except Exception as exc:

        print(
            f"Failed to save {STATE_FILE}: {exc}",
            flush=True
        )


def get_cooldown_key(
    guild_id,
    user_id
):

    return f"{guild_id}:{user_id}"


# ============================================================
# TIER HELPERS
# ============================================================

def get_member_tier(
    member: discord.Member
):

    role_names = {
        role.name
        for role in member.roles
    }

    active_tier = next(
        (
            tier
            for tier in TIER_ROLES
            if tier in role_names
        ),
        None
    )

    retired_tier = next(
        (
            retired.replace(
                "R",
                "",
                1
            )
            for retired in RETIRED_ROLES
            if retired in role_names
        ),
        None
    )

    return (
        active_tier,
        retired_tier
    )


def get_effective_tier(
    member: discord.Member
):

    active_tier, retired_tier = get_member_tier(
        member
    )

    return (
        active_tier
        or retired_tier
    )


def tier_display(tier):

    if not tier or tier == "UNRANKED":
        return "Unranked"

    return TIER_DISPLAY.get(
        tier,
        tier
    )


def has_permission(
    interaction: discord.Interaction
):

    if not isinstance(
        interaction.user,
        discord.Member
    ):
        return False

    role_names = {
        role.name
        for role in interaction.user.roles
    }

    return any(
        role in role_names
        for role in ALLOWED_ROLES
    )


def is_ticket_staff(
    member: discord.Member
):

    role_names = {
        role.name
        for role in member.roles
    }

    return any(
        role in role_names
        for role in ALLOWED_ROLES
    )


def cooldown_days_for_tier(tier):

    if tier in SEVEN_DAY_TIERS:
        return 7

    return 5


def ticket_group_for_tier(tier):

    key = tier or "UNRANKED"

    if key in LOW_TEST_TIERS:
        return "low"

    if key in HIGH_TEST_TIERS:
        return "high"

    return None


def make_ticket_channel_name(
    member: discord.Member,
    tier
):

    tier_part = (
        tier
        or "Unranked"
    )

    username = (
        member.display_name
        or member.name
    )

    username = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        username
    ).strip("-")

    if not username:
        username = str(
            member.id
        )

    return (
        f"{tier_part}-{username}"
    )[:100]


def parse_ticket_owner(
    channel: discord.TextChannel
):

    topic = channel.topic or ""

    match = re.search(
        r"ticket_owner_id=(\d+)",
        topic
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


# ============================================================
# WEBSITE API
# ============================================================

async def api_request(
    method,
    path,
    json_body=None
):

    timeout = aiohttp.ClientTimeout(
        total=12
    )

    try:

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.request(
                method,
                f"{API_BASE}{path}",
                json=json_body,
                ssl=False
            ) as response:

                text = await response.text()

                return (
                    response.status,
                    text
                )

    except Exception as exc:

        print(
            f"API request failed: "
            f"{method} {path} -> {exc}",
            flush=True
        )

        return (
            500,
            str(exc)
        )


async def update_player_tier(
    username,
    gamemode,
    tier,
    retired=False
):

    safe_username = quote(
        username,
        safe=""
    )

    status, _ = await api_request(
        "POST",
        f"/players/{safe_username}",
        {
            "gamemode": gamemode,
            "tier": tier,
            "retired": retired
        }
    )

    print(
        f"Updated {username} -> {tier} "
        f"in {gamemode} "
        f"| retired={retired} "
        f"| Status: {status}",
        flush=True
    )

    return status


async def retire_player_api(
    username,
    gamemode
):

    safe_username = quote(
        username,
        safe=""
    )

    status, _ = await api_request(
        "POST",
        f"/players/{safe_username}/retire",
        {
            "gamemode": gamemode
        }
    )

    print(
        f"Retired {username} in {gamemode} "
        f"| Status: {status}",
        flush=True
    )

    return status


async def delete_player_tier(
    username,
    gamemode
):

    safe_username = quote(
        username,
        safe=""
    )

    status, _ = await api_request(
        "DELETE",
        f"/players/{safe_username}/gamemode",
        {
            "gamemode": gamemode
        }
    )

    print(
        f"Deleted {username} from {gamemode} "
        f"| Status: {status}",
        flush=True
    )

    return status


async def post_peaktier(
    username,
    gamemode,
    action
):

    safe_username = quote(
        username,
        safe=""
    )

    status, _ = await api_request(
        "POST",
        f"/players/{safe_username}/peaktier",
        {
            "gamemode": gamemode,
            "action": action
        }
    )

    return status


# ============================================================
# COOLDOWNS
# ============================================================

def set_local_cooldown(
    guild_id,
    user_id,
    tier,
    started_at=None,
    days=None
):

    started_at = (
        started_at
        or datetime.now(
            timezone.utc
        )
    )

    days = (
        days
        or cooldown_days_for_tier(
            tier
        )
    )

    expires_at = (
        started_at
        + timedelta(
            days=days
        )
    )

    key = get_cooldown_key(
        guild_id,
        user_id
    )

    STATE.setdefault(
        "cooldowns",
        {}
    )[key] = {
        "guild_id": guild_id,
        "user_id": user_id,
        "tier": tier,
        "days": days,
        "started_at": started_at.timestamp(),
        "expires_at": expires_at.timestamp(),
    }

    save_state()

    return expires_at


def get_local_cooldown(
    guild_id,
    user_id
):

    key = get_cooldown_key(
        guild_id,
        user_id
    )

    entry = STATE.setdefault(
        "cooldowns",
        {}
    ).get(
        key
    )

    if not entry:
        return None

    try:

        expires_at = datetime.fromtimestamp(
            float(
                entry["expires_at"]
            ),
            tz=timezone.utc
        )

        if expires_at <= datetime.now(
            timezone.utc
        ):

            STATE["cooldowns"].pop(
                key,
                None
            )

            save_state()

            return None

        return {
            "tier": entry.get(
                "tier"
            ),

            "days": int(
                entry.get(
                    "days",
                    5
                )
            ),

            "expires_at":
                expires_at
        }

    except Exception:

        STATE["cooldowns"].pop(
            key,
            None
        )

        save_state()

        return None


def remove_local_cooldown(
    guild_id,
    user_id
):

    key = get_cooldown_key(
        guild_id,
        user_id
    )

    cooldowns = STATE.setdefault(
        "cooldowns",
        {}
    )

    existed = (
        key in cooldowns
    )

    cooldowns.pop(
        key,
        None
    )

    save_state()

    return existed


# ============================================================
# BOT
# ============================================================

intents = discord.Intents.default()

intents.members = True
intents.message_content = True


class TierlistBot(
    commands.Bot
):

    async def setup_hook(self):

        # Persistent ticket buttons
        self.add_view(
            LowTestTicketView()
        )

        self.add_view(
            HighTestTicketView()
        )

        # Clear old global commands
        await self.tree.sync()

        # Sync commands to each configured server
        for guild_id in GUILD_CONFIGS:

            guild_object = discord.Object(
                id=guild_id
            )

            synced = await self.tree.sync(
                guild=guild_object
            )

            config = GUILD_CONFIGS[
                guild_id
            ]

            print(
                f"Synced {len(synced)} commands "
                f"to {config['name']} "
                f"({guild_id})",
                flush=True
            )

        if not hourly_scan_loop.is_running():
            hourly_scan_loop.start()


bot = TierlistBot(
    command_prefix="!",
    intents=intents
)

tree = bot.tree


# ============================================================
# FIND EXISTING TICKET
# ============================================================

async def find_existing_ticket(
    guild: discord.Guild,
    user_id: int
):

    config = get_guild_config(
        guild.id
    )

    if not config:
        return None

    category_ids = (
        config["low_test_category"],
        config["high_test_category"]
    )

    for category_id in category_ids:

        category = guild.get_channel(
            category_id
        )

        if not isinstance(
            category,
            discord.CategoryChannel
        ):
            continue

        for channel in category.text_channels:

            if (
                parse_ticket_owner(
                    channel
                )
                == user_id
            ):

                return channel

    return None


# ============================================================
# CLOSE PLAYER TICKET
# ============================================================

async def close_player_ticket(
    guild: discord.Guild,
    user_id: int,
    reason: str
):

    ticket = await find_existing_ticket(
        guild,
        user_id
    )

    if not ticket:
        return False

    try:

        await ticket.delete(
            reason=reason
        )

        print(
            f"Automatically closed ticket "
            f"{ticket.name} "
            f"in {guild.name}",
            flush=True
        )

        return True

    except discord.Forbidden:

        print(
            f"Couldn't close {ticket.name}: "
            f"missing Manage Channels.",
            flush=True
        )

        return False

    except Exception as exc:

        print(
            f"Couldn't close ticket: {exc}",
            flush=True
        )

        return False


# ============================================================
# CREATE TEST TICKET
# ============================================================

async def create_test_ticket(
    interaction: discord.Interaction,
    expected_group: str
):

    await interaction.response.defer(
        ephemeral=True,
        thinking=True
    )

    config = get_guild_config(
        interaction.guild_id
    )

    if not config:

        await interaction.followup.send(
            "This ticket system isn't configured "
            "for this server.",
            ephemeral=True
        )

        return

    guild = interaction.guild

    if not guild:

        await interaction.followup.send(
            "I couldn't access the server.",
            ephemeral=True
        )

        return

    member = interaction.user

    if not isinstance(
        member,
        discord.Member
    ):

        try:

            member = await guild.fetch_member(
                interaction.user.id
            )

        except Exception:

            await interaction.followup.send(
                "I couldn't read your server roles.",
                ephemeral=True
            )

            return


    # ========================================================
    # CHECK THEIR CURRENT TIER
    # ========================================================

    current_tier = get_effective_tier(
        member
    )

    current_group = ticket_group_for_tier(
        current_tier
    )


    # ========================================================
    # WRONG TEST BUTTON
    # ========================================================

    if current_group != expected_group:

        if current_group == "high":

            correct_name = (
                "High Tests"
            )

        elif current_group == "low":

            correct_name = (
                "Request a Test"
            )

        else:

            correct_name = (
                "the correct ticket option"
            )

        await interaction.followup.send(
            "❌ **This ticket is not for your tier.**\n\n"
            f"Your current tier is "
            f"**{tier_display(current_tier)}**.\n\n"
            f"Use **{correct_name}** instead.",
            ephemeral=True
        )

        return


    # ========================================================
    # EXISTING TICKET
    # ========================================================

    existing_ticket = await find_existing_ticket(
        guild,
        member.id
    )

    if existing_ticket:

        await interaction.followup.send(
            "❌ You already have an open test ticket:\n"
            f"{existing_ticket.mention}",
            ephemeral=True
        )

        return


    # ========================================================
    # COOLDOWN CHECK
    # ========================================================

    cooldown = get_local_cooldown(
        guild.id,
        member.id
    )

    if cooldown:

        expires_at = cooldown[
            "expires_at"
        ]

        unix_time = int(
            expires_at.timestamp()
        )

        await interaction.followup.send(
            "⏳ **You are currently on a testing cooldown.**\n\n"
            f"You can test again "
            f"<t:{unix_time}:R>.\n\n"
            f"Cooldown ends: "
            f"<t:{unix_time}:F>",
            ephemeral=True
        )

        return


    # ========================================================
    # CHOOSE CATEGORY
    # ========================================================

    if expected_group == "low":

        category_id = config[
            "low_test_category"
        ]

    else:

        category_id = config[
            "high_test_category"
        ]

    category = guild.get_channel(
        category_id
    )

    if not isinstance(
        category,
        discord.CategoryChannel
    ):

        await interaction.followup.send(
            "❌ The ticket category "
            "could not be found.",
            ephemeral=True
        )

        return


    # ========================================================
    # PERMISSIONS
    # ========================================================

    bot_member = guild.me

    if (
        bot_member is None
        and bot.user
    ):

        bot_member = guild.get_member(
            bot.user.id
        )


    overwrites = {

        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            ),

        member:
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
    }


    if bot_member:

        overwrites[
            bot_member
        ] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_messages=True,
            manage_channels=True
        )


    # Give configured staff roles access
    for role_name in ALLOWED_ROLES:

        role = discord.utils.get(
            guild.roles,
            name=role_name
        )

        if role:

            overwrites[
                role
            ] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True
            )


    # ========================================================
    # CREATE CHANNEL
    # ========================================================

    channel_name = make_ticket_channel_name(
        member,
        current_tier
    )

    try:

        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=(
                f"{config['name']} test ticket "
                f"| ticket_owner_id={member.id} "
                f"| tier={current_tier or 'UNRANKED'}"
            ),
            reason=(
                f"{config['name']} test ticket "
                f"opened by {member} "
                f"({member.id})"
            )
        )

    except discord.Forbidden:

        await interaction.followup.send(
            "❌ I don't have permission "
            "to create tickets.\n"
            "Give the bot **Manage Channels**.",
            ephemeral=True
        )

        return

    except Exception as exc:

        print(
            f"Failed to create ticket: {exc}",
            flush=True
        )

        await interaction.followup.send(
            "❌ Something went wrong "
            "while creating your ticket.",
            ephemeral=True
        )

        return


    # ========================================================
    # TICKET MESSAGE
    # ========================================================

    ticket_embed = discord.Embed(
        title=(
            f"{config['name']} "
            f"Test Request 🎫"
        ),
        description=(
            f"**Testee:** "
            f"{member.mention}\n"

            f"**Current Tier:** "
            f"{tier_display(current_tier)}\n\n"

            "A tester can now handle "
            "this test.\n\n"

            "When the test is finished, "
            "use `/result` to record "
            "their result.\n\n"

            "The ticket will automatically "
            "close when the player is resulted.\n\n"

            "Use `/close` if you need to "
            "close it manually."
        ),
        color=0x5865F2
    )


    await ticket_channel.send(
        content=member.mention,
        embed=ticket_embed,
        allowed_mentions=discord.AllowedMentions(
            users=True,
            roles=False
        )
    )


    await interaction.followup.send(
        "✅ Your test ticket has been created:\n"
        f"{ticket_channel.mention}",
        ephemeral=True
    )


# ============================================================
# NORMAL TEST BUTTON
# ============================================================

class LowTestTicketView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )


    @discord.ui.button(
        label="📨 Open a ticket!",
        style=discord.ButtonStyle.primary,
        custom_id="tierlist_ticket:low"
    )
    async def low_test_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await create_test_ticket(
            interaction,
            "low"
        )


# ============================================================
# HIGH TEST BUTTON
# ============================================================

class HighTestTicketView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )


    @discord.ui.button(
        label="📨 Open a ticket!",
        style=discord.ButtonStyle.danger,
        custom_id="tierlist_ticket:high"
    )
    async def high_test_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await create_test_ticket(
            interaction,
            "high"
        )


# ============================================================
# TICKET PANELS
#
# TWO SEPARATE MESSAGES PER SERVER
# ============================================================

async def ensure_ticket_panel(
    guild: discord.Guild
):

    config = get_guild_config(
        guild.id
    )

    if not config:
        return


    panel_channel = guild.get_channel(
        config["ticket_panel_channel"]
    )


    if not isinstance(
        panel_channel,
        discord.TextChannel
    ):

        try:

            panel_channel = await guild.fetch_channel(
                config["ticket_panel_channel"]
            )

        except Exception as exc:

            print(
                f"{config['name']} ticket panel "
                f"channel not found: {exc}",
                flush=True
            )

            return


    normal_panel_exists = False
    high_panel_exists = False


    normal_footer = (
        f"{config['name']} Normal Test Tickets"
    )

    high_footer = (
        f"{config['name']} High Test Tickets"
    )


    # ========================================================
    # CHECK EXISTING PANELS
    # ========================================================

    try:

        async for message in panel_channel.history(
            limit=200
        ):

            if (
                not bot.user
                or message.author.id
                != bot.user.id
            ):
                continue


            for embed in message.embeds:

                footer_text = (
                    embed.footer.text
                    if embed.footer
                    else None
                )


                if footer_text == normal_footer:

                    normal_panel_exists = True


                if footer_text == high_footer:

                    high_panel_exists = True


    except discord.Forbidden:

        print(
            f"Cannot read ticket panel history "
            f"in {config['name']}.",
            flush=True
        )


    # ========================================================
    # NORMAL TEST PANEL
    # ========================================================

    if not normal_panel_exists:

        normal_embed = discord.Embed(
            title="Request a Test!",
            description=(
                "For **Unranked – HT4** players.\n\n"
                "**5 Day Cooldown** "
                "after being resulted."
            ),
            color=0x00C853
        )

        normal_embed.set_footer(
            text=normal_footer
        )

        try:

            await panel_channel.send(
                embed=normal_embed,
                view=LowTestTicketView()
            )

            print(
                f"Posted normal ticket panel "
                f"for {config['name']}.",
                flush=True
            )

        except Exception as exc:

            print(
                f"Failed to post normal panel "
                f"for {config['name']}: {exc}",
                flush=True
            )


    # ========================================================
    # HIGH TEST PANEL
    # ========================================================

    if not high_panel_exists:

        high_embed = discord.Embed(
            title="High Tests",
            description=(
                "For **LT3 – HT1** players.\n\n"
                "**LT3 / HT3:** "
                "5 Day Cooldown\n"
                "**LT2+:** "
                "7 Day Cooldown"
            ),
            color=0xD32F2F
        )

        high_embed.set_footer(
            text=high_footer
        )

        try:

            await panel_channel.send(
                embed=high_embed,
                view=HighTestTicketView()
            )

            print(
                f"Posted high ticket panel "
                f"for {config['name']}.",
                flush=True
            )

        except Exception as exc:

            print(
                f"Failed to post high panel "
                f"for {config['name']}: {exc}",
                flush=True
            )


# ============================================================
# SERVER SCAN
# ============================================================

async def scan_guild(
    guild: discord.Guild
):

    config = get_guild_config(
        guild.id
    )

    if not config:
        return


    gamemode = config[
        "api_gamemode"
    ]

    count = 0


    print(
        f"Scanning {guild.name} "
        f"for tier roles...",
        flush=True
    )


    try:

        async for member in guild.fetch_members(
            limit=None
        ):

            if member.bot:
                continue


            active_tier, retired_tier = get_member_tier(
                member
            )


            if active_tier:

                await update_player_tier(
                    member.name,
                    gamemode,
                    active_tier,
                    retired=False
                )

                count += 1


            elif retired_tier:

                await update_player_tier(
                    member.name,
                    gamemode,
                    retired_tier,
                    retired=True
                )

                count += 1


    except discord.Forbidden:

        print(
            f"Cannot fetch members in {guild.name}. "
            f"Enable Server Members Intent.",
            flush=True
        )

        return


    print(
        f"Scanned {guild.name}: "
        f"pushed {count} players "
        f"to {gamemode} API",
        flush=True
    )


async def scan_all_guilds():

    for guild in bot.guilds:

        if guild.id in GUILD_CONFIGS:

            await scan_guild(
                guild
            )


# ============================================================
# HOURLY SCAN
# ============================================================

@tasks.loop(
    hours=1
)
async def hourly_scan_loop():

    await scan_all_guilds()


@hourly_scan_loop.before_loop
async def before_hourly_scan():

    await bot.wait_until_ready()


# ============================================================
# READY
# ============================================================

_initial_ready_complete = False


@bot.event
async def on_ready():

    global _initial_ready_complete


    print(
        f"Logged in as {bot.user}",
        flush=True
    )


    print(
        f"Connected to "
        f"{len(bot.guilds)} guild(s)",
        flush=True
    )


    for guild in bot.guilds:

        print(
            f"  - {guild.name} "
            f"({guild.id})",
            flush=True
        )


    # Make sure each configured server has
    # its ticket panels.
    for guild in bot.guilds:

        if guild.id in GUILD_CONFIGS:

            await ensure_ticket_panel(
                guild
            )


    # Initial API scan only once
    if not _initial_ready_complete:

        _initial_ready_complete = True

        await scan_all_guilds()


# ============================================================
# ROLE UPDATE SYNC
# ============================================================

@bot.event
async def on_member_update(
    before: discord.Member,
    after: discord.Member
):

    config = get_guild_config(
        after.guild.id
    )

    if not config:
        return


    before_active, before_retired = get_member_tier(
        before
    )

    after_active, after_retired = get_member_tier(
        after
    )


    # Ignore updates that don't change tiers
    if (
        before_active,
        before_retired
    ) == (
        after_active,
        after_retired
    ):
        return


    gamemode = config[
        "api_gamemode"
    ]


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


    elif (
        before_active
        or before_retired
    ):

        await delete_player_tier(
            after.name,
            gamemode
        )


# ============================================================
# /result [tier] [testee]
#
# Tester = person running the command
# ============================================================

@tree.command(
    name="result",
    description="Post a player's test result"
)
@app_commands.guilds(
    *GUILD_OBJECTS
)
@app_commands.describe(
    tier="Tier earned",
    testee="The player who was tested"
)
@app_commands.choices(
    tier=TIER_CHOICES
)
async def result(
    interaction: discord.Interaction,
    tier: app_commands.Choice[str],
    testee: discord.Member
):

    config = get_guild_config(
        interaction.guild_id
    )


    if not config:

        await interaction.response.send_message(
            "This server isn't configured.",
            ephemeral=True
        )

        return


    if not has_permission(
        interaction
    ):

        await interaction.response.send_message(
            "You don't have permission "
            "to use this command.",
            ephemeral=True
        )

        return


    # Stops Discord from saying:
    # "The application did not respond"
    await interaction.response.defer(
        ephemeral=True,
        thinking=True
    )


    tier_earned = tier.value

    tester = interaction.user

    gamemode = config[
        "api_gamemode"
    ]


    # ========================================================
    # PREVIOUS TIER
    # ========================================================

    previous_active, previous_retired = get_member_tier(
        testee
    )


    if previous_active:

        previous_tier_display = tier_display(
            previous_active
        )


    elif previous_retired:

        previous_tier_display = (
            f"{tier_display(previous_retired)} "
            "(Retired)"
        )


    else:

        previous_tier_display = (
            "Unranked"
        )


    # ========================================================
    # FIND NEW ROLE
    # ========================================================

    new_role = discord.utils.get(
        interaction.guild.roles,
        name=tier_earned
    )


    if not new_role:

        await interaction.followup.send(
            f"❌ The `{tier_earned}` role "
            f"does not exist in this server.",
            ephemeral=True
        )

        return


    # ========================================================
    # REMOVE OLD TIERS
    # ========================================================

    roles_to_remove = [
        role
        for role in testee.roles
        if (
            role.name in TIER_ROLES
            or role.name in RETIRED_ROLES
        )
    ]


    try:

        if roles_to_remove:

            await testee.remove_roles(
                *roles_to_remove,
                reason=(
                    f"New {config['name']} result "
                    f"by {tester}"
                )
            )


        await testee.add_roles(
            new_role,
            reason=(
                f"{config['name']} result: "
                f"{tier_earned} "
                f"by {tester}"
            )
        )


    except discord.Forbidden:

        await interaction.followup.send(
            "❌ I couldn't update the player's role.\n\n"
            "Make sure my bot role is above "
            "all tier roles and has "
            "**Manage Roles**.",
            ephemeral=True
        )

        return


    # ========================================================
    # WEBSITE API
    #
    # Blackjack -> "Blackjack"
    # ConnectFour -> "ConnectFour"
    # ========================================================

    api_status = await update_player_tier(
        testee.name,
        gamemode,
        tier_earned,
        retired=False
    )


    # ========================================================
    # PUBLIC RESULT
    #
    # Cooldown stays private.
    # ========================================================

    embed = discord.Embed(
        title=(
            f"{testee.name}'s "
            f"Test Results 🏆"
        ),
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
        value=tier_display(
            tier_earned
        ),
        inline=False
    )


    # ========================================================
    # RESULTS CHANNEL FOR CURRENT SERVER
    # ========================================================

    results_channel = interaction.guild.get_channel(
        config["results_channel"]
    )


    if not isinstance(
        results_channel,
        discord.TextChannel
    ):

        try:

            results_channel = await interaction.guild.fetch_channel(
                config["results_channel"]
            )

        except Exception:

            results_channel = None


    if not isinstance(
        results_channel,
        discord.TextChannel
    ):

        await interaction.followup.send(
            "❌ The results channel "
            "could not be found.",
            ephemeral=True
        )

        return


    try:

        result_message = await results_channel.send(
            content=testee.mention,
            embed=embed
        )


    except discord.Forbidden:

        await interaction.followup.send(
            "❌ I can't post in the "
            "results channel.",
            ephemeral=True
        )

        return


    # ========================================================
    # START COOLDOWN
    # ========================================================

    cooldown_days = cooldown_days_for_tier(
        tier_earned
    )


    expires_at = set_local_cooldown(
        interaction.guild_id,
        testee.id,
        tier_earned,
        started_at=result_message.created_at,
        days=cooldown_days
    )


    unix_time = int(
        expires_at.timestamp()
    )


    # ========================================================
    # FIND THEIR OPEN TICKET
    # ========================================================

    ticket = await find_existing_ticket(
        interaction.guild,
        testee.id
    )


    api_note = ""


    if not (
        200 <= api_status < 300
    ):

        api_note = (
            "\n⚠️ Discord updated successfully, "
            "but the website API returned "
            f"`{api_status}`."
        )


    # Private message only tester sees
    await interaction.followup.send(
        f"✅ Results posted for "
        f"**{config['name']}**.\n\n"
        f"{testee.mention} now has a "
        f"**{cooldown_days} day cooldown**.\n"
        f"They can test again "
        f"<t:{unix_time}:R>."
        f"{api_note}",
        ephemeral=True
    )


    # ========================================================
    # AUTOMATICALLY CLOSE TESTEE'S TICKET
    # ========================================================

    if ticket:

        try:

            await ticket.delete(
                reason=(
                    f"Automatically closed after "
                    f"{testee} was resulted "
                    f"in {config['name']} "
                    f"by {tester}"
                )
            )


            print(
                f"Automatically closed "
                f"{ticket.name} after /result "
                f"in {config['name']}",
                flush=True
            )


        except discord.Forbidden:

            print(
                "Could not automatically close "
                "ticket: missing Manage Channels.",
                flush=True
            )


        except Exception as exc:

            print(
                f"Could not automatically "
                f"close ticket: {exc}",
                flush=True
            )


# ============================================================
# /removecooldown user:
#
# ADMINISTRATORS ONLY
#
# Only removes cooldown for CURRENT SERVER.
#
# ============================================================

@tree.command(
    name="removecooldown",
    description="Remove a player's testing cooldown"
)
@app_commands.guilds(
    *GUILD_OBJECTS
)
@app_commands.describe(
    user="The player whose cooldown should be removed"
)
async def removecooldown(
    interaction: discord.Interaction,
    user: discord.Member
):

    config = get_guild_config(
        interaction.guild_id
    )


    if not config:

        await interaction.response.send_message(
            "This server isn't configured.",
            ephemeral=True
        )

        return


    if not isinstance(
        interaction.user,
        discord.Member
    ):

        await interaction.response.send_message(
            "❌ You don't have permission "
            "to use this command.",
            ephemeral=True
        )

        return


    if not interaction.user.guild_permissions.administrator:

        await interaction.response.send_message(
            "❌ Only server administrators "
            "can use `/removecooldown`.",
            ephemeral=True
        )

        return


    await interaction.response.defer(
        ephemeral=True
    )


    existed = remove_local_cooldown(
        interaction.guild_id,
        user.id
    )


    if existed:

        await interaction.followup.send(
            f"✅ Removed {user.mention}'s "
            f"**{config['name']}** "
            f"testing cooldown.\n\n"
            "They can now open another "
            "test ticket.",
            ephemeral=True
        )


    else:

        await interaction.followup.send(
            f"ℹ️ {user.mention} does not "
            f"currently have a "
            f"**{config['name']}** cooldown.",
            ephemeral=True
        )


# ============================================================
# /close
# ============================================================

@tree.command(
    name="close",
    description="Close the current test ticket"
)
@app_commands.guilds(
    *GUILD_OBJECTS
)
async def close_ticket(
    interaction: discord.Interaction
):

    channel = interaction.channel


    if not isinstance(
        channel,
        discord.TextChannel
    ):

        await interaction.response.send_message(
            "This command can only be "
            "used inside a test ticket.",
            ephemeral=True
        )

        return


    owner_id = parse_ticket_owner(
        channel
    )


    if owner_id is None:

        await interaction.response.send_message(
            "This is not a test ticket.",
            ephemeral=True
        )

        return


    member = interaction.user


    is_owner = (
        member.id
        == owner_id
    )


    is_staff = (
        isinstance(
            member,
            discord.Member
        )
        and is_ticket_staff(
            member
        )
    )


    if (
        not is_owner
        and not is_staff
    ):

        await interaction.response.send_message(
            "You don't have permission "
            "to close this ticket.",
            ephemeral=True
        )

        return


    await interaction.response.send_message(
        "✅ Closing this ticket...",
        ephemeral=True
    )


    await asyncio.sleep(
        1
    )


    try:

        await channel.delete(
            reason=(
                f"Test ticket closed by "
                f"{interaction.user} "
                f"({interaction.user.id})"
            )
        )


    except discord.Forbidden:

        try:

            await interaction.followup.send(
                "I couldn't delete the ticket. "
                "I need **Manage Channels**.",
                ephemeral=True
            )

        except discord.HTTPException:

            pass


# ============================================================
# /retire
# ============================================================

@tree.command(
    name="retire",
    description="Mark a player as retired"
)
@app_commands.guilds(
    *GUILD_OBJECTS
)
@app_commands.describe(
    testee="The player to retire"
)
async def retire(
    interaction: discord.Interaction,
    testee: discord.Member
):

    config = get_guild_config(
        interaction.guild_id
    )


    if not config:

        await interaction.response.send_message(
            "This server isn't configured.",
            ephemeral=True
        )

        return


    if not has_permission(
        interaction
    ):

        await interaction.response.send_message(
            "You don't have permission "
            "to use this command.",
            ephemeral=True
        )

        return


    await interaction.response.defer(
        ephemeral=True,
        thinking=True
    )


    active_tier, retired_tier = get_member_tier(
        testee
    )


    tier = (
        active_tier
        or retired_tier
    )


    if not tier:

        await interaction.followup.send(
            f"❌ {testee.mention} doesn't "
            f"currently have a tier.",
            ephemeral=True
        )

        return


    retired_role = discord.utils.get(
        interaction.guild.roles,
        name=f"R{tier}"
    )


    if (
        active_tier
        and retired_role
    ):

        active_role = discord.utils.get(
            interaction.guild.roles,
            name=active_tier
        )


        try:

            if active_role:

                await testee.remove_roles(
                    active_role,
                    reason=(
                        f"Retired by "
                        f"{interaction.user}"
                    )
                )


            await testee.add_roles(
                retired_role,
                reason=(
                    f"Retired by "
                    f"{interaction.user}"
                )
            )


        except discord.Forbidden:

            await interaction.followup.send(
                "❌ I couldn't update "
                "the retired role.\n"
                "Make sure my bot role "
                "is above the tier roles "
                "and has **Manage Roles**.",
                ephemeral=True
            )

            return


    status = await retire_player_api(
        testee.name,
        config["api_gamemode"]
    )


    if (
        200 <= status < 300
    ):

        await interaction.followup.send(
            f"✅ {testee.mention} has been "
            f"marked as retired in "
            f"**{config['name']}**.",
            ephemeral=True
        )


    else:

        await interaction.followup.send(
            "⚠️ Discord was updated, "
            "but the website returned "
            f"`{status}`.",
            ephemeral=True
        )


# ============================================================
# /peaktier
# ============================================================

@tree.command(
    name="peaktier",
    description="Add or remove a player's peak tier visibility"
)
@app_commands.guilds(
    *GUILD_OBJECTS
)
@app_commands.describe(
    action="Add or remove peak tier visibility",
    testee="The player"
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
        )
    ]
)
async def peaktier(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    testee: discord.Member
):

    config = get_guild_config(
        interaction.guild_id
    )


    if not config:

        await interaction.response.send_message(
            "This server isn't configured.",
            ephemeral=True
        )

        return


    if not has_permission(
        interaction
    ):

        await interaction.response.send_message(
            "You don't have permission "
            "to use this command.",
            ephemeral=True
        )

        return


    await interaction.response.defer(
        ephemeral=True,
        thinking=True
    )


    status = await post_peaktier(
        testee.name,
        config["api_gamemode"],
        action.value
    )


    if (
        200 <= status < 300
    ):

        action_text = (
            "added"
            if action.value == "add"
            else "removed"
        )


        await interaction.followup.send(
            f"✅ Peak tier {action_text} "
            f"for {testee.name} "
            f"in **{config['name']}**.",
            ephemeral=True
        )


    else:

        await interaction.followup.send(
            "❌ Failed — the player may "
            "not have a tier in this gamemode.",
            ephemeral=True
        )


# ============================================================
# SLASH COMMAND ERROR HANDLER
# ============================================================

@tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    print(
        "Slash command error:",
        flush=True
    )


    traceback.print_exception(
        type(error),
        error,
        error.__traceback__
    )


    message = (
        "❌ Something went wrong "
        "while running that command."
    )


    try:

        if interaction.response.is_done():

            await interaction.followup.send(
                message,
                ephemeral=True
            )


        else:

            await interaction.response.send_message(
                message,
                ephemeral=True
            )


    except discord.HTTPException:

        pass


# ============================================================
# KEEP ALIVE SERVER
# ============================================================

class PingHandler(
    BaseHTTPRequestHandler
):

    def do_GET(self):

        self.send_response(
            200
        )

        self.end_headers()

        self.wfile.write(
            b"OK"
        )


    def do_HEAD(self):

        self.send_response(
            200
        )

        self.end_headers()


    def log_message(
        self,
        format,
        *args
    ):

        pass


def run_ping_server():

    port = int(
        os.environ.get(
            "PORT",
            "8080"
        )
    )


    server = HTTPServer(
        (
            "0.0.0.0",
            port
        ),
        PingHandler
    )


    print(
        f"Ping server started "
        f"on port {port}",
        flush=True
    )


    server.serve_forever()


Thread(
    target=run_ping_server,
    daemon=True
).start()


# ============================================================
# START BOT
# ============================================================

TOKEN = os.environ.get(
    "DISCORD_TOKEN"
)


if not TOKEN:

    print(
        "ERROR: DISCORD_TOKEN "
        "environment variable not set",
        flush=True
    )


else:

    print(
        "Starting tierlist bot...",
        flush=True
    )

    bot.run(
        TOKEN
    )
