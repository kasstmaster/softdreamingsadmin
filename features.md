1. Core Event Automations
Welcome / Join / Leave System
Sends custom welcome messages to WELCOME_CHANNEL_ID.
Assigns:
BOT_JOIN_ROLE_ID to bots on join.
MEMBER_JOIN_ROLE_ID to members after a 1-day delay (tracked with persistent storage + background watcher).
Logs joins, leaves, kicks, bans in mod/bot logs.
Birthday & Server Boost Announcements
Detects role changes via on_member_update.
Posts:
BOOST_TEXT when a user boosts.
BIRTHDAY_TEXT when the birthday role is assigned.

2. Dead Chat System (Role Game)
This is one of the largest subsystems.
Dead Chat Role Mechanics
Tracks activity timestamps per Dead Chat channel.
If a channel is silent for DEAD_CHAT_IDLE_SECONDS, the next speaking member steals the Dead Chat role.
Applies optional cooldowns per member.
Dead Chat Win Announcements
Announces the steal win.
Deletes previous win announcements.
Notes plague events or prize chances.
Daily Auto-Reset
At hour DEAD_CHAT_RESET_HOUR_UTC, removes the Dead Chat role from all members.
Persistent Storage
Saves:
last message timestamps
last winner times
last announcement message IDs
current holder
Has /deadchat_init, /deadchat_state_init, /deadchat_rescan to initialize or repair.

3. Dead Chat Plague System
Monthly “contagious day” mechanic.
Features
Admin schedules a plague day with /plague_infect.
On plague day, the member who steals Dead Chat becomes infected.
Infected gets INFECTED_ROLE_ID for 3 days.
Infection expires automatically via infected_watcher.
Storage
Saves:
scheduled plague days
infected members + expiry timestamps

4. Prize Drop System (Movie / Nitro / Steam)
Supports common / uncommon / rare prize drops triggered by Dead Chat or scheduled by admins.
Features
Admin can:
drop instant prize messages (/prize_movie, /prize_nitro, /prize_steam without date)
or schedule future drops (same commands with date)
list scheduled prizes (/prize_list)
delete scheduled prizes (/prize_delete)
manually announce prizes (/prize_announce)
Fully automated:
Schedules run in background and post the prize message when the time arrives.
Each prize uses a persistent interactive button to claim prize.
Sends an announcement to the welcome channel when claimed.

5. Twitch Live Notification System
Features
Watches listed Twitch channels via API.
When a channel goes live:
Sends announcement with @everyone.
Saves state so announcements aren't duplicated.
Saves live-state in storage.
Refreshes OAuth token when expired.

6. Sticky Message System
Per-channel persistent sticky messages with UI buttons.
Features
Admin can:
/sticky set "text" → sets sticky
/sticky clear → removes sticky
Bot automatically reposts the sticky whenever someone talks.
Stores:
sticky text
current sticky message ID
Reposts with a GameNotificationView attached.

7. Game Notification Role Selector (UI Dropdown)
UI component letting users opt-in to game roles.
Features
Clicking Get Notified opens a dropdown.
User selects roles for:
General games
Among Us Vanilla
Among Us Modded
Among Us Proximity Chat
Automatically adds/removes roles.
Replies ephemerally with changes.
8. Auto-Delete Channels
For channels in AUTO_DELETE_CHANNEL_IDS:
Deletes any message after DELETE_DELAY_SECONDS.
Birthday messages are exempt (detected via keywords).

9. Logging System
Two destinations:
MOD_LOG_THREAD_ID
BOT_LOG_CHANNEL_ID
Bot logs:
bans
kicks
user departures
bot joins
plague events
dead chat errors
storage issues

10. Storage System (Message-Based Persistent DB)
Stored inside a hidden storage channel (STORAGE_CHANNEL_ID).
Subsystems that store persistent JSON:
Sticky messages
Member join pending queue
Deadchat timestamps
Deadchat state
Twitch state
Prize schedules (Movie/Nitro/Steam)
Plague data
Admin commands create the missing storage messages.

11. Admin Utility Commands
/say
Bot says a message.
/editbotmsg
Edit any bot message with 4 lines of content.
/birthday_announce
Manual birthday message.

12. Background Loops
Running continuously:
twitch_watcher: checks live status every 60s
deadchat_reset_loop: resets Dead Chat role once per day
infected_watcher: clears expiring infections
member_join_watcher: applies delayed join roles
scheduled prize runners: one loop per scheduled prize

13. Views & Buttons
BasePrizeView
MoviePrizeView
NitroPrizeView
SteamPrizeView
GameNotificationView
GameNotificationSelect
All are persistent (timeout=None or registered on_ready).

14. Stealth Features & Edge-Case Handling
Prevents bot messages from triggering dead chat.
Prevents awarding infected role twice.
Avoids double Twitch notifications.
Catches missing storage and instructs admins how to repair.
Cleans old Dead Chat announcement messages when a new one fires.

# COMPLETE FEATURE SUMMARY
Welcome system
Boost announcements
Birthday announcements
Delayed role assignment for new members
Bot-join role assignment
Kick/ban/leave logging
Dead Chat role system with steal mechanic
Idle detection per channel
Dead Chat daily auto-reset
Dead Chat cooldown system
Dead Chat win announcements
Dead Chat plague system (scheduled infection days)
Infection role & expiration
Prize drop system (Movie / Nitro / Steam)
Scheduled prize system with background tasks
Prize claim UI
Twitch live tracking and announcements
Twitch OAuth token refresh
Sticky message system with auto-repost
Game Notification dropdown UI
Auto delete channels with exceptions
Persistent storage architecture using hidden channel messages

Admin commands for repairing/initializing storage

Admin message edit & say tools

Background workers for Twitch, prizes, dead chat reset, join role, infection expiry
