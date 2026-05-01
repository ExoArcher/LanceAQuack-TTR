# User/invite-server Command Briefing

## Feature Purpose
DM user the OAuth link to add the bot to a Discord server. Works as a User App (no server membership required).

## Scope
- Slash command: `/invite-server`
- Build invite link for server install
- Send link via DM to user
- Handle DM failures gracefully
- Provide both DM and channel fallback

## Code to Extract
**From Main-1.5.0/bot.py**
- `@app_commands.command(name="invite-server")` handler
- Build server install invite link (uses bot.user.id)
- Send embed/message to user via DM
- Fallback to ephemeral channel message if DM blocked

## Command Flow
```
1. User invokes /invite-server (anywhere: server, DM, group, User App)
2. Check ban status (_reject_if_banned)
3. Build server install link using bot.user.id
4. Create embed with link and instructions
5. Attempt to DM embed to user
6. If DM fails, send ephemeral message in channel instead
7. Send ephemeral response: "Check your DMs" or "See below"
```

## Invite Link Format
Server install link with required permissions:
```
https://discord.com/api/oauth2/authorize?client_id={bot_id}&permissions=[perms]&scope=bot+applications.commands
```

Required permissions: Send Messages, Edit Messages, Manage Messages, Manage Channels (create category/channels for /pd-setup)

## Embeds Sent
Invite embed includes:
- Title: "Add Paws Pendragon to Your Server"
- Link to server install
- Instructions: "Click the link to add the bot to your server"
- Note: "Server admins can then run /pd-setup to create live feeds"
- Permission requirements listed

## Dependencies
- Infrastructure/user-system (_reject_if_banned)
- discord.py library

## Key Design Patterns
1. **User App compatible** - No guild check, works anywhere
2. **DM-first** - Try to send to DM, fall back to ephemeral
3. **Graceful DM failure** - If user has DMs blocked, send ephemeral in channel
4. **Ban check** - Reject before doing work
5. **No API calls** - Pure local data, instant response
6. **Dynamic bot ID** - Uses bot.user.id, works across multiple deployments

## API Calls
- user.send(embed=...)
- ctx.response.send_message(content=..., ephemeral=True)

## Database Access
- Check banned_users

## Tests to Verify
- [ ] /invite-server builds invite link instantly
- [ ] Invite link includes correct bot ID
- [ ] Permissions bitmask correct
- [ ] Embed sent to user DM successfully
- [ ] If DM blocked, ephemeral message sent in channel
- [ ] Ban check prevents banned users
- [ ] Works in User App (no guild context)
- [ ] Works in DMs, servers, group chats
- [ ] DM failure handled gracefully

## Special Requirements
- Works as User App (no server membership required)
- Works in DMs, servers, group chats
- No API calls (all static data)
- DM failure should not prevent command success
- Ban check before doing work

## Integration Notes
- Slash command handler in bot.py
- Called by users wanting to add bot to their server
- Response is instant (no network I/O)

## Error Handling
- DM blocked - Send ephemeral message in channel instead
- No timeout needed (no I/O)
- Banned user - Reject with ephemeral message

## Response Pattern
If DM sent:
```
"Sent invite link to your DMs!"
```

If DM blocked, ephemeral embed in channel:
```
(Full invite embed displayed in channel)
```

## Reference Implementation
See Main-1.5.0/bot.py for complete invite-server command handler.
