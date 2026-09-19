# GodOfDars Backup Privacy Policy

Last updated: September 19, 2026

GodOfDars Backup is a private operational tool used by the GodOfDars project
owner to store encrypted PostgreSQL database backups in the owner's Google
Drive account.

## Google user data

The tool requests the Google Drive `drive.file` permission. This permission
allows it to create, read, update, and delete only the Google Drive files and
folders created through the tool. It does not grant access to unrelated files
already present in the account.

Google user data is used only to:

- upload an encrypted database backup and its checksum;
- verify that the uploaded backup is complete; and
- delete the previous backup after the new backup has been successfully
  uploaded and verified.

The tool does not sell, share, or use Google user data for advertising or
analytics. OAuth credentials and backup encryption keys are stored only on the
project owner's server. Backups are encrypted before they are uploaded.

## Retention and deletion

Only the latest verified backup is retained by the automated process. Older
backup files created by the tool are permanently deleted to limit storage use.
The project owner can revoke access at any time from their Google Account and
can delete the backup files directly from Google Drive.

## Contact

Questions about this policy can be sent to the support email shown on the
Google OAuth consent screen.
