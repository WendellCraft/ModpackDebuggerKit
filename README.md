# Modpack Debugger Kit

The Modpack Debugger Kit is a Python application designed to help creators of modpacks easily find mods causing crashes along with various small other helpful features.

## Features

*   **Project Management:** Save and load project configurations, including mod folder path and dependency rules.
*   **Mod Folder Snapshotting:** Create a snapshot of your current mod list to easily detect new additions.
*   **New Mod Detection:** Automatically identify which mods have been added since the last snapshot.
*   **Binary Search Debugging:** Automate the process of splitting your mod list into testable groups to isolate problematic mods quickly.
    *   **Mode 1 (All Mods):** Debug the entire modpack using a binary search.
    *   **Mode 2 (Specific New Mods):** Focus the search only on recently added mods.
*   **Dependency Awareness:** Maintain a list of mod dependencies to ensure essential libraries are always included in the test group of their dependent mods.
*   **Hanging Library Detection:** Identify library mods that remain in the folder but are no longer required by any main mod (useful for cleanup).
*   **Theming:** Toggle between dark and light themes.

## Prerequisites

To run this application, you need Python installed (3.11+ recommended). You also need pip installed.

## Installation and Setup

1.  **Clone the Repository (or download the files):**

    ```bash
    git clone https://github.com/WendellCraft/ModpackDebuggerKit.git
    cd ModpackDebuggerKit
    ```

2.  **Install Dependencies:**

    This application relies on various dependencies. Install them using pip:

    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the Application:**

    ```bash
    python modpack_debugger.py
    ```

## Usage Guide

### 1. Initial Setup

1.  **New or Load Project:** Start a `New Project` or `Load Project` if you have saved one previously.
2.  **Select Mod Folder:** Click `📁 Select Mod Folder` and choose the actual `mods` directory of your Minecraft instance (e.g., `C:\Users\User\AppData\Roaming\.minecraft\mods`).

### 2. Preparing for Debugging (New Mod Tracker)

If you are tracking new mods:

1.  **Create Snapshot:** Click `📸 Create Snapshot`. This logs all current mods. You only need to do this once, then whenever you add new mods simply press detect new mods and it will update your snapshot accordingly.
2.  **Add New Mods to Folder.**
3.  **Detect New Mods:** Click `🔍 Detect New Mods`. The application will compare the current mod list with the snapshot and list the new mods. You can then save them and debug them.

### 3. Managing Dependencies

For accurate binary searching, it is crucial to tell the tool which mods require which libraries:

1.  Click `⚙️ Manage Dependencies`.
2.  Add rules (e.g., Mod A requires Library X, Y, Z). When the debugger tests Mod A, it will automatically ensure X, Y, and Z are included in the test group, even if they were originally in the opposite half of the split.

### 4. Starting the Debug Session

1.  **Select Debug Mode:**
    *   **Mode 1 (All Mods):** Tests every mod in your folder. Ideal for finding a long-standing conflict.
    *   **Mode 2 (Specific New Mods):** Tests only the mods you selected from the new mod detection step. Ideal for finding the culprit in a new update batch.
2.  **Start Debug:** Click `🚀 Start Debug`.

### 5. Binary Search Process

1.  The application will move the majority of your mods to a temporary folder (`temp_mods` created next to the script).
2.  It will move the first test group into your main `mods` folder.
3.  A dialog will appear: **"Testing X mods. Launch Minecraft now and test if it loads."**
4.  **Launch Minecraft** (from your launcher).
5.  **Report Result:**
    *   Click `✅ Game Worked` if Minecraft loads successfully (indicating the culprit is in the remaining half).
    *   Click `❌ Game Crashed` if Minecraft crashes (indicating the culprit is in the current test group).
6.  Repeat the process until a single mod is isolated.

***Important:*** *Do not manually close the debug dialog until you have launched and tested Minecraft. If you close the application during an active scan, you may need to manually restore the mods from the `temp_mods` folder.*

### 6. Cleanup

1.  Once the debug is complete, all mods are automatically restored.
2.  Check the `⚠️ Hanging Libraries` button if it is highlighted (yellow/orange). This indicates dependencies that are present but no longer needed. You can delete them from the resulting dialog.

## Technical Details

The application uses the following directory structure:

*   `modpack_debugger.py` (The main script)
*   `temp_mods/` (Created automatically to temporarily hold mods during testing)
*   `[ProjectName].json` (Saved project files, containing settings and dependency rules)
