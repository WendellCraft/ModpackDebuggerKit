let projectModified = false;
let projectFilePath = "";
let currentTheme = "dark";
let syncActive = false;
let testDialogActive = false;

function log(message, level) {
    const area = document.getElementById("log-area");
    const entry = document.createElement("div");
    entry.className = "log-entry log-" + level;
    const timestamp = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const prefix = { INFO: "", SUCCESS: "", ERROR: "", WARNING: "", PROGRESS: "" }[level] || "";
    entry.textContent = "[" + timestamp + "] " + prefix + " " + message;
    if (level === "PROGRESS") {
        const prev = area.lastElementChild;
        if (prev && prev.classList.contains("log-PROGRESS")) {
            area.removeChild(prev);
        }
    }
    area.appendChild(entry);
    area.scrollTop = area.scrollHeight;
}

function showModal(title, bodyHtml, footerHtml) {
    const overlay = document.getElementById("modal-overlay");
    document.getElementById("modal-title").textContent = title;
    document.getElementById("modal-body").innerHTML = bodyHtml;
    document.getElementById("modal-footer").innerHTML = footerHtml || "";
    overlay.classList.remove("hidden");
    return overlay;
}

function closeModal() {
    document.getElementById("modal-overlay").classList.add("hidden");
}

document.getElementById("modal-close-btn").addEventListener("click", function() {
    if (testDialogActive) return;
    closeModal();
});
document.getElementById("modal-overlay").addEventListener("click", function(e) {
    if (e.target === this && !testDialogActive) closeModal();
});

async function showInfo(title, message) {
    showModal(title, "<p style='white-space: pre-wrap;'>" + message + "</p>",
        '<button class="btn" onclick="closeModal()">OK</button>'
    );
}

async function showError(title, message) {
    showModal(title, "<p style='white-space: pre-wrap; color: var(--log-error)'>" + message + "</p>",
        '<button class="btn" onclick="closeModal()">OK</button>'
    );
}

async function showConfirm(title, message) {
    return new Promise(function(resolve) {
        showModal(title, "<p>" + message + "</p>",
            '<button class="btn btn-danger" onclick="closeModal(); resolveConfirm(false)">No</button>' +
            '<button class="btn btn-primary" onclick="closeModal(); resolveConfirm(true)">Yes</button>'
        );
        window.resolveConfirm = resolve;
    });
}

async function showConfirmCancel(title, message) {
    return new Promise(function(resolve) {
        showModal(title, "<p>" + message + "</p>",
            '<button class="btn" onclick="closeModal(); resolveConfirmCancel(null)">Cancel</button>' +
            '<button class="btn btn-danger" onclick="closeModal(); resolveConfirmCancel(false)">No</button>' +
            '<button class="btn btn-primary" onclick="closeModal(); resolveConfirmCancel(true)">Yes</button>'
        );
        window.resolveConfirmCancel = resolve;
    });
}

async function updateUI() {
    try {
        const data = await window.go.main.App.GetProjectData();
        projectModified = await window.go.main.App.IsProjectModified();
        projectFilePath = await window.go.main.App.GetProjectFilePath();
        const theme = await window.go.main.App.GetTheme();
        const hasModsDir = !!data.mods_dir;

        document.getElementById("folder-label").textContent = data.mods_dir || "No folder selected";

        if (theme === "light") {
            document.body.classList.add("light");
        } else {
            document.body.classList.remove("light");
        }
        currentTheme = theme;

        var folderBtns = [
            "create-snapshot-btn",
            "detect-new-mods-btn",
            "hanging-libs-btn",
            "manage-deps-btn",
        ];
        folderBtns.forEach(function(id) {
            document.getElementById(id).disabled = !hasModsDir;
        });

        const savedMods = data.saved_new_mods || [];
        const savedBtn = document.getElementById("access-saved-btn");
        savedBtn.disabled = !hasModsDir || savedMods.length === 0;

        document.getElementById("save-project-btn").disabled = !hasModsDir;
        document.getElementById("save-as-btn").disabled = !projectFilePath;

        const activeScan = await window.go.main.App.IsActiveScan();
        const startBtn = document.getElementById("start-debug-btn");
        startBtn.disabled = !hasModsDir || activeScan;
        startBtn.textContent = activeScan ? "Scan in Progress..." : "Start Debug";
        document.getElementById("select-folder-btn").disabled = activeScan;
    } catch (err) {
        console.error("updateUI error:", err);
    }
}

// Event listeners
window.runtime.EventsOn("log", function(data) {
    log(data.message, data.level);
});

window.runtime.EventsOn("test-group-prompt", function(data) {
    showTestDialog(data.count);
});

window.runtime.EventsOn("debug-complete", function(culprit) {
    showInfo("Debug Complete", "Problematic mod(s) found:\n\n" + culprit + "\n\nAll mods have been restored.");
    updateUI();
});

window.runtime.EventsOn("debug-failed", function() {
    showError("Debug Failed", "Unable to isolate the problematic mod(s) even with fallback methods.\nThe issue may be a complex interaction between multiple mod groups.");
    updateUI();
});

window.runtime.EventsOn("test-fallback", function(message) {
    showInfo("Debug Fallback", message);
});

window.runtime.EventsOn("sync-progress", function(data) {
    var el = document.getElementById("sync-status-text");
    if (el) el.textContent = "Syncing: " + data.current + "/" + data.total;
});

window.runtime.EventsOn("sync-complete", function() {
    syncActive = false;
    if (document.getElementById("dep-list")) {
        closeModal();
        refreshDependencyList();
    }
    updateUI();
});

window.runtime.EventsOn("hanging-libs-alert", function(count) {
    var btn = document.getElementById("hanging-libs-btn");
    btn.textContent = "Hanging Libraries (" + count + ")";
});

window.runtime.EventsOn("close-confirm", function() {
    showModal("Unsaved Changes",
        '<p>You have unsaved changes. Do you want to save before closing?</p>',
        '<button class="btn" onclick="closeModal(); window.go.main.App.SubmitCloseAction(\'cancel\')">Cancel</button>' +
        '<button class="btn btn-danger" onclick="closeModal(); window.go.main.App.SubmitCloseAction(\'nosave\')">Don\'t Save</button>' +
        '<button class="btn btn-primary" onclick="closeModal(); window.go.main.App.SubmitCloseAction(\'save\')">Save</button>'
    );
});

function showTestDialog(count) {
    testDialogActive = true;
    showModal("Test Launch",
        '<div class="test-dialog-main">' +
        '<h2>Testing ' + count + ' mods</h2>' +
        '<p>Launch Minecraft now and test if it loads properly.</p>' +
        '<p style="color: var(--text-secondary); font-size: 12px;">Only the selected mods are in your mods folder.</p>' +
        '</div>',
        '<button class="btn btn-danger" onclick="cancelDebug()">Cancel Debug</button>' +
        '<button class="btn" style="background: var(--danger); border-color: var(--danger);" onclick="submitTestResult(false)">Game Crashed</button>' +
        '<button class="btn btn-primary" onclick="submitTestResult(true)">Game Worked</button>'
    );
}

function submitTestResult(success) {
    testDialogActive = false;
    closeModal();
    window.go.main.App.SubmitTestResult(success);
}

async function cancelDebug() {
    await window.go.main.App.CancelScan();
    testDialogActive = false;
    closeModal();
    await updateUI();
}

// Theme
document.getElementById("theme-btn").addEventListener("click", async function() {
    try {
        const newTheme = await window.go.main.App.ToggleTheme();
        if (newTheme === "light") {
            document.body.classList.add("light");
        } else {
            document.body.classList.remove("light");
        }
        currentTheme = newTheme;
    } catch (err) {
        console.error(err);
    }
});

// Project Management
document.getElementById("new-project-btn").addEventListener("click", async function() {
    if (projectModified) {
        const result = await showConfirmCancel("Unsaved Changes", "You have unsaved changes. Do you want to save before creating a new project?");
        if (result === null) return;
        if (result === true) {
            try { await window.go.main.App.SaveProject(); } catch(e) { await showError("Error", e.message); return; }
        }
    }
    try {
        await window.go.main.App.NewProject();
        await updateUI();
        document.getElementById("log-area").innerHTML = "";
    } catch (err) {
        await showError("Error", err);
    }
});

document.getElementById("load-project-btn").addEventListener("click", async function() {
    if (projectModified) {
        const result = await showConfirmCancel("Unsaved Changes", "You have unsaved changes. Do you want to save before loading?");
        if (result === null) return;
        if (result === true) {
            try { await window.go.main.App.SaveProject(); } catch(e) { await showError("Error", e.message); return; }
        }
    }
    try {
        await window.go.main.App.LoadProject();
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
});

document.getElementById("save-project-btn").addEventListener("click", async function() {
    try {
        await window.go.main.App.SaveProject();
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
});

document.getElementById("save-as-btn").addEventListener("click", async function() {
    try {
        await window.go.main.App.SaveProjectAs();
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
});

// Mod Folder
document.getElementById("select-folder-btn").addEventListener("click", async function() {
    try {
        const dir = await window.go.main.App.SelectModFolder();
        if (dir) {
            document.getElementById("folder-label").textContent = dir;
            await updateUI();
        }
    } catch (err) {
        await showError("Error", err);
    }
});

// Snapshot
document.getElementById("create-snapshot-btn").addEventListener("click", async function() {
    try {
        await window.go.main.App.CreateSnapshot();
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
});

// Detect New Mods
document.getElementById("detect-new-mods-btn").addEventListener("click", async function() {
    try {
        const result = await window.go.main.App.DetectNewMods();
        if (!result) {
            await showInfo("Detection Result", "No new mods detected since last snapshot");
            return;
        }
        if (result.NewMods && result.NewMods.length > 0) {
            showNewModsDialog(result.NewMods, result.DeletedMods);
        } else if (result.DeletedMods && result.DeletedMods.length > 0) {
            await showInfo("Detection Result", result.DeletedMods.length + " mod(s) were removed from the snapshot. No new mods were detected.");
        } else {
            await showInfo("Detection Result", "No new mods detected since last snapshot");
        }
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
});

function showNewModsDialog(newMods, deletedMods) {
    let html = '<p style="margin-bottom: 12px; font-weight: 600;">' + newMods.length + ' New Mod(s) Detected:</p><div class="checkbox-list">';
    newMods.forEach(function(mod) {
        html += '<div class="checkbox-item" style="padding: 3px 0; font-size: 13px;">&bull; ' + escapeHtml(mod) + '</div>';
    });
    html += '</div>';
    if (deletedMods && deletedMods.length > 0) {
        html += '<p style="margin-top: 12px; color: var(--log-warning);">' + deletedMods.length + ' mod(s) were removed from the snapshot.</p>';
    }
    html += '<p style="margin-top: 12px; font-weight: 600;">What would you like to do?</p>';

    showModal("New Mods Detected", html,
        '<button class="btn" onclick="closeModal()">Cancel</button>' +
        '<button class="btn btn-primary" onclick="saveNewModsForLater(' + JSON.stringify(newMods) + ')">Save for Later & Snapshot</button>' +
        '<button class="btn" style="background: var(--success); border-color: var(--success);" onclick="startDebugWithNewMods(' + JSON.stringify(newMods) + ')">Start Debug & Snapshot</button>'
    );
}

async function saveNewModsForLater(mods) {
    closeModal();
    try {
        await window.go.main.App.SaveNewModsForLater(mods);
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
}

async function startDebugWithNewMods(mods) {
    closeModal();
    try {
        await window.go.main.App.SaveNewModsForLater(mods);
        await updateUI();
        showModSelectionDialog(mods, "Select New Mods to Debug");
    } catch (err) {
        await showError("Error", err);
    }
}

// Access Saved New Mods
document.getElementById("access-saved-btn").addEventListener("click", async function() {
    try {
        const savedMods = await window.go.main.App.GetSavedNewMods();
        if (!savedMods || savedMods.length === 0) {
            await showInfo("Info", "No saved new mods available");
            return;
        }
        showModSelectionDialog(savedMods, "Saved New Mods");
    } catch (err) {
        await showError("Error", err);
    }
});

function showModSelectionDialog(mods, title) {
    let html = '<p style="margin-bottom: 10px;">' + title + ' (' + mods.length + ' mods)</p><div class="checkbox-list mod-selection-list">';
    const checkId = "modsel_";
    mods.forEach(function(mod, i) {
        html += '<label class="checkbox-item"><input type="checkbox" id="' + checkId + i + '" checked/> ' + escapeHtml(mod) + '</label>';
    });
    html += '</div>';

    const modsJson = JSON.stringify(mods);
    showModal(title, html,
        '<button class="btn" onclick="closeModal()">Cancel</button>' +
        '<button class="btn btn-primary" onclick="startDebugWithSelection(' + modsJson + ', \'' + checkId + '\')">Start Debug with Selected Mods</button>'
    );
}

async function startDebugWithSelection(mods, checkId) {
    const selected = [];
    mods.forEach(function(mod, i) {
        const cb = document.getElementById(checkId + i);
        if (cb && cb.checked) selected.push(mod);
    });
    if (selected.length === 0) {
        await showError("Error", "Please select at least one mod");
        return;
    }
    closeModal();
    try {
        await window.go.main.App.StartDebug("specific", selected);
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
}

// Hanging Libraries
document.getElementById("hanging-libs-btn").addEventListener("click", async function() {
    try {
        const libs = await window.go.main.App.GetHangingLibraries();
        if (!libs || libs.length === 0) {
            await showInfo("No Hanging Libraries", "No hanging library mods detected.");
            return;
        }
        showHangingLibsDialog(libs);
    } catch (err) {
        await showError("Error", err);
    }
});

function showHangingLibsDialog(libs) {
    let html = '<p style="margin-bottom: 10px;">These libraries have no main mod using them:</p><div class="checkbox-list mod-selection-list">';
    const checkId = "hglib_";
    libs.forEach(function(lib, i) {
        html += '<label class="checkbox-item"><input type="checkbox" id="' + checkId + i + '" checked/> ' + escapeHtml(lib) + '</label>';
    });
    html += '</div>';

    const libsJson = JSON.stringify(libs);
    showModal("Hanging Library Mods", html,
        '<button class="btn" onclick="closeModal()">Cancel</button>' +
        '<button class="btn btn-ghost" onclick="dismissSelectedLibs(' + libsJson + ', \'' + checkId + '\')">Dismiss Selected</button>' +
        '<button class="btn btn-danger" onclick="deleteSelectedLibs(' + libsJson + ', \'' + checkId + '\')">Delete Selected</button>'
    );
}

async function deleteSelectedLibs(libs, checkId) {
    const selected = [];
    libs.forEach(function(lib, i) {
        const cb = document.getElementById(checkId + i);
        if (cb && cb.checked) selected.push(lib);
    });
    if (selected.length === 0) {
        await showError("Error", "No libraries selected");
        return;
    }
    const confirmed = await showConfirm("Confirm Deletion", "Delete " + selected.length + " mod(s) permanently?");
    if (!confirmed) return;
    closeModal();
    try {
        await window.go.main.App.DeleteSelectedHangingLibs(selected);
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
}

async function dismissSelectedLibs(libs, checkId) {
    const selected = [];
    libs.forEach(function(lib, i) {
        const cb = document.getElementById(checkId + i);
        if (cb && cb.checked) selected.push(lib);
    });
    if (selected.length === 0) {
        await showError("Error", "No libraries selected");
        return;
    }
    const confirmed = await showConfirm("Confirm Dismiss", "Ignore these warnings? The files will stay, but you won't be warned again for these files.");
    if (!confirmed) return;
    closeModal();
    try {
        await window.go.main.App.DismissSelectedHangingLibs(selected);
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
}

// Dependencies
document.getElementById("manage-deps-btn").addEventListener("click", async function() {
    try {
        const deps = await window.go.main.App.GetDependencies();
        showDependencyManager(deps);
    } catch (err) {
        await showError("Error", err);
    }
});

function showDependencyManager(deps) {
    let html = '<div class="dep-toolbar">';
    html += '<button class="btn btn-primary" onclick="showAddDependency()">Add Dependency</button>';
    html += '<button class="btn btn-danger" onclick="confirmDeleteAllDeps()">Delete All</button>';
    html += '<button class="btn btn-success" onclick="startSync()">Modrinth Sync</button></div>';

    if (syncActive) {
        html += '<div id="sync-status"><span id="sync-status-text">Syncing Dependencies with Modrinth...</span><button class="btn btn-danger btn-sm" onclick="cancelSync()">Cancel Sync</button></div>';
    }

    html += '<div id="dep-list" class="dep-list">';
    const keys = Object.keys(deps);
    if (keys.length === 0) {
        html += '<div class="no-data">No dependencies defined</div>';
    } else {
        keys.forEach(function(mod) {
            const depList = deps[mod] || [];
            html += '<div class="dep-item">' +
                '<div class="dep-item-text">' +
                '<div class="dep-item-name">' + escapeHtml(mod) + '</div>' +
                '<div class="dep-item-deps">' + escapeHtml(depList.join(", ")) + '</div>' +
                '</div>' +
                '<button class="btn btn-danger btn-sm btn-icon" onclick="removeDep(\'' + escapeJs(mod) + '\')">&times;</button>' +
                '</div>';
        });
    }
    html += '</div>';

    showModal("Dependency Manager", html, '<button class="btn" onclick="closeModal()">Close</button>');
}

async function refreshDependencyList() {
    try {
        const deps = await window.go.main.App.GetDependencies();
        const listEl = document.getElementById("dep-list");
        if (!listEl) return;
        const keys = Object.keys(deps);
        if (keys.length === 0) {
            listEl.innerHTML = '<div class="no-data">No dependencies defined</div>';
        } else {
            let html = "";
            keys.forEach(function(mod) {
                const depList = deps[mod] || [];
                html += '<div class="dep-item">' +
                    '<div class="dep-item-text">' +
                    '<div class="dep-item-name">' + escapeHtml(mod) + '</div>' +
                    '<div class="dep-item-deps">' + escapeHtml(depList.join(", ")) + '</div>' +
                    '</div>' +
                    '<button class="btn btn-danger btn-sm btn-icon" onclick="removeDep(\'' + escapeJs(mod) + '\')">&times;</button>' +
                    '</div>';
            });
            listEl.innerHTML = html;
        }
    } catch (err) {
        console.error(err);
    }
}

async function removeDep(mod) {
    try {
        await window.go.main.App.RemoveDependency(mod);
        await refreshDependencyList();
    } catch (err) {
        await showError("Error", err);
    }
}

async function confirmDeleteAllDeps() {
    const confirmed = await showConfirm("Confirm Delete All", "Are you sure you want to delete ALL dependency rules?\nThis action cannot be undone.");
    if (!confirmed) return;
    try {
        await window.go.main.App.DeleteAllDependencies();
        await refreshDependencyList();
    } catch (err) {
        await showError("Error", err);
    }
}

async function startSync() {
    syncActive = true;
    try {
        await window.go.main.App.StartModrinthSync();
        showDependencyManager(await window.go.main.App.GetDependencies());
    } catch (err) {
        await showError("Error", err);
        syncActive = false;
    }
}

async function cancelSync() {
    try {
        await window.go.main.App.CancelSync();
    } catch (err) {
        console.error(err);
    }
}

async function showAddDependency() {
    let availableMods;
    try {
        availableMods = await window.go.main.App.GetAvailableMods();
        if (!availableMods || availableMods.length === 0) {
            await showError("Error", "No mods available. Please select a mod folder first.");
            closeModal();
            return;
        }
    } catch (err) {
        await showError("Error", err);
        return;
    }

    let html = '<div style="margin-bottom: 8px;">';
    html += '<label class="checkbox-item"><input type="checkbox" id="multi-mode" onchange="toggleMultiMode()"/> Select Multiple Main Mods</label>';
    html += '</div>';

    html += '<div class="helper-btns" id="multi-helpers" style="display:none;">';
    html += '<button class="btn" onclick="selectAllMain()">Select All</button>';
    html += '<button class="btn" onclick="selectNoneMain()">Select None</button>';
    html += '</div>';

    html += '<div class="form-label">Select Main Mod(s):</div>';
    html += '<input class="search-input" id="main-search" placeholder="Search main mod..." oninput="filterMainMods()"/>';
    html += '<div class="checkbox-list mod-selection-list" id="main-mod-list">';
    availableMods.forEach(function(mod) {
        html += '<label class="checkbox-item" data-mod="' + escapeHtml(mod) + '">' +
            '<input type="radio" name="main-mod" value="' + escapeHtml(mod) + '" class="main-radio"/> ' + escapeHtml(mod) + '</label>';
    });
    html += '</div>';

    html += '<div class="form-label">Select Dependencies:</div>';
    html += '<input class="search-input" id="dep-search" placeholder="Search dependencies..." oninput="filterDepMods()"/>';
    html += '<div class="checkbox-list mod-selection-list" id="dep-mod-list">';
    availableMods.forEach(function(mod) {
        html += '<label class="checkbox-item" data-mod="' + escapeHtml(mod) + '">' +
            '<input type="checkbox" value="' + escapeHtml(mod) + '" class="dep-check"/> ' + escapeHtml(mod) + '</label>';
    });
    html += '</div>';

    showModal("Add Dependency", html,
        '<button class="btn" onclick="closeModal()">Cancel</button>' +
        '<button class="btn btn-primary" onclick="saveDependency()">Save Dependency</button>'
    );

    window._availableMods = availableMods;
}

function toggleMultiMode() {
    const multi = document.getElementById("multi-mode").checked;
    document.getElementById("multi-helpers").style.display = multi ? "flex" : "none";
    const radios = document.querySelectorAll(".main-radio");
    radios.forEach(function(r) {
        r.type = multi ? "checkbox" : "radio";
    });
    if (!multi) {
        document.querySelectorAll(".main-radio:checked").forEach(function(r) { r.checked = false; });
    }
}

function selectAllMain() {
    document.querySelectorAll(".main-radio").forEach(function(r) { r.checked = true; });
}

function selectNoneMain() {
    document.querySelectorAll(".main-radio").forEach(function(r) { r.checked = false; });
}

function filterMainMods() {
    const q = document.getElementById("main-search").value.toLowerCase();
    document.querySelectorAll("#main-mod-list .checkbox-item").forEach(function(el) {
        const mod = (el.getAttribute("data-mod") || "").toLowerCase();
        el.style.display = mod.includes(q) ? "" : "none";
    });
}

function filterDepMods() {
    const q = document.getElementById("dep-search").value.toLowerCase();
    document.querySelectorAll("#dep-mod-list .checkbox-item").forEach(function(el) {
        const mod = (el.getAttribute("data-mod") || "").toLowerCase();
        el.style.display = mod.includes(q) ? "" : "none";
    });
}

async function saveDependency() {
    const multi = document.getElementById("multi-mode").checked;
    const deps = [];
    document.querySelectorAll(".dep-check:checked").forEach(function(cb) {
        deps.push(cb.value);
    });
    if (deps.length === 0) {
        await showError("Error", "Please select at least one dependency");
        return;
    }
    if (multi) {
        const mains = [];
        document.querySelectorAll(".main-radio:checked").forEach(function(cb) {
            mains.push(cb.value);
        });
        if (mains.length === 0) {
            await showError("Error", "Please select at least one main mod");
            return;
        }
        try {
            await window.go.main.App.AddDependencyMulti(mains, deps);
            closeModal();
            showDependencyManager(await window.go.main.App.GetDependencies());
        } catch (err) {
            await showError("Error", err);
        }
    } else {
        const main = document.querySelector(".main-radio:checked");
        if (!main) {
            await showError("Error", "Please select a main mod");
            return;
        }
        try {
            await window.go.main.App.AddDependency(main.value, deps);
            closeModal();
            showDependencyManager(await window.go.main.App.GetDependencies());
        } catch (err) {
            await showError("Error", err);
        }
    }
}

// Start Debug
document.getElementById("start-debug-btn").addEventListener("click", async function() {
    const mode = document.querySelector('input[name="mode"]:checked');
    if (!mode) return;

    try {
        if (mode.value === "all") {
            await window.go.main.App.StartDebug("all", null);
        } else {
            const savedMods = await window.go.main.App.GetSavedNewMods();
            if (!savedMods || savedMods.length === 0) {
                await showError("Error", "No saved new mods available. Please use 'Detect New Mods' first or switch to Mode 1.");
                return;
            }
            showModSelectionDialog(savedMods, "Select New Mods to Debug");
            return;
        }
        await updateUI();
    } catch (err) {
        await showError("Error", err);
    }
});

// Export Logs
document.getElementById("export-logs-btn").addEventListener("click", async function() {
    const entries = document.querySelectorAll("#log-area .log-entry");
    const text = Array.from(entries).map(function(e) { return e.textContent; }).join("\n");
    if (!text.trim()) {
        await showInfo("Info", "No logs to export.");
        return;
    }
    try {
        await window.go.main.App.ExportLogsToFile(text);
    } catch (err) {
        await showError("Error", err);
    }
});

// Utility
function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function escapeJs(str) {
    if (!str) return "";
    return str.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/"/g, "\\\"");
}

// Initialize
updateUI();
