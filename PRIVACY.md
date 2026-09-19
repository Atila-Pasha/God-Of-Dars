# GodOfDars Backup Privacy Policy

Last updated: September 19, 2026

GodOfDars Backup is a private operational tool used by the GodOfDars project
owner to store encrypted PostgreSQL database backups in the owner's Dropbox
account.

## Dropbox user data

The tool uses Dropbox through rclone to create, read, update, and delete the
encrypted files in its configured backup location.

Dropbox user data is used only to:

- upload an encrypted database backup and its checksum;
- verify that the uploaded backup is complete; and
- delete the previous backup after the new backup has been successfully
  uploaded and verified.

The tool does not sell, share, or use Dropbox user data for advertising or
analytics. OAuth credentials and backup encryption keys are stored only on the
project owner's server. Backups are encrypted before they are uploaded.

## Retention and deletion

Only the latest verified backup is retained by the automated process. Older
backup files created by the tool are permanently deleted to limit storage use.
The project owner can revoke access at any time from Dropbox's connected-app
settings and can delete the backup files directly from Dropbox.

## Contact

Questions about this policy can be sent to the project owner through the
contact information associated with this repository.
