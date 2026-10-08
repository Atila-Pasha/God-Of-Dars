# GodOfDars Privacy Policy

Last updated: October 8, 2026

This Privacy Policy describes how GodOfDars, an educational strategy game
provided through a Telegram Bot, processes information when operating the bot
in private chats and Telegram groups. It also covers the project's optional
administration bot and database backup integration.

This policy reflects the implementation in this repository. Hosting locations,
live deployment settings, and operator practices that are not documented in
the repository cannot be confirmed by this policy.

## Data We Collect

### Telegram account information

GodOfDars stores your numeric Telegram User ID, username (if available), first
name, and last name (if available). It assigns an internal game account ID and
stores account creation and update times, active/inactive status, game level,
hospital level, and the time of your last rewarded slogan. Names and usernames
are updated when the bot processes relevant Telegram profile information;
updates may be delayed by caching.

Registration is not limited to users who send `/start`. For group updates that
Telegram delivers to the bot, the application may register the message sender,
the author of a replied-to message, joining or leaving members, and people
identified in membership updates. It skips bot accounts in this group
registration process. This can create a game account even if the person has
not started a private conversation with GodOfDars. The implementation does
not maintain a complete group membership list.

### Group and channel information

The database stores Telegram group chat IDs, titles, optional usernames,
active/inactive status, and creation and update times. Game records can link
users to groups where they answered questions or participated in activities.

For published group questions and chance boxes, it stores the associated
group, game content or references, Telegram message IDs (including relevant
sticker messages), publication or creation times, expiry and completion status,
and, where applicable, the winning user. Attack records can include source and
launch chat IDs and launch message IDs.

Configured subscription channels are stored by Telegram ID and/or username.
Channel-joining quests may also contain a channel identifier and invite link.
The bot asks Telegram about membership to control access or validate rewards.
Routine membership-check results are cached in memory; related quest progress
and reward records are stored in PostgreSQL.

### Game activity and submitted content

Depending on the features you use, GodOfDars stores:

- Resource balances (coins, diamonds, and bananas used as game XP), levels,
  school/castle strength, defense power, and related status and timestamps.
- Owned teachers as game units, their levels, health and status, recovery
  periods, shield inventory and activation times, and mine levels, production,
  collections, and daily counters. These are game mechanics, not records of
  your real health or education.
- Attacks and defenses, attacker and target references, selected teachers,
  combat snapshots, damage, loot, outcomes, timing, and processing/retry errors.
  Random opponent selections include selected units, reroll counts, and expiry.
- Submitted question-answer text, question and group references, correctness,
  validity, and submission times. Incorrect answers can also be retained.
- Study sessions, daily quest progress, activity dates, event references,
  completion and claim times, chance-card rewards, generated CAPTCHA answers
  and hashes, and chance-box attempts and correctness.
- Referral relationships between accounts and associated rewards. Referral
  links contain an internal account identifier.
- In-game reward and transaction histories: resource type, amount, reason,
  related activity, timestamps, and, where recorded, balances before and after
  a transaction. These are game-resource records; the current application has
  no payment-card collection or real-money checkout integration.
- Queued notifications, including recipient references, destination chat IDs,
  message text or message-deletion instructions, delivery state, retries,
  timestamps, and error details.

The bot processes commands, button interactions, and messages delivered by
Telegram. The application does not implement a general archive of all chat
messages, but stores the submitted answers and generated notification content
described above. Avoid including sensitive information in game answers.

Administrators also supply game questions, correct answers, teacher and shield
catalogs, study packs, rewards, channel settings, and presentation assets or
Telegram asset identifiers. These are stored to configure the game.

### Operational information

Application logs may contain user or chat identifiers, message identifiers,
and error details. Development mode also enables SQL logging, which may
include database values. Runtime counters and timing samples are maintained
in memory. The repository does not establish how long deployment logs are
retained.

The current application has no dedicated collection or storage fields for
phone numbers, email addresses, contact lists, precise location, or user IP
addresses. This does not prevent personal information from appearing in text
you submit or in diagnostic output.

## How We Use Data

We use the information described above to:

- Identify returning Telegram accounts and associate them with game progress.
- Display names and usernames, find players by username or Telegram ID,
  select opponents, and deliver messages to the correct chats.
- Run educational questions, battles, resource accounting, upgrades, study,
  recovery, quests, referrals, and reward eligibility checks.
- Produce profiles, rankings, game statistics, and battle reports.
- Prevent duplicate rewards and repeated attempts, enforce account restrictions,
  and recover from interrupted processing or message-delivery failures.
- Administer the game, send administrator broadcasts, diagnose problems, and
  back up and restore the database.

The administrator broadcast function can select registered accounts including
inactive accounts; deactivation is not a notification opt-out.

## Data Storage and Retention

Persistent application records are stored in PostgreSQL. The supplied Docker
configuration uses a persistent database volume. The repository does not
identify a verified hosting provider or storage country, or establish a
general retention period for accounts, game history, answers, or notifications.
There is no implemented schedule that automatically erases inactive accounts
or all personal data after a fixed time; these records may remain indefinitely
unless removed through operator intervention.

Game expiry times and daily counter resets are gameplay controls, not a
promise of record deletion. The cleanup worker deletes certain completed or
expired Telegram game messages and clears their stored message IDs, while
retaining the underlying database records.

### Database backups and Dropbox

The repository includes an optional backup script and a daily scheduling
configuration. The script creates a full PostgreSQL dump, including the user
and game data described above, along with database operational metadata and
checksums. It uploads a backup through rclone to a configured remote intended
to be an encrypted Dropbox location in the operator's account. Encryption
depends on the operator configuring an rclone crypt remote correctly; the
script alone does not verify that configuration.

After uploading and downloading the new backup for verification, the script
synchronizes the destination to retain only the latest verified archive and
checksum. It also retains a local copy and removes its temporary working
files on exit. The local archive is not encrypted by this script. Failed runs,
provider recovery/version history, or separately managed copies can affect
actual retention; permanent erasure from every backup cannot be guaranteed
from this implementation. The operator can revoke the Dropbox connection
and manage backup files through their Dropbox account.

## Data Sharing

- **Telegram:** Bot interactions, membership checks, outgoing messages,
  administrator-bot responses, and message-management requests are processed
  through Telegram. Telegram's own data handling is outside this repository.
- **Other players and group members:** Names or usernames and game statistics
  can appear in leaderboards, group profile responses, opponent previews, and
  battle reports. Telegram user identifiers may also be included in interaction
  buttons or player references. Information posted in a group is visible to
  its audience; game activity should not be treated as entirely private.
- **The operator and administrators:** Authorized administrators can search
  registered users and view or change account and game information. People
  with authorized access to the hosting environment, database, logs, or backups
  may also access stored information.
- **Backup and infrastructure services:** If the supplied backup integration
  is enabled, Dropbox receives the backup files described above. The bot also
  supports an optional Telegram connection proxy. Actual hosting, proxy, and
  backup configuration are deployment choices not verified by this policy.

No advertising-network, data-sale, or external analytics integration was found
in the current application. This is a statement about the reviewed code, not
an assurance about undocumented operator actions or third-party services.

## User Rights

You can view supported game information through the bot's profile and related
menus. Changes to your Telegram name or username can be reflected when the
bot next processes your profile, subject to caching. There is no dedicated
personal-data export or general data-correction workflow in the current bot.

Privacy questions and requests for access, correction, or deletion require
operator assistance using the contact route below once it is supplied. The
repository does not establish a request-handling procedure or response deadline.
This policy does not limit rights you may have under applicable law.

## Data Deletion

The current implementation has no self-service account-deletion command and
no complete administrator function for erasing a user's personal data.
Administrators can deactivate accounts, but this retains stored information.
Full deletion or anonymization would require manual operator work across
linked records; some database relationships prevent deleting an account while
associated history remains. No automated deletion process or completion time
is promised here.

Stopping interaction, blocking the bot, leaving a group, or deleting Telegram
messages does not trigger deletion of the PostgreSQL records. Subsequent group
updates can still cause profile processing as described above. Removing data
from the live database would not by itself remove existing backup copies or
messages already delivered to Telegram and other participants.

## Security

The implementation uses an administrator ID allow-list for the admin bot,
loads deployment credentials from configuration, and provides a Docker setup
without a publicly published database port. The backup script restricts local
backup-directory permissions and supports an encrypted remote as described
above. Actual access controls, database encryption, key management, and server
security depend on deployment and cannot be verified from the repository.
No method of storage or transmission can guarantee absolute security.

## Changes to This Policy

This policy may be revised to reflect changes to GodOfDars. Revisions will be
recorded in this file with an updated date. The current bot does not implement
automated privacy-policy change notifications.

## Contact

**GodOfDars privacy contact: [TO BE PROVIDED BY THE OPERATOR: a monitored
support email address or Telegram support username].**

No verified public privacy contact is specified in the repository. This is a
placeholder, not an operational support channel; the operator must replace it
with a valid contact before relying on this policy as a user request route.
