# Send files with RNCP

Open **Tools → RNCP**. The receiving device must start its RNCP listener and approve your Reticulum identity. Enter that listener's destination hash in the Send tab.

On Android or in a browser, choose **Browse** and select a file. neXt streams a private copy into its own storage and selects it for sending. Wait for preparation to finish, then choose **Send File**. The original file remains on your device. Desktop users can also select a native file path directly.

Imported files remain available for retry after leaving the page or restarting the app. Select a listed copy to use it again, or choose **Remove copy** when finished. Removing a copy never removes the original selected file. Copies in use by an active transfer cannot be removed. A canceled import is cleaned up; an import interrupted by an app crash can be removed from the list afterward.

The import limit is 512 MiB per file, 1 GiB in total and 16 retained copies per identity. Available device storage can impose a lower limit. RNCP transfers can take a long time over radio links; use the progress display and Cancel control. Success means the final segment completed, rather than only the first segment.

Imported copies are separate from RNCP's remotely fetchable shared folder. Importing a file does not start a listener or enable remote fetching. Existing identity-key and private-storage restrictions still apply. This import limit is specific to RNCP; message attachments have their own transport limits.
