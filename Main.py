import os
import sys
import json
from datetime import datetime
import discord
from discord.ext import commands
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime

# Dotenv loading
load_dotenv()
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')
Token = os.getenv('BOT_TOKEN')

# Supabase
supabase = create_client(url, key)

# Discord bot
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

if os.path.exists('registered_guilds.json'):
    with open('registered_guilds.json', 'r') as f:
        registered_guilds = json.load(f)
else:
    registered_guilds = {}
    
def register_role_with_guild():
    with open('registered_guilds.json', 'w') as file:
        json.dump(registered_guilds, file, indent=4)

def has_correct_roles(ctx, registered_guilds):
    # Get the guild ID as a string
    guild_id = str(ctx.guild.id)
    
    # Retrieve the set of role IDs associated with the guild from registered_guilds
    role_ids = set(registered_guilds.get(guild_id, {}).get("database_role_perms", []))
    
    # Get the set of role IDs that the user has
    user_roles = {role.id for role in ctx.author.roles}
    
    # Check if the user has any of the correct roles
    return not role_ids.isdisjoint(user_roles)

spine_save = []

def guild_owner_only():
    async def predicate(ctx):
        return ctx.author == ctx.guild.owner
    return commands.check(predicate)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    print(f"Logged into guilds: {bot.guilds}")

@bot.event
async def on_guild_join(guild):
    registered_guilds[str(guild.id)] = {"database_role_perms": []}
    print(f"Added guild {guild.name} ({guild.id}) to registered_guilds.")
    print(registered_guilds)

@bot.event
async def on_guild_remove(guild):
    if str(guild.id) in registered_guilds:
        del registered_guilds[str(guild.id)]
        print(f"Removed guild {guild.name} ({guild.id}) from registered_guilds.")
    print(registered_guilds)


### Bot commands

## Add: Adds the data to the "financial_data" table.
@bot.command(name="add")
async def add_data(ctx, category: str, amount: float, date: str = None):
    if has_correct_roles(ctx, registered_guilds): # Makes so the bot only responds if the user has a role that has permissions to use the bots database commands.
        try:
            if not date: # Checks if a date has been specified.
                current_time = datetime.now() # If the date hasn't been specified it makes os it's logged as having been added at the current time of the machine running the bot.
                date = current_time.strftime("%H:%M-%d.%m.%Y") # Formats the time.
            else: # Otherwise it just formats the date.
                try:
                    datetime.strptime(date, "%H:%M-%d.%m.%Y")
                except Exception as e: # If the user used the incorrect format then an error code is sent and the data is not added.
                    await ctx.send(f"Failed to add data: {str(e)}")
                    return # Ends the commands runtime.
            if amount > 0:
                response = supabase.table("financial_data").insert({ 
                    "category": category,
                    "amount": amount,
                    "date": date
                }).execute() # Adds the data to the supabase table.
                await ctx.send(f"Added data: {category} - ${amount} on {date}") # Informs the user via discord that the data has been added to the supabase table.
            else:
                await ctx.send(f"Data not added. Amount({amount}) must be greater than zero.") # If amount is less than zero then it sends this message and doesn't add the data.
        except Exception as e:
            await ctx.send(f"Failed to add data: {str(e)}") # If a unforseen failure occurs then it sends this error message via discord informing the user that the data wasn't added and hopefully why.
    else:
        await ctx.send("You do not have permission to use this command", ephemeral=True)

## Remove: Removes the specified row(s) from the "financial_data" table.
@bot.command(name="remove")
async def remove_data(ctx, reason: str = "No reason provided", *ids: str):
    if has_correct_roles(ctx, registered_guilds): # Makes so the bot only responds if the user has a role that has permissions to use the bots database commands.
        try:
            if not ids:
                await ctx.send("Please provide at least one ID to remove.") # If no ID(s) are provided then the bot will send this error message via discord.
                return # Ends the runtime of the command.

            data = supabase.table("financial_data").select("*").in_("id", ids).execute() # Fetches the row(s) to be deleted by using the specified ID(s).
            rows = data.data # Adds each row to a list.
            
            if not rows:
                await ctx.send("No matching records found for the given IDs.") # Checks if the ID(s) exist in the table and if it doesn't it sends this error message.
                return # Ends the commands runtime.

            # Prepare audit log entries
            removal_date = datetime.now().strftime("%H:%M-%d.%m.%Y") # Adds the current local date of the machine running the bot to the removal log.
            audit_logs = [] # Initializes audit_logs as a empty list.
            for row in rows:
                audit_logs.append({ # Adds a audit log to audit_logs for each row being removed.
                    "removal_date": removal_date, # Adds the removal date of the row.
                    "category": "Remove",
                    "removed_item": f"{row['id']}, {row['category']}, ${row['amount']}, {row['date']}", # Adds the row removed.
                    "reason": reason # Adds the reason for removal if specified.
                })

            # Insert audit logs
            supabase.table("audit_log").insert(audit_logs).execute()

            # Remove rows from "financial_data" table
            supabase.table("financial_data").delete().in_("id", ids).execute()

            removed_items = "\n".join( # Formats the message to be sent informing of each row that has been removed.
                f"{row['id']} - {row['category']} | ${row['amount']} | {row['date']}"
                for row in rows
            ) 

            result = (
                f"**Action:** Remove\n"
                f"**Reason:** {reason}\n"
                f"**Removed items:**\n{removed_items}\n"
                f"**Removal date:** {removal_date}"
            )

            await ctx.send(result)

        except Exception as e:
            await ctx.send(f"Failed to remove data: {str(e)}")
    else:
        await ctx.send("You do not have permission to use this command", ephemeral=True)
        

## Clear: Clears the specified table or "audit_log" as default.
@bot.command(name="clear")
async def clear(ctx, table: str = "audit_log", reason: str = "Regular clearing of log."): # Defines table as audit_log by default if it is not specified by the user.
    if has_correct_roles(ctx, registered_guilds): # Makes so the bot only responds if the user has a role that has permissions to use the bots database commands.
        await ctx.send(f"Are you sure you want to clear **{table}**? Reply **Yes** to this message if you do.") # Sends a message on discord to confirm they want to clear the specified table.

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel and message.content.lower() in ["yes", "no"] # Defines a function that checks every message sent in a channel on discord and sees if it's from the user of the command and if its a yes or a no, otherwise it continues waiting.

        try:
            msg = await bot.wait_for("message", check=check, timeout=30.0) # Makes so the bot will listen for messages for 30 seconds.

            # Respond based on user's input
            if msg.content.lower() == "yes":
                supabase.table(table).delete().gt('id', 0).execute() # Deletes all rows in the specified table.
                await ctx.send(f"Cleared {table}.") # Informs the user the specified table has been cleared.
                audit_logs = []
                audit_logs.append({"category": f"Clear {table}", 
                    "removal_date": f"{str(datetime.now().strftime("%H:%M-%d.%m.%Y"))}",
                    "removed_item": "N/A",
                    "reason": reason
                }) # Formats the log for the clearing of the table.
                supabase.table("audit_log").insert(audit_logs).execute() # Logs the table having been cleared in the table "audit_log"
            elif msg.content.lower() == "no":
                await ctx.send(f"Cancelled clearing of {table}.") # Cancels the deletion request if the user says no.
        
        except TimeoutError:
            await ctx.send("You didn't respond in time.") # Cancels the deletion request if the user does not respond within 30 seconds.
    else:
        await ctx.send("You do not have permission to use this command", ephemeral=True)

## View: Makes the bot send a message on discord containing the content of the specified table or financial_data as default.
@bot.command(name="view")
async def view_data(ctx, table: str = "financial_data"): # table is initialized as "financial_data" if it's not specified when running the command.
    try:
        if has_correct_roles(ctx, registered_guilds): # Makes so the bot only responds if the user has a role that has permissions to use the bots database commands.
            data = supabase.table(table).select("*").execute() # Fetches all the data in the specified table.
            rows = data.data # Puts each row in the specified table in a list.
            
            if not rows: # Checks if the table was empty.
                await ctx.send(f"No data found in {table}.") # Sends a message on discord informing you the table was empty.
                return # Ends the commands runtime.

            # Group the data by category
            categories = {} # Initializes categories as a empty dictionary.
            for row in rows:
                category = row['category'] # Initializes the category with the category in the row being checked.
                categories.setdefault(category, []).append(row) # Adds the new category if the category doesn't already exist and then adds the row to the category. Otherwise it adds the row to the category.

            # Prepare formatted output
            result = [f"# {table}:\n"]  # Using list for faster string concatenation
            for category, items in categories.items():
                result.append(f"**{category}:**")
                
                if table == "financial_data":
                    items_sorted = sorted(items, key=lambda x: x['amount'])  # Sorts the items in the table seperated by category according to which item in said category has the largest number, but only if it's the "finiancial_data" table.
                    for item in items_sorted:
                        result.append(f"{item['id']}-{item['date']} | {item['category']} | ${item['amount']}") # Formats the data in a discord message so it still makes sense.
                
                elif table == "audit_log":
                    items_sorted = sorted(items, key=lambda x: datetime.strptime(x['removal_date'], "%H:%M-%d.%m.%Y"))  # Otherwise it instead sorts the items in the table still seperated by each category, but now the newest date appears a the top since "audit_log" has no nummerical value.
                    for item in items_sorted:
                        result.append(f"{item['id']} - {item['removal_date']} | {item['category']} | {item['removed_item']} | {item['reason']}") # Formats the data so it fits within a discord message and still makes sense.

            # Send the final output message as a single string
            await ctx.send("\n".join(result))
        else:
            await ctx.send("You do not have the correct permissions to access this command.", ephemeral=True)
    
    except Exception as e:
        await ctx.send(f"Failed to fetch data: {str(e)}")

### Guild managment
## Add_role: Adds roles that gain a permit to use the supabase discord bot commands. !!!ONLY USABLE BY THE GUILD/GROUP OWNER!!!
@bot.command(name="add_role")
@guild_owner_only()
async def add_role(ctx, role: discord.Role):
    guild_id = str(ctx.guild.id)
    if guild_id not in registered_guilds:
        registered_guilds[guild_id] = []
    if role.id not in registered_guilds[guild_id]["database_role_perms"]:
        registered_guilds[guild_id]["database_role_perms"].append(role.id)
        register_role_with_guild()
        await ctx.send(f"Added role {role.name} ({role.id}) to the list.")
    else:
        await ctx.send(f"Role {role.name} is already registered.")
    print(registered_guilds)

## Show_roles: Shows all roles with permission to use the supabase commands in your server.
@bot.command(name="show_roles")
@guild_owner_only()
async def show_roles(ctx):
    guild_id = str(ctx.guild.id)
    role_ids = registered_guilds.get(guild_id, {}).get("database_role_perms", [])

    if role_ids:
        # Convert role IDs to role names
        role_names = [ctx.guild.get_role(role_id).name for role_id in role_ids if ctx.guild.get_role(role_id)]
        if role_names:
            await ctx.send(f"Registered roles: {', '.join(role_names)}")
        else:
            await ctx.send("No valid roles found (roles may have been deleted).")
    else:
        await ctx.send("No roles registered for this guild.")

    print(registered_guilds)



### Silly commands
## Spine: Set so someone has or doesn't have a spine.
@bot.command(name="spine")
@guild_owner_only()
async def spine(ctx, user: discord.User, spinee: bool = True):
    if spinee:
        if user.id not in spine_save:
            spine_save.append(user.id)  # Add user ID to the list
            await ctx.send(f"{user} has gained a spine.")
        else:
            await ctx.send(f"{user} already has a spine.")
    else:
        if user.id not in spine_save:
            await ctx.send(f"{user} already has no spine.")
        else:
            spine_save.remove(user.id)  # Remove user ID from the list
            await ctx.send(f"{user} has lost their spine.")

### Bot managment
## Shutdown: Shuts down the bot.
@bot.command(name="shutdown")
@commands.is_owner() # Makes so the bot only responds if the user is the owner of the bot.
async def shutdown(ctx):
    await ctx.send("Shutting down...") # Sends a message on discord that the bot is shutting down.
    print("Shutting down...") # I forgot this stupid line so the bot would restart even if I told it to shut the fack up. >:C My fault I guess, but still!
    await bot.close() # Shuts down the bot.

## Restart: Restarts the bot letting it update its source code.
@bot.command(name="restart")
@commands.is_owner() # Make so the bot only responds if the user is the owner of the bot.
async def restart(ctx):
    await ctx.send("Restarting...") # Sends a message on discord that the bot is restarting.
    os.execv(sys.executable, ['python'] + sys.argv) # Kills the current runtime after having made a new one with the updated or same source code.

## Show_guilds: Shows all the guilds the bot is in.
@bot.command(name="show_guilds")
@commands.is_owner()
async def show_guilds(ctx):
    await ctx.send(f"Registered Guilds: {registered_guilds}")

bot.run(Token)
