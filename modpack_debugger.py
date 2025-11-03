import os
import shutil
import json
import threading
from datetime import datetime
from pathlib import Path
import hashlib
import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

def _get_sha1_hash(file_path):
    """Calculate the SHA1 hash of a file."""
    sha1 = hashlib.sha1()
    try:
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(65536)  # Read in 64k chunks
                if not data:
                    break
                sha1.update(data)
        return sha1.hexdigest()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return None

def _get_mod_info(mod_hash):
    """Get mod information from Modrinth API using the file hash."""
    url = f"https://api.modrinth.com/v2/version_file/{mod_hash}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching mod info for hash {mod_hash}: {e}")
        return None

def _get_project_versions(project_id):
    """Get all versions of a project from Modrinth API."""
    url = f"https://api.modrinth.com/v2/project/{project_id}/version"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching project versions for ID {project_id}: {e}")
        return None
    
class ModpackDebuggerKit(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Modpack Debugger Kit")
        self.geometry("1200x824")
        self.minsize(1000, 700)
        
        self.temp_dir = Path(__file__).parent / "temp_mods"
        self.project_data = self.get_default_project_data()
        self.active_scan = False
        self.scan_cancelled = False
        self.current_test_group = []
        self.detected_new_mods = []
        self.saved_new_mods = []
        self.hanging_libraries = []
        self.project_file_path = None
        self.project_modified = False
        self.sync_thread = None
        self.sync_cancelled = False
        
        self.setup_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def get_default_project_data(self):
        return {
            "mods_dir": "",
            "latest_snapshot": None,
            "dependencies": {},
            "saved_new_mods": [],
            "theme": "dark"
        }
    
    def setup_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=80, corner_radius=0)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        
        title_label = ctk.CTkLabel(header, text="🔧 Modpack Debugger Kit", 
                                   font=ctk.CTkFont(size=28, weight="bold"))
        title_label.pack(side="left", padx=30, pady=20)
        
        theme_btn = ctk.CTkButton(header, text="🌓 Theme", width=100, 
                                 command=self.toggle_theme)
        theme_btn.pack(side="right", padx=30, pady=20)
        
        # Main container
        main_container = ctk.CTkFrame(self, fg_color="transparent")
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Left panel
        left_panel = ctk.CTkFrame(main_container, width=350)
        left_panel.pack(side="left", fill="both", padx=(0, 10))
        left_panel.pack_propagate(False)
        
        self.setup_left_panel(left_panel)
        
        # Right panel
        right_panel = ctk.CTkFrame(main_container)
        right_panel.pack(side="right", fill="both", expand=True)
        
        self.setup_right_panel(right_panel)
        
    def setup_left_panel(self, parent):
        # Project management
        project_frame = ctk.CTkFrame(parent)
        project_frame.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkLabel(project_frame, text="Project Management", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 15))
        
        btn_frame1 = ctk.CTkFrame(project_frame, fg_color="transparent")
        btn_frame1.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(btn_frame1, text="📁 New Project", 
                     command=self.new_project).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(btn_frame1, text="📂 Load Project", 
                     command=self.load_project).pack(side="right", expand=True, padx=5)
        
        btn_frame2 = ctk.CTkFrame(project_frame, fg_color="transparent")
        btn_frame2.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(btn_frame2, text="💾 Save Project", 
                     command=self.save_project).pack(side="left", expand=True, padx=5)
        
        self.save_as_btn = ctk.CTkButton(btn_frame2, text="📄 Save As", 
                                         command=self.save_project_as, 
                                         state="disabled", fg_color="gray")
        self.save_as_btn.pack(side="right", expand=True, padx=5)
        
        # Mod folder
        folder_frame = ctk.CTkFrame(parent)
        folder_frame.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkLabel(folder_frame, text="Mod Folder", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 15))
        
        self.folder_label = ctk.CTkLabel(folder_frame, text="No folder selected", 
                                        wraplength=300, fg_color=("gray85", "gray25"), 
                                        corner_radius=6, height=40)
        self.folder_label.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkButton(folder_frame, text="📁 Select Mod Folder", 
                     command=self.select_mod_folder).pack(fill="x", padx=10, pady=10)
        
        # Snapshot management
        snapshot_frame = ctk.CTkFrame(parent)
        snapshot_frame.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkLabel(snapshot_frame, text="New Mod Tracker", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 15))
        
        ctk.CTkButton(snapshot_frame, text="📸 Create Snapshot", 
                     command=self.create_snapshot).pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(snapshot_frame, text="🔍 Detect New Mods", 
                     command=self.detect_new_mods).pack(fill="x", padx=10, pady=5)
        
        self.access_saved_btn = ctk.CTkButton(snapshot_frame, text="📋 Access Saved New Mods", 
                                               command=self.access_saved_new_mods,
                                               state="disabled", fg_color="gray")
        self.access_saved_btn.pack(fill="x", padx=10, pady=5)
        
        self.hanging_libs_btn = ctk.CTkButton(snapshot_frame, text="⚠️ Hanging Libraries", 
                                              command=self.show_hanging_libraries,
                                              fg_color="gray")
        self.hanging_libs_btn.pack(fill="x", padx=10, pady=5)
        
        # Dependency manager
        dep_frame = ctk.CTkFrame(parent)
        dep_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        ctk.CTkLabel(dep_frame, text="Mod Dependencies", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10, 15))
        
        ctk.CTkButton(dep_frame, text="⚙️ Manage Dependencies", 
                     command=self.manage_dependencies).pack(fill="x", padx=10, pady=5)
        
    def setup_right_panel(self, parent):
        # Debug mode selection
        mode_frame = ctk.CTkFrame(parent)
        mode_frame.pack(fill="x", padx=15, pady=15)
        
        ctk.CTkLabel(mode_frame, text="Debug Mode", 
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 10))
        
        self.mode_var = ctk.StringVar(value="all")
        
        mode_radio_frame = ctk.CTkFrame(mode_frame, fg_color="transparent")
        mode_radio_frame.pack(pady=10)
        
        ctk.CTkRadioButton(mode_radio_frame, text="Mode 1: All Mods (Binary Search)", 
                          variable=self.mode_var, value="all").pack(side="left", padx=20)
        ctk.CTkRadioButton(mode_radio_frame, text="Mode 2: Specific New Mods", 
                          variable=self.mode_var, value="specific").pack(side="left", padx=20)
        
        # Start button
        btn_frame = ctk.CTkFrame(mode_frame, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        self.start_btn = ctk.CTkButton(btn_frame, text="🚀 Start Debug", 
                                       command=self.start_debug, width=150, height=40,
                                       font=ctk.CTkFont(size=14, weight="bold"))
        self.start_btn.pack(side="left", padx=10)
        
        # Log area
        log_frame = ctk.CTkFrame(parent)
        log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        ctk.CTkLabel(log_frame, text="Debug Log", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(15, 10))
        
        self.log_text = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(size=12))
        self.log_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
    def log(self, message, level="INFO"):
        def _update_log_widget():
            if level == "PROGRESS":
                # Delete the previous progress line
                self.log_text.delete("end-2l", "end-1l")
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            prefix = {"INFO": "ℹ️", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️", "PROGRESS": "⏳"}.get(level, "•")
            
            self.log_text.insert("end", f"[{timestamp}] {prefix} {message}\n")
            self.log_text.see("end")

        # Schedule the GUI update to run on the main thread
        self.after(0, _update_log_widget)
        
    def toggle_theme(self):
        current = ctk.get_appearance_mode()
        new_theme = "light" if current == "Dark" else "dark"
        ctk.set_appearance_mode(new_theme)
        self.project_data["theme"] = new_theme
        self.log(f"Theme changed to {new_theme} mode", "SUCCESS")
        
    def new_project(self):
        if self.active_scan:
            messagebox.showwarning("Active Scan", "Cannot create new project during active scan")
            return
        self.project_data = self.get_default_project_data()
        self.folder_label.configure(text="No folder selected")
        self.log_text.delete("1.0", "end")
        self.project_file_path = None
        self.project_modified = False
        self.save_as_btn.configure(state="disabled", fg_color="gray")
        self.log("New project created", "SUCCESS")
    
    def mark_modified(self):
        self.project_modified = True
        
    def save_project(self):
        if self.active_scan:
            messagebox.showerror("Error", "Cannot save project during an active debug session")
            return
            
        if not self.project_data["mods_dir"]:
            messagebox.showerror("Error", "No mod folder selected")
            return
        
        if self.project_file_path:
            self._save_to_file(self.project_file_path)
        else:
            self.save_project_as()
    
    def save_project_as(self):
        if self.active_scan:
            messagebox.showerror("Error", "Cannot save project during an active debug session")
            return
            
        if not self.project_data["mods_dir"]:
            messagebox.showerror("Error", "No mod folder selected")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")]
        )
        
        if file_path:
            self._save_to_file(file_path)
            self.project_file_path = file_path
            self.save_as_btn.configure(state="normal", fg_color=["#3B8ED0", "#1F6AA5"])
    
    def _save_to_file(self, file_path):
        save_data = self.project_data.copy()
        save_data["saved_new_mods"] = self.saved_new_mods
        with open(file_path, 'w') as f:
            json.dump(save_data, f, indent=2)
        self.project_modified = False
        self.log(f"Project saved to {Path(file_path).name}", "SUCCESS")
            
    def load_project(self):
        if self.active_scan:
            messagebox.showwarning("Active Scan", "Cannot load project during active scan")
            return
            
        file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        
        if file_path:
            with open(file_path, 'r') as f:
                self.project_data = json.load(f)
            
            self.project_file_path = file_path
            self.project_modified = False
            self.save_as_btn.configure(state="normal", fg_color=["#3B8ED0", "#1F6AA5"])
            
            if self.project_data.get("mods_dir"):
                self.folder_label.configure(text=self.project_data["mods_dir"])
            
            if self.project_data.get("theme"):
                ctk.set_appearance_mode(self.project_data["theme"])
            
            self.saved_new_mods = self.project_data.get("saved_new_mods", [])
            if self.saved_new_mods:
                self.access_saved_btn.configure(state="normal", fg_color=["#3B8ED0", "#1F6AA5"])
            else:
                self.access_saved_btn.configure(state="disabled", fg_color="gray")
            
            self.update_hanging_libraries()
            self.log(f"Project loaded from {Path(file_path).name}", "SUCCESS")
    
    def on_closing(self):
        if self.project_modified:
            response = messagebox.askyesnocancel(
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?"
            )
            if response is None:  # Cancel
                return
            elif response:  # Yes
                self.save_project()
        self.destroy()

    def modrinth_sync(self, dep_frame):
        try:
            if not self.project_data["mods_dir"]:
                self.log("Error: Please select a mod folder first", "ERROR")
                return
                
            mods_dir = Path(self.project_data["mods_dir"])
            if not mods_dir.exists():
                self.log("Error: Mod folder does not exist", "ERROR")
                return
                
            jar_files = [f.name for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar"]
            total_files = len(jar_files)
            if total_files == 0:
                self.log("No .jar files found in the mods folder.", "WARNING")
                return
                
            self.log(f"Starting Modrinth dependency sync for {total_files} mods...", "INFO")
            
            # 1. Calculate hashes for all current mods
            mod_hashes = {}
            for i, jar_file in enumerate(jar_files):
                if self.sync_cancelled: return
                file_path = mods_dir / jar_file
                file_hash = _get_sha1_hash(file_path)
                if file_hash:
                    mod_hashes[jar_file] = file_hash
                
                self.log(f"Hashing mods... ({i + 1}/{total_files})", "PROGRESS")
                
            # 2. Build map of all current mod hashes
            hash_to_filename = {v: k for k, v in mod_hashes.items()}
            
            new_dependencies_count = 0
            
            # 3. Iterate over mods to find their dependencies
            for i, (jar_file, file_hash) in enumerate(mod_hashes.items()):
                if self.sync_cancelled: return
                self.log(f"Syncing... ({i + 1}/{total_files})", "PROGRESS")
                
                mod_info = _get_mod_info(file_hash)
                
                if not mod_info:
                    self.log(f"API failed or mod not found for {jar_file}. Skipping.", "WARNING")
                    continue

                dependencies = mod_info.get('dependencies', [])

                if not dependencies:
                    continue

                found_dependencies = []
                
                # Use a set to prevent checking the same project multiple times
                projects_to_check = set(d.get('project_id') for d in dependencies if d.get('project_id'))

                for project_id in projects_to_check:
                    if self.sync_cancelled: return
                    project_versions = _get_project_versions(project_id)
                    
                    if project_versions:
                        for version in project_versions:
                            for file_info in version.get('files', []):
                                dependency_hash = file_info.get('hashes', {}).get('sha1')
                                # Check if the dependency's file is one of the mods currently in the folder
                                if dependency_hash in hash_to_filename:
                                    found_dependencies.append(hash_to_filename[dependency_hash])
                                    break 
                            if hash_to_filename.get(dependency_hash):
                                 break

                if found_dependencies:
                    # Add only new, unique dependencies
                    current_deps = set(self.project_data["dependencies"].get(jar_file, []))
                    new_deps = set(found_dependencies)
                    
                    if new_deps - current_deps:
                        self.project_data["dependencies"][jar_file] = sorted(list(current_deps | new_deps))
                        self.mark_modified()
                        new_dependencies_count += 1
                        self.log(f"Added dependencies for {jar_file}: {', '.join(list(new_deps - current_deps))}", "SUCCESS")
                    else:
                        self.log(f"Dependencies for {jar_file} already tracked.", "INFO")

            if self.sync_cancelled: return

            # 4. Final steps
            self.update_hanging_libraries()
            
            if new_dependencies_count > 0:
                self.log(f"Modrinth Sync complete: Added {new_dependencies_count} dependency rule(s).", "SUCCESS")
            else:
                self.log("Modrinth Sync complete: No new dependencies were added.", "INFO")
        except Exception as e:
            self.log(f"An unexpected error occurred during sync: {e}", "ERROR")
            
    def select_mod_folder(self):
        folder = filedialog.askdirectory(title="Select Mod Folder")
        if folder:
            self.project_data["mods_dir"] = folder
            self.folder_label.configure(text=folder)
            self.mark_modified()
            self.log(f"Mod folder set: {folder}", "SUCCESS")
            
    def create_snapshot(self):
        if not self.project_data["mods_dir"]:
            messagebox.showerror("Error", "Please select a mod folder first")
            return
            
        mods_dir = Path(self.project_data["mods_dir"])
        if not mods_dir.exists():
            messagebox.showerror("Error", "Mod folder does not exist")
            return
            
        mod_files = [f.name for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar"]
        snapshot_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.project_data["latest_snapshot"] = {
            "name": snapshot_name,
            "mods": mod_files
        }
        
        self.mark_modified()
        self.log(f"Snapshot created: {snapshot_name} ({len(mod_files)} mods)", "SUCCESS")
        
    def detect_new_mods(self):
        if not self.project_data["mods_dir"]:
            messagebox.showerror("Error", "Please select a mod folder first")
            return
            
        if not self.project_data.get("latest_snapshot"):
            messagebox.showerror("Error", "No snapshot available. Create a snapshot first.")
            return
            
        mods_dir = Path(self.project_data["mods_dir"])
        current_mods = set(f.name for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar")
        
        # Clean up self.saved_new_mods list based on current mods folder content
        if self.saved_new_mods:
            original_count = len(self.saved_new_mods)
            self.saved_new_mods = [mod for mod in self.saved_new_mods if mod in current_mods]
            
            if len(self.saved_new_mods) < original_count:
                removed_count = original_count - len(self.saved_new_mods)
                self.log(f"Removed {removed_count} deleted mod(s) from 'saved new mods' list.", "INFO")
                self.mark_modified()

        snapshot_mods = set(self.project_data["latest_snapshot"]["mods"])
        
        deleted_mods = snapshot_mods - current_mods
        
        if deleted_mods:
            self.log(f"Detected {len(deleted_mods)} deleted mod(s). Updating snapshot to reflect changes...", "INFO")
            
            snapshot_list = self.project_data["latest_snapshot"]["mods"]
            self.project_data["latest_snapshot"]["mods"] = [mod for mod in snapshot_list if mod not in deleted_mods]
            
            self.mark_modified()
            # Refresh the local set of snapshot mods for new mod calculation
            snapshot_mods = set(self.project_data["latest_snapshot"]["mods"])

        new_mods = current_mods - snapshot_mods
        
        self.update_hanging_libraries()
        
        # MESSAGING LOGIC
        
        # Case 1: No changes at all
        if not new_mods and not deleted_mods:
            messagebox.showinfo("Detection Result", "No new mods detected since last snapshot")
            self.detected_new_mods = []
            return

        # Case 2: Only deletions occurred
        if not new_mods and deleted_mods:
            messagebox.showinfo("Detection Result", f"{len(deleted_mods)} mod(s) were removed from the snapshot. No new mods were detected.")
            self.detected_new_mods = []
            return

        # Case 3: Additions and deletions occured
        if new_mods and deleted_mods:
            self.log(f"Detected {len(new_mods)} new mods since last snapshot", "SUCCESS")
            self.log(f"{len(deleted_mods)} mod(s) were removed from the snapshot.", "SUCCESS")
            
            self.detected_new_mods = list(new_mods)
            # The dialog proceeds, showing the user the newly added mods for action.
            self.show_new_mods_options_dialog(list(new_mods))

        # Case 4: Additions occurred but not deletions
        if new_mods:
            self.log(f"Detected {len(new_mods)} new mods since last snapshot", "SUCCESS")
            
            self.detected_new_mods = list(new_mods)
            # The dialog proceeds, showing the user the newly added mods for action.
            self.show_new_mods_options_dialog(list(new_mods))
        
    def manage_dependencies(self):
        dep_window = ctk.CTkToplevel(self)
        dep_window.title("Dependency Manager")
        dep_window.geometry("750x550")
        dep_window.grab_set()

        ctk.CTkLabel(dep_window, text="Mod Dependency Manager",
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 10))

        dep_frame = ctk.CTkScrollableFrame(dep_window, height=300)
        dep_frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.refresh_dependency_list(dep_frame)

        add_frame = ctk.CTkFrame(dep_window)
        add_frame.pack(fill="x", padx=20, pady=10)

        btn_row = ctk.CTkFrame(add_frame, fg_color="transparent")
        btn_row.pack(pady=10)
        
        sync_status_frame = ctk.CTkFrame(dep_window, fg_color="transparent")
        sync_status_frame.pack(fill="x", padx=20, pady=5)

        modrinth_btn = ctk.CTkButton(btn_row, text="🔄 Modrinth Sync", fg_color="green")
        add_btn = ctk.CTkButton(btn_row, text="➕ Add Dependency",
                     command=lambda: self.add_dependency_dialog(dep_window, dep_frame))
        delete_all_btn = ctk.CTkButton(btn_row, text="🗑️ Delete All",
                     command=lambda: self.delete_all_dependencies(dep_frame),
                     fg_color="darkred")

        modrinth_btn.pack(side="left", padx=5)
        add_btn.pack(side="left", padx=5)
        delete_all_btn.pack(side="left", padx=5)
        
        controls = [modrinth_btn, add_btn, delete_all_btn]
        modrinth_btn.configure(command=lambda: self.run_sync_operation(
            dep_window, dep_frame, controls, sync_status_frame
        ))
        
    def cancel_sync(self):
        self.sync_cancelled = True
        self.log("Sync cancellation requested...", "WARNING")

    def run_sync_operation(self, window, dep_frame, controls, status_frame):
        # UI Setup
        for control in controls:
            control.configure(state="disabled")
        controls[0].configure(text="Syncing...")
        
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        
        for widget in status_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(status_frame, text="Syncing Dependencies with Modrinth...").pack(side="left", expand=True, padx=10)
        ctk.CTkButton(status_frame, text="Cancel Sync", fg_color="darkred", command=self.cancel_sync).pack(side="right", padx=10)
        
        # Threading
        self.sync_cancelled = False
        self.sync_thread = threading.Thread(target=self.modrinth_sync, args=(dep_frame,), daemon=True)
        self.sync_thread.start()
        
        # Monitor Thread
        self.monitor_sync_thread(window, dep_frame, controls, status_frame)

    def monitor_sync_thread(self, window, dep_frame, controls, status_frame):
        if self.sync_thread.is_alive():
            self.after(100, lambda: self.monitor_sync_thread(window, dep_frame, controls, status_frame))
        else:
            # UI Cleanup
            for control in controls:
                control.configure(state="normal")
            controls[0].configure(text="🔄 Modrinth Sync")
            
            for widget in status_frame.winfo_children():
                widget.destroy()
            
            window.protocol("WM_DELETE_WINDOW", window.destroy)
            
            self.refresh_dependency_list(dep_frame)
            if self.sync_cancelled:
                self.log("Sync process terminated by user.", "WARNING")
            else:
                self.log("Sync process finished.", "INFO")

    def refresh_dependency_list(self, parent):
        for widget in parent.winfo_children():
            widget.destroy()
            
        if not self.project_data["dependencies"]:
            ctk.CTkLabel(parent, text="No dependencies defined", 
                        text_color="gray").pack(pady=20)
            return
            
        for mod, deps in self.project_data["dependencies"].items():
            dep_item = ctk.CTkFrame(parent)
            dep_item.pack(fill="x", pady=5, padx=5)
            
            text_frame = ctk.CTkFrame(dep_item, fg_color="transparent")
            text_frame.pack(side="left", fill="x", expand=True, padx=10, pady=5)
            
            ctk.CTkLabel(text_frame, text=f"🔗 {mod}", 
                        font=ctk.CTkFont(weight="bold"), anchor="w").pack(fill="x")
            ctk.CTkLabel(text_frame, text=f"→ {', '.join(deps)}", 
                        text_color="gray", anchor="w").pack(fill="x")
            
            ctk.CTkButton(dep_item, text="❌", width=40, height=40,
                         command=lambda m=mod: self.remove_dependency(m, parent)).pack(side="right", padx=5)
    
    def delete_all_dependencies(self, refresh_frame):
        if not self.project_data["dependencies"]:
            messagebox.showinfo("Info", "No dependencies to delete")
            return
        
        response = messagebox.askyesno(
            "Confirm Delete All",
            "Are you sure you want to delete ALL dependency rules?\nThis action cannot be undone."
        )
        
        if response:
            self.project_data["dependencies"].clear()
            self.mark_modified()
            self.refresh_dependency_list(refresh_frame)
            self.update_hanging_libraries()
            self.log("All dependencies deleted", "WARNING")
            
    def add_dependency_dialog(self, parent_window, refresh_frame):
        if not self.project_data["mods_dir"]:
            messagebox.showerror("Error", "Please select a mod folder first")
            return
            
        mods_dir = Path(self.project_data["mods_dir"])
        available_mods = sorted([f.name for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar"])
        
        dialog = ctk.CTkToplevel(parent_window)
        dialog.title("Add Dependency")
        dialog.geometry("650x864")
        dialog.grab_set()
        
        # Multiple selection checkbox
        multi_var = ctk.BooleanVar(value=False)
        
        ctk.CTkLabel(dialog, text="Select Main Mod(s):", 
                    font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(15, 5))
        
        multi_check = ctk.CTkCheckBox(dialog, text="Select Multiple Main Mods", 
                                      variable=multi_var, command=lambda: toggle_selection_mode())
        multi_check.pack(pady=5)
        
        main_search_var = ctk.StringVar()
        main_search_var.trace("w", lambda *args: filter_main_mods())
        
        ctk.CTkEntry(dialog, textvariable=main_search_var, 
                    placeholder_text="🔍 Search main mod...").pack(fill="x", padx=20, pady=5)
        
        select_btns_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        select_btns_frame.pack(pady=2)

        select_all_btn = ctk.CTkButton(select_btns_frame, text="Select All", height=25,
                                       command=lambda: select_all_main_mods(), state="disabled")
        select_all_btn.pack(side="left", padx=5)

        select_none_btn = ctk.CTkButton(select_btns_frame, text="Select None", height=25,
                                        command=lambda: select_none_main_mods(), state="disabled")
        select_none_btn.pack(side="left", padx=5)
        
        main_frame = ctk.CTkScrollableFrame(dialog, height=100)
        main_frame.pack(fill="x", padx=20, pady=5)
        
        main_mod_var = ctk.StringVar()
        main_check_vars = {}
        main_widgets = []
        
        def toggle_selection_mode():
            filter_main_mods()
            if multi_var.get():
                select_all_btn.configure(state="normal")
                select_none_btn.configure(state="normal")
            else:
                select_all_btn.configure(state="disabled")
                select_none_btn.configure(state="disabled")
        
        def select_all_main_mods():
            for var in main_check_vars.values():
                var.set(True)

        def select_none_main_mods():
            for var in main_check_vars.values():
                var.set(False)
        
        def filter_main_mods():
            search_term = main_search_var.get().lower()
            for widget in main_frame.winfo_children():
                widget.destroy()
            main_widgets.clear()
            
            filtered_mods = [m for m in available_mods if search_term in m.lower()]
            
            if multi_var.get():
                for mod in filtered_mods:
                    if mod not in main_check_vars:
                        main_check_vars[mod] = ctk.BooleanVar()
                    cb = ctk.CTkCheckBox(main_frame, text=mod, variable=main_check_vars[mod])
                    cb.pack(anchor="w", pady=2)
                    main_widgets.append(cb)
            else:
                for mod in filtered_mods:
                    rb = ctk.CTkRadioButton(main_frame, text=mod, variable=main_mod_var, value=mod)
                    rb.pack(anchor="w", pady=2)
                    main_widgets.append(rb)
        
        filter_main_mods()
        
        # Dependencies section
        ctk.CTkLabel(dialog, text="Select Dependencies:", 
                    font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(15, 5))
        
        dep_search_var = ctk.StringVar()
        dep_search_var.trace("w", lambda *args: filter_dependencies())
        
        ctk.CTkEntry(dialog, textvariable=dep_search_var, 
                    placeholder_text="🔍 Search dependencies...").pack(fill="x", padx=20, pady=5)
        
        dep_frame = ctk.CTkScrollableFrame(dialog, height=250)
        dep_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        dep_vars = {}
        dep_checkboxes = []
        
        def filter_dependencies():
            search_term = dep_search_var.get().lower()
            for widget in dep_frame.winfo_children():
                widget.destroy()
            dep_checkboxes.clear()
            
            filtered_mods = [m for m in available_mods if search_term in m.lower()]
            for mod in filtered_mods:
                if mod not in dep_vars:
                    dep_vars[mod] = ctk.BooleanVar()
                cb = ctk.CTkCheckBox(dep_frame, text=mod, variable=dep_vars[mod])
                cb.pack(anchor="w", pady=2)
                dep_checkboxes.append(cb)
        
        filter_dependencies()
        
        def save_dependency():
            deps = [mod for mod, var in dep_vars.items() if var.get()]
            
            if not deps:
                messagebox.showerror("Error", "Please select at least one dependency")
                return
            
            if multi_var.get():
                main_mods = [mod for mod, var in main_check_vars.items() if var.get()]
                if not main_mods:
                    messagebox.showerror("Error", "Please select at least one main mod")
                    return
                
                for main in main_mods:
                    self.project_data["dependencies"][main] = deps
                
                self.log(f"Dependencies added for {len(main_mods)} mods", "SUCCESS")
            else:
                main = main_mod_var.get()
                if not main:
                    messagebox.showerror("Error", "Please select a main mod")
                    return
                
                self.project_data["dependencies"][main] = deps
                self.log(f"Dependency added: {main} → {', '.join(deps)}", "SUCCESS")
            
            self.mark_modified()
            self.refresh_dependency_list(refresh_frame)
            self.update_hanging_libraries()
            dialog.destroy()
        
        ctk.CTkButton(dialog, text="💾 Save Dependency", 
                     command=save_dependency, height=40).pack(pady=15)
        
    def remove_dependency(self, mod, refresh_frame):
        if mod in self.project_data["dependencies"]:
            del self.project_data["dependencies"][mod]
            self.mark_modified()
            self.refresh_dependency_list(refresh_frame)
            self.update_hanging_libraries()
            self.log(f"Dependency removed: {mod}", "SUCCESS")
    
    def update_hanging_libraries(self):
        """Update the list of hanging libraries"""
        if not self.project_data["mods_dir"] or not self.project_data.get("latest_snapshot"):
            return
        
        mods_dir = Path(self.project_data["mods_dir"])
        current_mods = set(f.name for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar")
        
        all_needed_deps = set()
        
        # Collect all dependencies still needed by existing mods
        for mod, deps in self.project_data["dependencies"].items():
            if mod in current_mods:
                all_needed_deps.update(deps)
        
        # Find hanging dependencies (dependencies without their main mod)
        hanging = []
        for mod, deps in self.project_data["dependencies"].items():
            if mod not in current_mods:
                for dep in deps:
                    if dep not in all_needed_deps and dep in current_mods:
                        hanging.append(dep)
        
        self.hanging_libraries = list(set(hanging))
        
        if self.hanging_libraries:
            self.hanging_libs_btn.configure(fg_color=["#DAA520", "#B8860B"])
            messagebox.showinfo("Hanging Libraries Detected!", 
                              f"Found {len(self.hanging_libraries)} hanging library mod(s).\n\nClick the 'Hanging Libraries' button to manage them.")
        else:
            self.hanging_libs_btn.configure(fg_color="gray")
    
    def show_hanging_libraries(self):
        """Show dialog to manage hanging libraries"""
        if not self.hanging_libraries:
            messagebox.showinfo("No Hanging Libraries", "No hanging library mods detected.")
            return
        
        dialog = ctk.CTkToplevel(self)
        dialog.title("Hanging Libraries Manager")
        dialog.geometry("600x500")
        dialog.grab_set()
        
        ctk.CTkLabel(dialog, text="⚠️ Hanging Library Mods", 
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=20)
        
        ctk.CTkLabel(dialog, text="These libraries have no main mod using them:", 
                    font=ctk.CTkFont(size=12)).pack(pady=5)
        
        list_frame = ctk.CTkScrollableFrame(dialog, height=280)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        lib_vars = {}
        for lib in self.hanging_libraries:
            var = ctk.BooleanVar(value=True)
            lib_vars[lib] = var
            ctk.CTkCheckBox(list_frame, text=lib, variable=var).pack(anchor="w", pady=3)
        
        def delete_selected():
            to_delete = [lib for lib, var in lib_vars.items() if var.get()]
            
            if not to_delete:
                messagebox.showinfo("Info", "No libraries selected for deletion")
                return
            
            response = messagebox.askyesno(
                "Confirm Deletion",
                f"Delete {len(to_delete)} hanging library mod(s)?\nThis will permanently remove them from your mods folder."
            )
            
            if response:
                mods_dir = Path(self.project_data["mods_dir"])
                for lib in to_delete:
                    lib_path = mods_dir / lib
                    if lib_path.exists():
                        lib_path.unlink()
                        self.log(f"Deleted hanging library: {lib}", "WARNING")
                
                self.update_hanging_libraries()
                self.mark_modified()
                dialog.destroy()
                
                if self.hanging_libraries:
                    self.show_hanging_libraries()
        
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        ctk.CTkButton(btn_frame, text="🗑️ Delete Selected", 
                     command=delete_selected, width=150,
                     fg_color="darkred").pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="Cancel", 
                     command=dialog.destroy, width=150).pack(side="left", padx=10)
    
    def show_new_mods_options_dialog(self, new_mods):
        """Show dialog with options for handling detected new mods"""
        dialog = ctk.CTkToplevel(self)
        dialog.title("New Mods Detected")
        dialog.geometry("500x400")
        dialog.grab_set()
        
        ctk.CTkLabel(dialog, text=f"🎉 {len(new_mods)} New Mods Detected", 
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=20)
        
        # Show list of new mods
        list_frame = ctk.CTkScrollableFrame(dialog, height=180)
        list_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        for mod in new_mods:
            ctk.CTkLabel(list_frame, text=f"• {mod}", anchor="w").pack(fill="x", pady=2)
        
        ctk.CTkLabel(dialog, text="What would you like to do?", 
                    font=ctk.CTkFont(size=14)).pack(pady=10)
        
        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        
        def save_and_snapshot():
            self.saved_new_mods = new_mods
            self.mark_modified()  # Mark as modified since saved_new_mods changed
            self.create_snapshot()
            self.access_saved_btn.configure(state="normal", fg_color=["#3B8ED0", "#1F6AA5"])
            self.log(f"Saved {len(new_mods)} new mods for later", "SUCCESS")
            dialog.destroy()
        
        def start_debug_now():
            self.saved_new_mods = new_mods
            self.mark_modified()
            self.create_snapshot()
            self.access_saved_btn.configure(state="normal", fg_color=["#3B8ED0", "#1F6AA5"])
            dialog.destroy()
            self.show_mod_selection_dialog(new_mods, "Select New Mods to Debug")
        
        ctk.CTkButton(btn_frame, text="💾 Save for Later & Snapshot", 
                     command=save_and_snapshot, width=220).pack(pady=5)
        ctk.CTkButton(btn_frame, text="🚀 Start Debug & Snapshot", 
                     command=start_debug_now, width=220).pack(pady=5)
    
    def access_saved_new_mods(self):
        """Access previously saved new mods"""
        if not self.saved_new_mods:
            messagebox.showinfo("Info", "No saved new mods available")
            return
        
        self.show_mod_selection_dialog(self.saved_new_mods, "Saved New Mods")
            
    def show_mod_selection_dialog(self, mods, title):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("600x500")
        dialog.grab_set()
        
        ctk.CTkLabel(dialog, text=f"{title} ({len(mods)} mods)", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=20)
        
        scroll_frame = ctk.CTkScrollableFrame(dialog, height=350)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        mod_vars = {}
        for mod in mods:
            var = ctk.BooleanVar(value=True)
            mod_vars[mod] = var
            ctk.CTkCheckBox(scroll_frame, text=mod, variable=var).pack(anchor="w", pady=3)
        
        def start_with_selection():
            selected = [mod for mod, var in mod_vars.items() if var.get()]
            if not selected:
                messagebox.showerror("Error", "Please select at least one mod")
                return
            dialog.destroy()
            threading.Thread(target=self.run_debug_scan, args=(selected,), daemon=True).start()
        
        ctk.CTkButton(dialog, text="Start Debug with Selected Mods", 
                     command=start_with_selection).pack(pady=10)
        
    def start_debug(self):
        if not self.project_data["mods_dir"]:
            messagebox.showerror("Error", "Please select a mod folder first")
            return
            
        mods_dir = Path(self.project_data["mods_dir"])
        if not mods_dir.exists():
            messagebox.showerror("Error", "Mod folder does not exist")
            return
            
        if self.mode_var.get() == "all":
            all_mods = [f.name for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar"]
            if len(all_mods) < 2:
                messagebox.showerror("Error", "Need at least 2 mods to start a debug session")
                return
            threading.Thread(target=self.run_debug_scan, args=(all_mods,), daemon=True).start()
        else:
            if not self.saved_new_mods:
                messagebox.showerror("Error", "No saved new mods available. Please use 'Detect New Mods' first or switch to Mode 1.")
                return
            if len(self.saved_new_mods) < 2:
                messagebox.showerror("Error", "Need at least 2 new mods to start a debug session")
                return
            self.show_mod_selection_dialog(self.saved_new_mods, "Select New Mods to Debug")
            
    def run_debug_scan(self, mods_to_test):
        self.active_scan = True
        self.scan_cancelled = False
        self.start_btn.configure(state="disabled")
        
        self.log(f"Starting debug scan with {len(mods_to_test)} mods...", "INFO")
        
        self.temp_dir.mkdir(exist_ok=True)
        mods_dir = Path(self.project_data["mods_dir"])
        
        # Move mods to temp
        self.log("Preparing... (moving mods to temp directory)", "INFO")
        total_mods = len(mods_to_test)
        for i, mod in enumerate(mods_to_test):
            if self.scan_cancelled: break
            src = mods_dir / mod
            dest = self.temp_dir / mod
            if src.exists():
                shutil.move(str(src), str(dest))
            
            # Update progress for every mod
            self.log(f"Moving... ({i + 1}/{total_mods})", "PROGRESS")
        
        if not self.scan_cancelled:
            self.log("Preparation complete.", "SUCCESS")
            self.current_test_group = mods_to_test
            culprit = self.binary_search(mods_to_test)
        else:
            culprit = None

        # Restore all mods
        self.log("Restoring all mods...", "INFO")
        for i, mod in enumerate(mods_to_test):
            src = self.temp_dir / mod
            dest = mods_dir / mod
            if src.exists():
                shutil.move(str(src), str(dest))
            
            # Update progress for every mod
            self.log(f"Restoring... ({i + 1}/{total_mods})", "PROGRESS")
        
        self.active_scan = False
        self.start_btn.configure(state="normal")
        
        if self.scan_cancelled:
            self.log("Debug scan cancelled - all mods restored.", "WARNING")
        elif culprit:
            self.log(f"CULPRIT IDENTIFIED: {culprit}", "ERROR")
            messagebox.showinfo("Debug Complete", f"Problematic mod found:\n\n{culprit}\n\nAll mods have been restored.")
        else:
            self.log("No single culprit identified. All mods restored.", "WARNING")
            
    def binary_search(self, mods):
        current_group = mods[:]
        fallback_level = 1
        
        while len(current_group) > fallback_level and not self.scan_cancelled:
            mid = len(current_group) // 2
            
            self.log("Splitting mods and resolving dependencies...", "INFO")
            group_a, group_b = self.split_with_dependencies(current_group, mid)
            self.log("Dependency resolution complete.", "SUCCESS")
            
            self.log(f"Testing Group A ({len(group_a)} mods)...", "INFO")
            
            test_result = self.test_group(group_a)
            
            if test_result is None:
                return None
            
            if test_result:
                self.log("Group A passed - focusing on Group B", "SUCCESS")
                current_group = group_b
            else:
                self.log("Group A failed - focusing on Group A", "ERROR")
                current_group = group_a
        
        if self.scan_cancelled:
            return None
            
        if len(current_group) == 1:
            mod = current_group[0]
            if mod in self.project_data["dependencies"]:
                deps = self.project_data["dependencies"][mod]
                self.log(f"Testing mod with dependencies: {mod}", "INFO")
                
                res1 = self.test_group([mod])
                if res1 is None: return None
                if not res1: return mod
                
                res2 = self.test_group(deps)
                if res2 is None: return None
                if not res2: return f"{mod} (dependencies: {', '.join(deps)})"
            else:
                res = self.test_group([mod])
                if res is None: return None
                if not res: return mod
        
        if len(current_group) >= 2 and fallback_level == 1:
            self.log("Unable to isolate single mod. Falling back to 2-mod resolution...", "WARNING")
            messagebox.showwarning("Debug Fallback", "Unable to isolate a single problematic mod.\n\nFalling back to identify 2 problematic mods.")
            return self.binary_search_fallback(mods, 2)
        
        return None
    
    def binary_search_fallback(self, mods, target_count):
        """Fallback binary search that tries to isolate target_count mods"""
        if len(mods) <= target_count:
            self.log(f"Cannot perform {target_count}-mod fallback with only {len(mods)} mods", "ERROR")
            if target_count == 2 and len(mods) > 2 and not self.scan_cancelled:
                self.log("Falling back to 3-mod resolution...", "WARNING")
                messagebox.showwarning("Debug Fallback", "Unable to isolate 2 problematic mods.\n\nFalling back to identify 3 problematic mods.")
                return self.binary_search_fallback(mods, 3)
            return None
        
        current_group = mods[:]
        
        while len(current_group) > target_count and not self.scan_cancelled:
            mid = len(current_group) // 2
            group_a, group_b = self.split_with_dependencies(current_group, mid)
            
            self.log(f"Testing Group A ({len(group_a)} mods) - Target: {target_count} mods...", "INFO")
            
            test_result = self.test_group(group_a)

            # If test_group returns None, it means the user cancelled. Exit immediately.
            if test_result is None:
                return None

            if test_result:
                self.log("Group A passed - focusing on Group B", "SUCCESS")
                current_group = group_b
            else:
                self.log("Group A failed - focusing on Group A", "ERROR")
                current_group = group_a
        
        if self.scan_cancelled:
            return None

        if len(current_group) == target_count:
            test_result = self.test_group(current_group)
            if test_result is None: return None
            if not test_result:
                return f"Problematic group ({target_count} mods): {', '.join(current_group)}"
        
        # Further fallback
        if target_count == 2 and len(mods) > 3 and not self.scan_cancelled:
            self.log("Unable to isolate 2 mods. Falling back to 3-mod resolution...", "WARNING")
            messagebox.showwarning("Debug Fallback", "Unable to isolate 2 problematic mods.\n\nFalling back to identify 3 problematic mods.")
            return self.binary_search_fallback(mods, 3)
        elif target_count == 3:
            self.log("Debug session failed - unable to isolate problematic mods", "ERROR")
            messagebox.showerror("Debug Failed", "Unable to isolate problematic mods even with fallback methods.\n\nThe issue may be more complex than a simple mod conflict.")
        
        return None
        
    def split_with_dependencies(self, mods, split_point):
        set_a = set(mods[:split_point])
        set_b = set(mods[split_point:])
        
        pass_count = 0
        while True:
            pass_count += 1
            self.log(f"Resolving dependencies... Pass {pass_count}", "PROGRESS")

            # Create sets of mods that need to be moved in this pass
            to_move_to_a = set()
            to_move_to_b = set()

            # Check Group A's mods for dependencies that are in Group B
            for mod in set_a:
                if mod in self.project_data["dependencies"]:
                    for dep in self.project_data["dependencies"][mod]:
                        if dep in set_b:
                            to_move_to_a.add(dep)

            # Check Group B's mods for dependencies that are in Group A
            for mod in set_b:
                if mod in self.project_data["dependencies"]:
                    for dep in self.project_data["dependencies"][mod]:
                        if dep in set_a:
                            to_move_to_b.add(dep)
            
            # If no mods need to be moved, the groups are stable and we can exit
            if not to_move_to_a and not to_move_to_b:
                break
            
            # Perform the moves using efficient set operations
            set_a.update(to_move_to_a)
            set_b.difference_update(to_move_to_a)
            
            set_b.update(to_move_to_b)
            set_a.difference_update(to_move_to_b)
            
            # Failsafe to prevent infinite loops in case of circular dependencies
            if pass_count > len(mods):
                self.log("Potential circular dependency detected or complex split. Breaking resolution.", "WARNING")
                break
        
        return list(set_a), list(set_b)
        
    def test_group(self, mods):
        mods_dir = Path(self.project_data["mods_dir"])
        
        # Clear mods folder
        for mod in self.current_test_group:
            mod_path = mods_dir / mod
            if mod_path.exists():
                shutil.move(str(mod_path), str(self.temp_dir / mod))
        
        # Move test mods in
        for mod in mods:
            src = self.temp_dir / mod
            dest = mods_dir / mod
            if src.exists():
                shutil.move(str(src), str(dest))
        
        # Wait for user input
        result = self.wait_for_test_result(len(mods))
        
        return result
        
    def wait_for_test_result(self, mod_count):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Test Launch")
        dialog.geometry("500x300")
        dialog.grab_set()
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        
        ctk.CTkLabel(dialog, text=f"Testing {mod_count} mods", 
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=20)
        ctk.CTkLabel(dialog, text="Launch Minecraft now and test if it loads", 
                    font=ctk.CTkFont(size=14)).pack(pady=10)
        
        result = {"success": None}
        
        def set_result(success):
            result["success"] = success
            dialog.destroy()
            
        def do_cancel():
            if messagebox.askyesno("Cancel Debug", "Are you sure you want to cancel the debug process?"):
                self.scan_cancelled = True
                self.log("Cancelling debug scan...", "WARNING")
                dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=30)
        
        ctk.CTkButton(btn_frame, text="✅ Game Worked", width=150, height=50,
                     command=lambda: set_result(True),
                     font=ctk.CTkFont(size=14)).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="❌ Game Crashed", width=150, height=50,
                     command=lambda: set_result(False),
                     font=ctk.CTkFont(size=14)).pack(side="left", padx=10)

        ctk.CTkButton(dialog, text="Cancel Debug", width=150, height=35,
                     command=do_cancel, fg_color="darkred").pack(pady=(10, 0))
        
        self.wait_window(dialog)
        return result["success"]

if __name__ == "__main__":
    app = ModpackDebuggerKit()
    app.mainloop()
