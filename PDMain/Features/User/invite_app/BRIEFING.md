# User/invite-app Command Briefing

## Feature Purpose
DM user the OAuth link to add the bot to their personal Discord account (User App install). Works as a User App (no server membership required).

## Scope
- Slash command: `/invite-app`
- Build invite link for User App install
- Send link via DM to user
- Handle DM failures gracefully
- Provide both DM and channel fallback

## Code to Extract
**From Main-1.5.0/bot.py**
- `@app_commands.command(name="invite-app")` handler
- Build User App install invite link (uses bot.user.id)
- Send embed/message to user via DM
- Fallback to ephemeral channel message if DM blocked

## Command Flow
```
1. User invokes /invite-app (anywhere: server, DM, group, User App)
2. Check ban status (_reject_if_banned)
3. Build User App install link using bot.user.id
4. Create embed with link and instructions
5. Attempt to DM embed to user
6. If DM fails, send ephemeral message in channel instead
7. Send ephemeral response: "Check your DMs" or "See below"
```

## Invite Link Format
User App install link:
```
https://discord.com/api/oauth2/authorize?client_id={bot_id}&scope=applications.commands
```

## Embeds Sent
Invite embed includes:
- Title: "Add Paws Pendragon to Your Account"
- Link to User App install
- Instructions: "Click the link to add the bot to your personal Discord account"
- Note: "You can then use /ttrinfo, /doodleinfo, /calculate, etc. anywhere"

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
- [ ] /invite-app builds invite link instantly
- [ ] Invite link includes correct bot ID
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
- Called by users wanting to add bot to their account
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
See Main-1.5.0/bot.py for complete invite-app command handler.
