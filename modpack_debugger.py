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
        # Clean up temp dir on exit just in case
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
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
        if self.active_scan:
            messagebox.showerror("Error", "A debug session is already in progress.")
            return

        if not self.project_data["mods_dir"]:
            messagebox.showerror("Error", "Please select a mod folder first")
            return
            
        mods_dir = Path(self.project_data["mods_dir"])
        if not mods_dir.exists():
            messagebox.showerror("Error", "Mod folder does not exist")
            return
            
        if self.mode_var.get() == "all":
            all_mods = [f.name for f in mods_dir.iterdir() if f.is_file() and f.suffix == ".jar"]
            if len(all_mods) < 1:
                messagebox.showerror("Error", "Need at least 1 mod to start a debug session")
                return
            threading.Thread(target=self.run_debug_scan, args=(all_mods,), daemon=True).start()
        else:
            if not self.saved_new_mods:
                messagebox.showerror("Error", "No saved new mods available. Please use 'Detect New Mods' first or switch to Mode 1.")
                return
            self.show_mod_selection_dialog(self.saved_new_mods, "Select New Mods to Debug")

    def _get_primary_mods_and_group_map(self, all_mods):
        """
        Analyzes dependencies to find "primary" mods and maps each to its full dependency group.
        A primary mod is one that is not solely a dependency for another mod in the set.
        This allows the binary search to work on interactions between mods.
        """
        all_mods_set = set(all_mods)
        all_dependencies_in_set = set()
        
        # First, find all mods that are listed as a dependency for at least one other mod
        for mod in all_mods:
            deps = self.project_data["dependencies"].get(mod, [])
            for dep in deps:
                if dep in all_mods_set:
                    all_dependencies_in_set.add(dep)
        
        # Primary mods are those in the test set that are NOT in the dependency list
        primary_mods = sorted([mod for mod in all_mods if mod not in all_dependencies_in_set])
        
        # If all mods are dependencies of each other (e.g., A needs B, B needs A),
        # or there are no primary mods, then every mod must be treated as primary.
        if not primary_mods:
            primary_mods = sorted(all_mods)
            
        group_map = {}
        for primary_mod in primary_mods:
            group = {primary_mod}
            deps_to_check = list(self.project_data["dependencies"].get(primary_mod, []))
            processed_deps = set()

            while deps_to_check:
                dep = deps_to_check.pop(0)
                if dep in processed_deps:
                    continue
                processed_deps.add(dep)
                
                if dep in all_mods_set:
                    group.add(dep)
                    # Check for nested dependencies
                    nested_deps = self.project_data["dependencies"].get(dep, [])
                    deps_to_check.extend(nested_deps)

            group_map[primary_mod] = sorted(list(group))
            
        return primary_mods, group_map
            
    def run_debug_scan(self, mods_to_test):
        self.active_scan = True
        self.scan_cancelled = False
        self.start_btn.configure(state="disabled")
        mods_dir = Path(self.project_data["mods_dir"])
        
        # Ensure temp dir is clean before starting
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        
        try:
            self.log(f"Starting debug scan with {len(mods_to_test)} mods...", "INFO")
            
            self.log("Preparing... (moving mods to temp directory)", "INFO")
            for i, mod in enumerate(mods_to_test):
                if self.scan_cancelled: break
                src = mods_dir / mod
                dest = self.temp_dir / mod
                if src.exists():
                    shutil.move(str(src), str(dest))
                self.log(f"Moving... ({i + 1}/{len(mods_to_test)})", "PROGRESS")
            
            culprit_info = None
            if not self.scan_cancelled:
                self.log("Preparation complete.", "SUCCESS")
                self.current_test_group = mods_to_test # Store the original full list for cleanup

                self.log("Analyzing mod dependencies to form testable groups...", "INFO")
                primary_mods, group_map = self._get_primary_mods_and_group_map(mods_to_test)
                self.log(f"Identified {len(primary_mods)} primary mods/groups for testing.", "SUCCESS")
                
                if not primary_mods:
                    self.log("No primary mods could be identified. Aborting scan.", "ERROR")
                else:
                    # Start search with a target of 1 primary mod/group
                    self.log("Starting debug search to isolate 1 culprit...", "INFO")
                    culprit_info = self.binary_search(primary_mods, group_map, 1)

                    # Fallback to 2 if first search fails
                    if not culprit_info and not self.scan_cancelled:
                        self.log("Unable to isolate a single culprit. Falling back to 2-culprit resolution...", "WARNING")
                        messagebox.showwarning("Debug Fallback", "Unable to isolate a single problematic mod/group.\n\nFalling back to identify an interaction between 2.")
                        culprit_info = self.binary_search(primary_mods, group_map, 2)
                    
                    # Fallback to 3 if second search fails
                    if not culprit_info and not self.scan_cancelled:
                        self.log("Unable to isolate 2 culprits. Falling back to 3-culprit resolution...", "WARNING")
                        messagebox.showwarning("Debug Fallback", "Unable to isolate a 2-mod/group interaction.\n\nFalling back to identify an interaction between 3.")
                        culprit_info = self.binary_search(primary_mods, group_map, 3)

            if self.scan_cancelled:
                 self.log("Debug scan cancelled by user.", "WARNING")
            elif culprit_info:
                self.log(f"CULPRIT(S) IDENTIFIED: {culprit_info}", "ERROR")
                messagebox.showinfo("Debug Complete", f"Problematic mod(s) found:\n\n{culprit_info}\n\nAll mods have been restored.")
            else:
                self.log("No specific culprit(s) identified.", "WARNING")
                messagebox.showerror("Debug Failed", "Unable to isolate the problematic mod(s) even with fallback methods.\nThe issue may be a complex interaction between multiple mod groups.")
        
        finally:
            # This block is GUARANTEED to run, ensuring a clean state.
            self.log("Restoring all mods and cleaning up...", "INFO")
            for mod in self.current_test_group:
                src = self.temp_dir / mod
                dest = mods_dir / mod
                if src.exists():
                    shutil.move(str(src), str(dest))
            
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)

            self.active_scan = False
            self.start_btn.configure(state="normal")
            self.log("Cleanup complete. Ready for next session.", "SUCCESS")


    def binary_search(self, primary_mods, group_map, target_count):
        current_primary_mods = primary_mods[:]

        while len(current_primary_mods) > target_count and not self.scan_cancelled:
            mid = len(current_primary_mods) // 2
            group_a_primary = current_primary_mods[:mid]
            group_b_primary = current_primary_mods[mid:]

            # Flatten the primary mods into a unique set of actual mod files for testing
            mods_to_test_in_a = set()
            for primary_mod in group_a_primary:
                mods_to_test_in_a.update(group_map[primary_mod])

            self.log(f"Testing Group A ({len(mods_to_test_in_a)} mods from {len(group_a_primary)} primary groups)...", "INFO")
            test_result = self.test_group(list(mods_to_test_in_a))
            
            if test_result is None: # User cancelled
                return None

            if test_result:
                self.log("Group A passed - focusing on Group B", "SUCCESS")
                current_primary_mods = group_b_primary
            else:
                self.log("Group A failed - focusing on Group A", "ERROR")
                current_primary_mods = group_a_primary
        
        if self.scan_cancelled:
            return None
        
        if len(current_primary_mods) > target_count:
            self.log(f"Could not isolate to {target_count} primary mod(s). Smallest set is {len(current_primary_mods)}.", "INFO")
            return None

        # Final verification
        final_mods_to_test = set()
        for primary_mod in current_primary_mods:
            final_mods_to_test.update(group_map[primary_mod])

        self.log(f"Final test on suspected culprit(s) ({len(final_mods_to_test)} mods from {len(current_primary_mods)} groups)...", "INFO")
        final_test_result = self.test_group(list(final_mods_to_test))

        if final_test_result is None: # User cancelled
            return None

        if not final_test_result: # It crashed, we found the culprit(s).
            return f"{', '.join(sorted(list(final_mods_to_test)))}"

        self.log(f"Final test passed. Could not isolate the issue.", "WARNING")
        return None
        
    def test_group(self, mods):
        mods_dir = Path(self.project_data["mods_dir"])
        
        # Clear mods dir of any files from the original test group.
        # This is safer than just clearing the previous test's mods.
        for item in mods_dir.iterdir():
            if item.is_file() and item.name in self.current_test_group:
                shutil.move(str(item), str(self.temp_dir / item.name))

        # Move current test mods in
        for mod in mods:
            src = self.temp_dir / mod
            dest = mods_dir / mod
            if src.exists():
                shutil.move(str(src), str(dest))
        
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