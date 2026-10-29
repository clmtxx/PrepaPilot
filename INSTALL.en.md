# Install PrépaPilot on Windows

PrépaPilot helps you organise your studies: grades, documents, timetables, study sessions and personal progress. It runs on **64-bit Windows 10 (version 1809 or later) and Windows 11**. You do not need Python or administrator rights to use it.

This guide covers **version 2.26.1 · corrective distribution prepared on 29 October 2026**. Source files are available at [clmtxx/PrepaPilot](https://github.com/clmtxx/PrepaPilot); published downloads are available on the [latest release](https://github.com/clmtxx/PrepaPilot/releases/latest) page. The [publication report](VERIFICATION-PUBLICATION.md), in French, records verification for each distribution. If you received **PrepaPilot-2.26.1-Setup.exe** directly, open that file and follow setup. On first launch, choose your language and set up your space. **Ctrl+F** searches documents, grades and personal notes, **Ctrl+K** opens quick actions, and **F1** opens offline help. Your study session remains within reach on every page.

In version 2.26, reflections and illustrations respond to the pointer across their whole card on every page. Progress keeps its existing colours and gradients. Buttons and fields stay in place; **Settings → Reduce animations** stops these movements.

## Organise courses with an AI

In **Documents → Organise with AI**, choose **Prepare a new workspace**. The app creates readable copies grouped by folder, subject and type, plus an inventory with exact original file paths, an assistant guide and a proposal file. Data and workspace paths are shown in the dialog and can be copied.

Use **Copy instructions for my AI** and give them to your chosen assistant with file access. It reads `NOTICE-IA.md` and `catalogue.json`, then fills in `proposition.json`. To add courses from elsewhere on your computer, it copies them into `A-importer` and lists them in the proposal. Return to the app, choose **Read proposal**, review the changes, then **Apply organisation**. Managed originals remain intact. Preparing another workspace preserves previous sessions; **Resume a workspace…** reopens one.

PrépaPilot bundles no AI model and sends no courses through this workflow. Whether your assistant uses a local model or a remote service depends on the assistant you choose. Applied folders and imports are included in normal document backups; pending workspace copies remain on this computer.

## Recommended installation

1. Open the project’s [latest release](https://github.com/clmtxx/PrepaPilot/releases/latest) page.
2. Open the latest release and expand **Assets** if needed.
3. Download the file whose name ends in **`-Setup.exe`**.
4. Open the downloaded file and follow the setup instructions. The installer is available in English and French.
5. Open **PrépaPilot** from the Windows Start menu.

The app is installed for your Windows account. You can choose to create a desktop shortcut during setup.

The installer is not digitally signed. Windows may display a warning. Check that the file came from the release published by the project owner before deciding whether to open it.

The **Source code (zip)** and **Source code (tar.gz)** downloads contain the project's source files. Choose **Setup.exe** for the ready-to-use Windows app.

## Choose your language

The first time you open the app, choose **English** or **Français**. Then enter your name or nickname, optionally add your course or programme, and set up your subjects and timetable. You can start with an empty workspace or use an editable example.

To switch languages later, open **Settings → Language**, choose a language and click **Save preferences**. In French, use **Réglages → Langue → Enregistrer mon profil**. The whole interface changes immediately, without restarting, and your choice is remembered for future launches.

Your own subject names, assessment titles, goals, personal notes and document contents stay as you wrote them. Changing the interface language does not translate or replace your work.

## Portable version

The release also includes a file whose name ends in **`-Windows-portable.zip`**:

1. Download that ZIP file.
2. In File Explorer, right-click the ZIP and choose **Extract All**.
3. Open the extracted **PrepaPilot** folder, then double-click **PrepaPilot.exe**.

Keep the whole folder, including **`_internal`**. Opening the executable from the ZIP preview will not work. Put the extracted folder somewhere your account can write to, such as Documents.

## Back up your work and move to another PC

| Version | Where your data is stored |
| --- | --- |
| Installed | `%LOCALAPPDATA%\PrepaPilot\data` |
| Portable | The `data` folder next to `PrepaPilot.exe` |

To find the installed app's data, paste **`%LOCALAPPDATA%\PrepaPilot`** into File Explorer's address bar.

To move to another PC or switch between the portable and installed versions:

1. In the old copy, pause any running study session, then open **Settings → Export all my data**.
2. Keep the resulting **`.prepapilot`** file and close the app.
3. Install and open the new copy. Use the same app version on both sides when transferring your data.
4. Open **Settings → Import my data** and select the exported file.
5. Read the summary before confirming: a full import replaces the destination workspace. Check your grades, documents and preferences afterwards.

Keep the old copy and your export until you have checked the transfer. A `.prepapilot` file contains your personal data; keep it private and do not attach it to a GitHub release.

## Update the app

The final distribution is connected to the public repository `clmtxx/PrepaPilot`. PrépaPilot checks for new releases at startup, at most once a day, and notifies you when an update is available. You can also open **Settings → Updates** and check manually. Version 2.26.1 corrects downloads from GitHub’s current file hosting.

With the installed version, choose **Download and install**. The app downloads the release installer, checks its SHA-256 checksum and offers to close PrépaPilot before starting setup. Pause any running study session and save your changes first. The new installer replaces the program and keeps your grades, documents and preferences. **You do not need to uninstall the app.**

You can still download the latest installer from **Releases**, close the app and run it yourself. Exporting your workspace before an update gives you an independent backup.

The portable version can check for updates and open the **Releases** page. Download the new portable ZIP, extract it into a new folder, then use the export and import steps above. Keep the old folder until you have checked the new copy.

If the app says its update repository has not been configured, use the files provided by the publisher. Builds produced by the project's GitHub workflow receive their repository address automatically.

## Uninstall

Close PrépaPilot, then open **Windows Settings → Apps** and uninstall it. The uninstaller keeps **`%LOCALAPPDATA%\PrepaPilot\data`** so you can reinstall later. If you also want to remove your workspace, export anything you want to keep, then delete that data folder yourself.

For the portable version, deleting its folder also deletes its data. Export your work before removing it.

## Google Drive

You can use all local features without a Google account. The publisher prepares Google's shared application configuration once and includes it in the installer. With a configured copy, open **Settings → Manage Google Drive backups → Sign in with Google**, choose your account in the browser and authorise PrépaPilot. You can then create or find your backup folder. Users do not need a Google Cloud project or a JSON file. Personal configurations remain available under **Advanced options** for those who need them.

The final distribution includes the shared Google application client, with the Google app in production. A real sign-in, backup and restore were verified on 28 October 2026 using fictional study data. No account is connected automatically and Google remains optional: local `.prepapilot` exports can also back up and move your workspace. On another PC, use a copy prepared with the same Google application configuration and connect your own account again; a second computer and a different account have not yet been tested. The project's **Documentation** folder contains **Google-Drive.md** and **Guide-PrepaPilot.md**, currently in French. See also the bilingual [privacy notice](PRIVACY.md).
