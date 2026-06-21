package main

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	wailsRuntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

//go:embed version
var versionFile embed.FS

var AppVersion string

func init() {
	data, err := versionFile.ReadFile("version")
	if err != nil {
		AppVersion = "0.0.0"
	} else {
		AppVersion = strings.TrimSpace(string(data))
	}
}

type App struct {
	ctx                context.Context
	ProjectData        *ProjectData
	TempDir            string
	ActiveScan         bool
	ScanCancelled      bool
	CurrentTestGroup   []string
	HangingLibraries   []string
	ProjectFilePath    string
	ProjectModified    bool
	SyncCancelled      bool
	AutoLaunchGame     bool
	prevHangingCount   int
	testResultChan     chan bool
	closeConfirmChan   chan string
	mu                 sync.Mutex
}

func NewApp() *App {
	return &App{
		ProjectData: &ProjectData{
			Dependencies:        make(map[string][]string),
			Theme:               "dark",
			SavedNewMods:        []string{},
			DismissedHangingLibs: []string{},
		},
		testResultChan:   make(chan bool, 1),
		closeConfirmChan: make(chan string, 1),
	}
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
	a.TempDir = filepath.Join(os.TempDir(), "modpack-debugger-temp-mods")
	os.RemoveAll(a.TempDir)
	os.MkdirAll(a.TempDir, 0755)

	go a.checkForUpdate()
}

type githubRelease struct {
	TagName string `json:"tag_name"`
}

func (a *App) checkForUpdate() {
	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get("https://api.github.com/repos/WendellCraft/ModpackDebuggerKit/releases/latest")
	if err != nil {
		return
	}
	defer resp.Body.Close()

	var release githubRelease
	if err := json.NewDecoder(resp.Body).Decode(&release); err != nil {
		return
	}
	if release.TagName == "" {
		return
	}

	latest := strings.TrimPrefix(release.TagName, "v")
	if isNewerVersion(latest, AppVersion) {
		wailsRuntime.EventsEmit(a.ctx, "update-available", latest)
	}
}

func isNewerVersion(latest, current string) bool {
	if idx := strings.Index(latest, "-"); idx >= 0 {
		latest = latest[:idx]
	}
	if idx := strings.Index(current, "-"); idx >= 0 {
		current = current[:idx]
	}
	ls := strings.Split(latest, ".")
	cs := strings.Split(current, ".")
	max := len(ls)
	if len(cs) > max {
		max = len(cs)
	}
	for i := 0; i < max; i++ {
		var l, c int
		if i < len(ls) {
			l, _ = strconv.Atoi(ls[i])
		}
		if i < len(cs) {
			c, _ = strconv.Atoi(cs[i])
		}
		if l > c {
			return true
		} else if l < c {
			return false
		}
	}
	return false
}

func (a *App) OpenUpdateURL() {
	wailsRuntime.BrowserOpenURL(a.ctx, "https://github.com/WendellCraft/ModpackDebuggerKit/releases/latest")
}

func (a *App) shutdown(ctx context.Context) {
	os.RemoveAll(a.TempDir)
}

func (a *App) onBeforeClose(ctx context.Context) bool {
	a.mu.Lock()
	modified := a.ProjectModified
	a.mu.Unlock()

	if !modified {
		return false
	}

	wailsRuntime.EventsEmit(a.ctx, "close-confirm", nil)
	result := <-a.closeConfirmChan

	switch result {
	case "save":
		if saveErr := a.SaveProject(); saveErr != nil {
			wailsRuntime.MessageDialog(ctx, wailsRuntime.MessageDialogOptions{
				Type:    wailsRuntime.ErrorDialog,
				Title:   "Error",
				Message: "Failed to save project: " + saveErr.Error(),
			})
			return true
		}
		return false
	case "nosave":
		return false
	default:
		return true
	}
}

func (a *App) SubmitCloseAction(action string) {
	select {
	case a.closeConfirmChan <- action:
	default:
	}
}

func (a *App) emitLog(message, level string) {
	if a.ctx == nil {
		return
	}
	wailsRuntime.EventsEmit(a.ctx, "log", LogMessage{Message: message, Level: level})
}

func (a *App) emitTestGroup(info TestGroupInfo) {
	if a.ctx == nil {
		return
	}
	wailsRuntime.EventsEmit(a.ctx, "test-group-prompt", info)
}

// --- Project Management ---

func (a *App) NewProject() {
	a.mu.Lock()
	defer a.mu.Unlock()

	if a.ActiveScan {
		a.emitLog("Cannot create new project during active scan", LogError)
		return
	}

	a.ProjectData = &ProjectData{
		Dependencies:        make(map[string][]string),
		Theme:               "dark",
		SavedNewMods:        []string{},
		DismissedHangingLibs: []string{},
	}
	a.ProjectFilePath = ""
	a.ProjectModified = false
	a.HangingLibraries = nil
	a.emitLog("New project created", LogSuccess)
}

func (a *App) GetProjectData() *ProjectData {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ProjectData
}

func (a *App) GetProjectFilePath() string {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ProjectFilePath
}

func (a *App) IsProjectModified() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ProjectModified
}

func (a *App) IsActiveScan() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ActiveScan
}

func (a *App) markModified() {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.ProjectModified = true
}

func (a *App) SaveProject() error {
	a.mu.Lock()
	if a.ActiveScan {
		a.mu.Unlock()
		return fmt.Errorf("cannot save project during an active debug session")
	}
	if a.ProjectData.ModsDir == "" {
		a.mu.Unlock()
		return fmt.Errorf("no mod folder selected")
	}
	filePath := a.ProjectFilePath
	a.mu.Unlock()

	if filePath != "" {
		return a.saveToFile(filePath)
	}
	return a.SaveProjectAs()
}

func (a *App) SaveProjectAs() error {
	a.mu.Lock()
	if a.ActiveScan {
		a.mu.Unlock()
		return fmt.Errorf("cannot save project during an active debug session")
	}
	if a.ProjectData.ModsDir == "" {
		a.mu.Unlock()
		return fmt.Errorf("no mod folder selected")
	}
	a.mu.Unlock()

	filePath, err := wailsRuntime.SaveFileDialog(a.ctx, wailsRuntime.SaveDialogOptions{
		Title:           "Save Project As",
		DefaultFilename: "project.json",
		Filters: []wailsRuntime.FileFilter{
			{DisplayName: "JSON Files", Pattern: "*.json"},
		},
	})
	if err != nil {
		return err
	}
	if filePath == "" {
		return fmt.Errorf("save cancelled")
	}

	if err := a.saveToFile(filePath); err != nil {
		return err
	}

	a.mu.Lock()
	a.ProjectFilePath = filePath
	a.mu.Unlock()
	return nil
}

func (a *App) saveToFile(filePath string) error {
	a.mu.Lock()
	data := ProjectData{
		ModsDir:             a.ProjectData.ModsDir,
		LatestSnapshot:      a.ProjectData.LatestSnapshot,
		Dependencies:        a.ProjectData.Dependencies,
		SavedNewMods:        a.ProjectData.SavedNewMods,
		DismissedHangingLibs: a.ProjectData.DismissedHangingLibs,
		Theme:               a.ProjectData.Theme,
	}
	a.mu.Unlock()

	jsonData, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		return fmt.Errorf("error marshaling project data: %w", err)
	}

	if err := os.WriteFile(filePath, jsonData, 0644); err != nil {
		return fmt.Errorf("error writing project file: %w", err)
	}

	a.mu.Lock()
	a.ProjectModified = false
	a.mu.Unlock()

	a.emitLog(fmt.Sprintf("Project saved to %s", filepath.Base(filePath)), LogSuccess)
	return nil
}

func (a *App) LoadProject() error {
	a.mu.Lock()
	if a.ActiveScan {
		a.mu.Unlock()
		return fmt.Errorf("cannot load project during active scan")
	}
	a.mu.Unlock()

	filePath, err := wailsRuntime.OpenFileDialog(a.ctx, wailsRuntime.OpenDialogOptions{
		Title: "Load Project",
		Filters: []wailsRuntime.FileFilter{
			{DisplayName: "JSON Files", Pattern: "*.json"},
		},
	})
	if err != nil {
		return err
	}
	if filePath == "" {
		return nil
	}

	data, err := os.ReadFile(filePath)
	if err != nil {
		return fmt.Errorf("error reading project file: %w", err)
	}

	var projectData ProjectData
	if err := json.Unmarshal(data, &projectData); err != nil {
		return fmt.Errorf("error parsing project file: %w", err)
	}

	if projectData.Dependencies == nil {
		projectData.Dependencies = make(map[string][]string)
	}
	if projectData.SavedNewMods == nil {
		projectData.SavedNewMods = []string{}
	}
	if projectData.DismissedHangingLibs == nil {
		projectData.DismissedHangingLibs = []string{}
	}
	if projectData.Theme == "" {
		projectData.Theme = "dark"
	}

	a.mu.Lock()
	a.ProjectData = &projectData
	a.ProjectFilePath = filePath
	a.ProjectModified = false
	a.mu.Unlock()

	if a.ProjectData.ModsDir != "" {
		a.emitLog(fmt.Sprintf("Mod folder: %s", a.ProjectData.ModsDir), LogInfo)
	}

	a.updateHangingLibraries()
	a.emitLog(fmt.Sprintf("Project loaded from %s", filepath.Base(filePath)), LogSuccess)
	return nil
}

// --- Mod Folder ---

func (a *App) SelectModFolder() (string, error) {
	dir, err := wailsRuntime.OpenDirectoryDialog(a.ctx, wailsRuntime.OpenDialogOptions{
		Title: "Select Mod Folder",
	})
	if err != nil {
		return "", err
	}
	return dir, nil
}

func (a *App) SetModFolderPath(path string) error {
	a.mu.Lock()
	if a.ActiveScan {
		a.mu.Unlock()
		return fmt.Errorf("cannot change mod folder while a debug scan is in progress")
	}
	a.mu.Unlock()

	if path == "" {
		return fmt.Errorf("path cannot be empty")
	}

	info, err := os.Stat(path)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("path does not exist: %s", path)
		}
		return fmt.Errorf("cannot access path: %v", err)
	}
	if !info.IsDir() {
		return fmt.Errorf("path is not a directory: %s", path)
	}

	a.mu.Lock()
	a.ProjectData.ModsDir = path
	a.ProjectData.Dependencies = make(map[string][]string)
	a.ProjectData.LatestSnapshot = nil
	a.ProjectData.SavedNewMods = nil
	a.ProjectData.DismissedHangingLibs = nil
	a.HangingLibraries = nil
	a.ProjectModified = true
	a.mu.Unlock()

	wailsRuntime.EventsEmit(a.ctx, "hanging-libs-alert", 0)
	a.emitLog(fmt.Sprintf("Mod folder set: %s", path), LogSuccess)
	return nil
}

func (a *App) GetAvailableMods() []string {
	a.mu.Lock()
	modsDir := a.ProjectData.ModsDir
	a.mu.Unlock()

	if modsDir == "" {
		return nil
	}

	entries, err := os.ReadDir(modsDir)
	if err != nil {
		return nil
	}

	var mods []string
	for _, e := range entries {
		if !e.IsDir() && filepath.Ext(e.Name()) == ".jar" {
			mods = append(mods, e.Name())
		}
	}
	sort.Strings(mods)
	return mods
}

// --- Snapshot ---

func (a *App) CreateSnapshot() error {
	a.mu.Lock()
	modsDir := a.ProjectData.ModsDir
	a.mu.Unlock()

	if modsDir == "" {
		return fmt.Errorf("please select a mod folder first")
	}

	entries, err := os.ReadDir(modsDir)
	if err != nil {
		return fmt.Errorf("mod folder does not exist: %w", err)
	}

	var modFiles []string
	for _, e := range entries {
		if !e.IsDir() && filepath.Ext(e.Name()) == ".jar" {
			modFiles = append(modFiles, e.Name())
		}
	}

	snapshotName := time.Now().Format("20060102_150405")
	snapshot := &Snapshot{
		Name: snapshotName,
		Mods: modFiles,
	}

	a.mu.Lock()
	a.ProjectData.LatestSnapshot = snapshot
	a.ProjectModified = true
	a.mu.Unlock()

	a.emitLog(fmt.Sprintf("Snapshot created: %s (%d mods)", snapshotName, len(modFiles)), LogSuccess)
	return nil
}

func (a *App) DetectNewMods() (*DetectResult, error) {
	a.mu.Lock()
	modsDir := a.ProjectData.ModsDir
	snapshot := a.ProjectData.LatestSnapshot
	savedNewMods := a.ProjectData.SavedNewMods
	a.mu.Unlock()

	if modsDir == "" {
		return nil, fmt.Errorf("please select a mod folder first")
	}
	if snapshot == nil {
		return nil, fmt.Errorf("no snapshot available. Create a snapshot first.")
	}

	entries, err := os.ReadDir(modsDir)
	if err != nil {
		return nil, fmt.Errorf("mod folder does not exist: %w", err)
	}

	currentMods := make(map[string]bool)
	for _, e := range entries {
		if !e.IsDir() && filepath.Ext(e.Name()) == ".jar" {
			currentMods[e.Name()] = true
		}
	}

	if savedNewMods != nil {
		var filtered []string
		for _, mod := range savedNewMods {
			if currentMods[mod] {
				filtered = append(filtered, mod)
			}
		}
		if len(filtered) < len(savedNewMods) {
			a.mu.Lock()
			a.ProjectData.SavedNewMods = filtered
			a.ProjectModified = true
			a.mu.Unlock()
			a.emitLog(fmt.Sprintf("Removed %d deleted mod(s) from 'saved new mods' list.", len(savedNewMods)-len(filtered)), LogInfo)
		}
	}

	snapshotMods := make(map[string]bool)
	for _, mod := range snapshot.Mods {
		snapshotMods[mod] = true
	}

	var deletedMods []string
	for mod := range snapshotMods {
		if !currentMods[mod] {
			deletedMods = append(deletedMods, mod)
		}
	}

	if len(deletedMods) > 0 {
		a.emitLog(fmt.Sprintf("Detected %d deleted mod(s). Updating snapshot...", len(deletedMods)), LogInfo)
		var updatedMods []string
		for _, mod := range snapshot.Mods {
			if currentMods[mod] {
				updatedMods = append(updatedMods, mod)
			}
		}
		a.mu.Lock()
		a.ProjectData.LatestSnapshot.Mods = updatedMods
		a.ProjectModified = true
		a.mu.Unlock()
		for _, m := range deletedMods {
			delete(snapshotMods, m)
		}
	}

	var newMods []string
	for mod := range currentMods {
		if !snapshotMods[mod] {
			newMods = append(newMods, mod)
		}
	}
	sort.Strings(newMods)

	a.updateHangingLibraries()

	result := &DetectResult{
		NewMods:     newMods,
		DeletedMods: deletedMods,
	}

	return result, nil
}

type DetectResult struct {
	NewMods     []string `json:"new_mods"`
	DeletedMods []string `json:"deleted_mods"`
}

// --- Saved New Mods ---

func (a *App) GetSavedNewMods() []string {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ProjectData.SavedNewMods
}

func (a *App) SaveNewModsForLater(mods []string) {
	a.mu.Lock()
	a.ProjectData.SavedNewMods = mods
	a.ProjectModified = true
	a.mu.Unlock()

	a.CreateSnapshot()
	a.emitLog(fmt.Sprintf("Saved %d new mods for later", len(mods)), LogSuccess)
}

// --- Dependencies ---

func (a *App) GetDependencies() map[string][]string {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ProjectData.Dependencies
}

func (a *App) AddDependency(mainMod string, deps []string) {
	a.mu.Lock()
	depsCopy := append([]string{}, deps...)
	a.ProjectData.Dependencies[mainMod] = depsCopy
	a.ProjectModified = true
	a.mu.Unlock()
	a.emitLog(fmt.Sprintf("Dependency added: %s -> %s", mainMod, joinStrings(deps, ", ")), LogSuccess)
	a.updateHangingLibraries()
}

func (a *App) AddDependencyMulti(mainMods []string, deps []string) {
	a.mu.Lock()
	for _, main := range mainMods {
		depsCopy := append([]string{}, deps...)
		a.ProjectData.Dependencies[main] = depsCopy
	}
	a.ProjectModified = true
	a.mu.Unlock()
	a.emitLog(fmt.Sprintf("Dependencies added for %d mods", len(mainMods)), LogSuccess)
	a.updateHangingLibraries()
}

func (a *App) RemoveDependency(mod string) {
	a.mu.Lock()
	delete(a.ProjectData.Dependencies, mod)
	a.ProjectModified = true
	a.mu.Unlock()
	a.emitLog(fmt.Sprintf("Dependency removed: %s", mod), LogSuccess)
	a.updateHangingLibraries()
}

func (a *App) DeleteAllDependencies() {
	a.mu.Lock()
	a.ProjectData.Dependencies = make(map[string][]string)
	a.ProjectModified = true
	a.mu.Unlock()
	a.emitLog("All dependencies deleted", LogWarning)
	a.updateHangingLibraries()
}

// --- Modrinth Sync ---

func (a *App) StartModrinthSync() {
	a.mu.Lock()
	a.SyncCancelled = false
	a.mu.Unlock()
	go a.modrinthSync()
}

func (a *App) CancelSync() {
	a.mu.Lock()
	a.SyncCancelled = true
	a.mu.Unlock()
	a.emitLog("Sync cancellation requested...", LogWarning)
}

func (a *App) modrinthSync() {
	a.mu.Lock()
	modsDir := a.ProjectData.ModsDir
	a.mu.Unlock()

	if modsDir == "" {
		a.emitLog("Error: Please select a mod folder first", LogError)
		wailsRuntime.EventsEmit(a.ctx, "sync-complete", nil)
		return
	}

	entries, err := os.ReadDir(modsDir)
	if err != nil {
		a.emitLog("Error: Mod folder does not exist", LogError)
		wailsRuntime.EventsEmit(a.ctx, "sync-complete", nil)
		return
	}

	var jarFiles []string
	for _, e := range entries {
		if !e.IsDir() && filepath.Ext(e.Name()) == ".jar" {
			jarFiles = append(jarFiles, e.Name())
		}
	}

	if len(jarFiles) == 0 {
		a.emitLog("No .jar files found in the mods folder.", LogWarning)
		wailsRuntime.EventsEmit(a.ctx, "sync-complete", nil)
		return
	}

	a.emitLog(fmt.Sprintf("Starting Modrinth dependency sync for %d mods...", len(jarFiles)), LogInfo)

	modHashes := make(map[string]string)
	for i, jf := range jarFiles {
		if a.getSyncCancelled() {
			wailsRuntime.EventsEmit(a.ctx, "sync-complete", nil)
			return
		}
		filePath := filepath.Join(modsDir, jf)
		hash, err := getSHA1Hash(filePath)
		if err == nil && hash != "" {
			modHashes[jf] = hash
		}
		a.emitLog(fmt.Sprintf("Hashing mods... (%d/%d)", i+1, len(jarFiles)), LogProgress)
		wailsRuntime.EventsEmit(a.ctx, "sync-progress", map[string]int{"current": i + 1, "total": len(jarFiles)})
	}

	hashToFilename := make(map[string]string)
	for k, v := range modHashes {
		hashToFilename[v] = k
	}

	newDepsCount := 0
	i := 0
	for jarFile, fileHash := range modHashes {
		if a.getSyncCancelled() {
			wailsRuntime.EventsEmit(a.ctx, "sync-complete", nil)
			return
		}
		i++
		a.emitLog(fmt.Sprintf("Syncing... (%d/%d)", i, len(jarFiles)), LogProgress)
		wailsRuntime.EventsEmit(a.ctx, "sync-progress", map[string]int{"current": i, "total": len(jarFiles)})

		modInfo, err := getModInfo(fileHash)
		if err != nil {
			a.emitLog(fmt.Sprintf("API failed or mod not found for %s. Skipping.", jarFile), LogWarning)
			continue
		}

		deps := modInfo.Dependencies
		if len(deps) == 0 {
			continue
		}

		var foundDeps []string
		projectsChecked := make(map[string]bool)

		for _, dep := range deps {
			if dep.DependencyType == "required" && dep.ProjectID != "" && !projectsChecked[dep.ProjectID] {
				projectsChecked[dep.ProjectID] = true

				depVersions, err := getProjectVersions(dep.ProjectID)
				if err != nil {
					continue
				}

				found := false
				for _, dv := range depVersions {
					if found {
						break
					}
					for _, df := range dv.Files {
						if depHash, ok := df.Hashes["sha1"]; ok {
							if filename, exists := hashToFilename[depHash]; exists {
								foundDeps = append(foundDeps, filename)
								found = true
								break
							}
						}
					}
				}
			}
		}

		if len(foundDeps) > 0 {
			a.mu.Lock()
			currentDeps := a.ProjectData.Dependencies[jarFile]
			currentSet := make(map[string]bool)
			for _, d := range currentDeps {
				currentSet[d] = true
			}
			var newDeps []string
			for _, d := range foundDeps {
				if !currentSet[d] {
					newDeps = append(newDeps, d)
				}
			}
			if len(newDeps) > 0 {
				merged := make(map[string]bool)
				for _, d := range currentDeps {
					merged[d] = true
				}
				for _, d := range newDeps {
					merged[d] = true
				}
				var mergedList []string
				for d := range merged {
					mergedList = append(mergedList, d)
				}
				sort.Strings(mergedList)
				a.ProjectData.Dependencies[jarFile] = mergedList
				a.ProjectModified = true
				newDepsCount++
				a.mu.Unlock()
				a.emitLog(fmt.Sprintf("Added dependencies for %s: %s", jarFile, joinStrings(newDeps, ", ")), LogSuccess)
			} else {
				a.mu.Unlock()
				a.emitLog(fmt.Sprintf("Dependencies for %s already tracked.", jarFile), LogInfo)
			}
		}
	}

	if a.getSyncCancelled() {
		wailsRuntime.EventsEmit(a.ctx, "sync-complete", nil)
		return
	}

	a.updateHangingLibraries()

	if newDepsCount > 0 {
		a.emitLog(fmt.Sprintf("Modrinth Sync complete: Added %d dependency rule(s).", newDepsCount), LogSuccess)
	} else {
		a.emitLog("Modrinth Sync complete: No new dependencies were added.", LogInfo)
	}

	wailsRuntime.EventsEmit(a.ctx, "sync-complete", nil)
}

func (a *App) getSyncCancelled() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.SyncCancelled
}

// --- Hanging Libraries ---

func (a *App) updateHangingLibraries() {
	a.mu.Lock()
	modsDir := a.ProjectData.ModsDir
	snapshot := a.ProjectData.LatestSnapshot
	deps := a.ProjectData.Dependencies
	dismissed := make(map[string]bool)
	for _, d := range a.ProjectData.DismissedHangingLibs {
		dismissed[d] = true
	}
	a.mu.Unlock()

	if modsDir == "" || snapshot == nil {
		return
	}

	entries, err := os.ReadDir(modsDir)
	if err != nil {
		return
	}

	currentMods := make(map[string]bool)
	for _, e := range entries {
		if !e.IsDir() && filepath.Ext(e.Name()) == ".jar" {
			currentMods[e.Name()] = true
		}
	}

	allNeededDeps := make(map[string]bool)
	for mod, depList := range deps {
		if currentMods[mod] {
			for _, dep := range depList {
				allNeededDeps[dep] = true
			}
		}
	}

	var hanging []string
	for mod, depList := range deps {
		if !currentMods[mod] {
			for _, dep := range depList {
				if !allNeededDeps[dep] && currentMods[dep] && !dismissed[dep] {
					hanging = append(hanging, dep)
				}
			}
		}
	}

	hangingSet := make(map[string]bool)
	for _, h := range hanging {
		hangingSet[h] = true
	}
	var hangingList []string
	for h := range hangingSet {
		hangingList = append(hangingList, h)
	}

	a.mu.Lock()
	a.HangingLibraries = hangingList
	count := len(hangingList)
	a.mu.Unlock()

	if count != a.prevHangingCount {
		a.prevHangingCount = count
		wailsRuntime.EventsEmit(a.ctx, "hanging-libs-alert", count)
	}
	if count > 0 {
		a.emitLog(fmt.Sprintf("Found %d hanging library mod(s).", count), LogWarning)
	}
}

func (a *App) GetHangingLibraries() []string {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.HangingLibraries
}

func (a *App) DeleteSelectedHangingLibs(libs []string) error {
	a.mu.Lock()
	modsDir := a.ProjectData.ModsDir
	a.mu.Unlock()

	if modsDir == "" {
		return fmt.Errorf("no mod folder selected")
	}

	for _, lib := range libs {
		libPath := filepath.Join(modsDir, lib)
		if err := os.Remove(libPath); err != nil {
			if !os.IsNotExist(err) {
				a.emitLog(fmt.Sprintf("Error deleting %s: %v", lib, err), LogError)
			}
		} else {
			a.emitLog(fmt.Sprintf("Deleted hanging library: %s", lib), LogWarning)
		}
	}

	a.markModified()
	a.updateHangingLibraries()
	return nil
}

func (a *App) DismissSelectedHangingLibs(libs []string) {
	a.mu.Lock()
	a.ProjectData.DismissedHangingLibs = append(a.ProjectData.DismissedHangingLibs, libs...)
	a.ProjectModified = true
	a.mu.Unlock()
	a.updateHangingLibraries()
}

// --- Theme ---

func (a *App) ToggleTheme() string {
	a.mu.Lock()
	current := a.ProjectData.Theme
	newTheme := "light"
	if current == "light" {
		newTheme = "dark"
	}
	a.ProjectData.Theme = newTheme
	a.mu.Unlock()

	a.emitLog(fmt.Sprintf("Theme changed to %s mode", newTheme), LogSuccess)
	return newTheme
}

func (a *App) GetTheme() string {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ProjectData.Theme
}

// --- Debug Control ---

func findPrismLauncher() (string, error) {
	if path, err := exec.LookPath("prismlauncher"); err == nil {
		return path, nil
	}
	return "", fmt.Errorf("Prism Launcher not found. Install it or turn off Auto Launch Game.")
}

func (a *App) StartDebug(mode string, selectedMods []string, autoLaunch bool) error {
	a.mu.Lock()
	if a.ActiveScan {
		a.mu.Unlock()
		return fmt.Errorf("a debug session is already in progress")
	}
	a.AutoLaunchGame = autoLaunch
	modsDir := a.ProjectData.ModsDir
	a.mu.Unlock()

	if modsDir == "" {
		return fmt.Errorf("please select a mod folder first")
	}

	if autoLaunch {
		if _, err := findPrismLauncher(); err != nil {
			return fmt.Errorf("Failed to start debug session, Prism Launcher is not installed. Please install Prism Launcher or turn off Auto Launch Game.")
		}
	}

	entries, err := os.ReadDir(modsDir)
	if err != nil {
		return fmt.Errorf("mod folder does not exist")
	}

	var mods []string
	if mode == "all" {
		for _, e := range entries {
			if !e.IsDir() && filepath.Ext(e.Name()) == ".jar" {
				mods = append(mods, e.Name())
			}
		}
		if len(mods) < 1 {
			return fmt.Errorf("need at least 1 mod to start a debug session")
		}
	} else {
		if len(selectedMods) == 0 {
			a.mu.Lock()
			saved := a.ProjectData.SavedNewMods
			a.mu.Unlock()
			if len(saved) == 0 {
				return fmt.Errorf("no saved new mods available")
			}
			return fmt.Errorf("please select mods and call StartDebug with selectedMods")
		}
		mods = selectedMods
	}

	os.RemoveAll(a.TempDir)
	os.MkdirAll(a.TempDir, 0755)

	go a.runDebugScan(mods)
	return nil
}

func (a *App) SubmitTestResult(success bool) {
	select {
	case a.testResultChan <- success:
	default:
	}
}

func (a *App) CancelScan() {
	a.mu.Lock()
	a.ScanCancelled = true
	a.ActiveScan = false
	a.mu.Unlock()

	select {
	case a.testResultChan <- false:
	default:
	}

	a.emitLog("Cancelling debug scan...", LogWarning)
}

// --- Utility ---

func (a *App) ExportLogsToFile(logs string) error {
	filePath, err := wailsRuntime.SaveFileDialog(a.ctx, wailsRuntime.SaveDialogOptions{
		Title:           "Export Logs",
		DefaultFilename: "log_export.txt",
		Filters: []wailsRuntime.FileFilter{
			{DisplayName: "Text Files", Pattern: "*.txt"},
		},
	})
	if err != nil {
		return err
	}
	if filePath == "" {
		return nil
	}

	if err := os.WriteFile(filePath, []byte(logs), 0644); err != nil {
		return fmt.Errorf("error writing log file: %w", err)
	}

	a.emitLog(fmt.Sprintf("Logs exported to %s", filepath.Base(filePath)), LogSuccess)
	return nil
}

func (a *App) ShowMessageDialog(title, message, dialogType string) (string, error) {
	var msgType wailsRuntime.DialogType
	switch dialogType {
	case "info":
		msgType = wailsRuntime.InfoDialog
	case "warning":
		msgType = wailsRuntime.WarningDialog
	case "error":
		msgType = wailsRuntime.ErrorDialog
	case "question":
		msgType = wailsRuntime.QuestionDialog
	default:
		msgType = wailsRuntime.InfoDialog
	}

	result, err := wailsRuntime.MessageDialog(a.ctx, wailsRuntime.MessageDialogOptions{
		Type:    msgType,
		Title:   title,
		Message: message,
	})
	if err != nil {
		return "", err
	}
	return result, nil
}
