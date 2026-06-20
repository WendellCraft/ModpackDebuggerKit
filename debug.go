package main

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"

	wailsRuntime "github.com/wailsapp/wails/v2/pkg/runtime"
)

func moveFile(src, dst string) error {
	err := os.Rename(src, dst)
	if err == nil {
		return nil
	}
	if _, ok := err.(*os.LinkError); ok {
		return copyFile(src, dst)
	}
	return err
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	if _, err := io.Copy(out, in); err != nil {
		return err
	}
	if err := out.Close(); err != nil {
		return err
	}
	return os.Remove(src)
}

func (a *App) getPrimaryModsAndGroupMap(allMods []string) ([]string, map[string][]string) {
	a.mu.Lock()
	deps := a.ProjectData.Dependencies
	a.mu.Unlock()

	allModsSet := make(map[string]bool)
	for _, m := range allMods {
		allModsSet[m] = true
	}

	allDepsInSet := make(map[string]bool)
	for _, mod := range allMods {
		for _, dep := range deps[mod] {
			if allModsSet[dep] {
				allDepsInSet[dep] = true
			}
		}
	}

	var primaryMods []string
	for _, mod := range allMods {
		if !allDepsInSet[mod] {
			primaryMods = append(primaryMods, mod)
		}
	}
	sort.Strings(primaryMods)

	if len(primaryMods) == 0 {
		primaryMods = make([]string, len(allMods))
		copy(primaryMods, allMods)
		sort.Strings(primaryMods)
	}

	groupMap := make(map[string][]string)
	for _, primary := range primaryMods {
		group := make(map[string]bool)
		group[primary] = true
		queue := make([]string, 0)
		queue = append(queue, deps[primary]...)
		processed := make(map[string]bool)

		for len(queue) > 0 {
			dep := queue[0]
			queue = queue[1:]
			if processed[dep] {
				continue
			}
			processed[dep] = true
			if allModsSet[dep] {
				group[dep] = true
				queue = append(queue, deps[dep]...)
			}
		}

		var groupList []string
		for m := range group {
			groupList = append(groupList, m)
		}
		sort.Strings(groupList)
		groupMap[primary] = groupList
	}

	return primaryMods, groupMap
}

func (a *App) runDebugScan(modsToTest []string) {
	a.mu.Lock()
	a.ActiveScan = true
	a.ScanCancelled = false
	a.CurrentTestGroup = modsToTest
	modsDir := a.ProjectData.ModsDir
	a.mu.Unlock()

	a.emitLog(fmt.Sprintf("Starting debug scan with %d mods...", len(modsToTest)), LogInfo)
	a.emitLog("Preparing... (moving mods to temp directory)", LogInfo)

	for i, mod := range modsToTest {
		if a.getScanCancelled() {
			break
		}
		src := filepath.Join(modsDir, mod)
		dst := filepath.Join(a.TempDir, mod)
		if _, err := os.Stat(src); err == nil {
			if err := moveFile(src, dst); err != nil {
				a.emitLog("Failed to move "+mod+": "+err.Error(), LogError)
				a.restoreAllMods(modsDir)
				a.mu.Lock()
				a.ActiveScan = false
				a.CurrentTestGroup = nil
				a.mu.Unlock()
				wailsRuntime.EventsEmit(a.ctx, "debug-failed", nil)
				return
			}
		}
		a.emitLog(fmt.Sprintf("Moving... (%d/%d)", i+1, len(modsToTest)), LogProgress)
	}

	var culpritInfo string
	if !a.getScanCancelled() {
		a.emitLog("Preparation complete.", LogSuccess)
		a.emitLog("Analyzing mod dependencies to form testable groups...", LogInfo)
		primaryMods, groupMap := a.getPrimaryModsAndGroupMap(modsToTest)
		a.emitLog(fmt.Sprintf("Identified %d primary mods/groups for testing.", len(primaryMods)), LogSuccess)

		if len(primaryMods) > 0 {
			a.emitLog("Starting debug search to isolate 1 culprit...", LogInfo)
			culpritInfo = a.binarySearch(primaryMods, groupMap, 1)

			if culpritInfo == "" && !a.getScanCancelled() {
				a.emitLog("Unable to isolate a single culprit. Falling back to 2-culprit resolution...", LogWarning)
				wailsRuntime.EventsEmit(a.ctx, "test-fallback", "Unable to isolate a single problematic mod/group.\n\nFalling back to identify an interaction between 2.")
				culpritInfo = a.binarySearch(primaryMods, groupMap, 2)
			}
			if culpritInfo == "" && !a.getScanCancelled() {
				a.emitLog("Unable to isolate 2 culprits. Falling back to 3-culprit resolution...", LogWarning)
				wailsRuntime.EventsEmit(a.ctx, "test-fallback", "Unable to isolate a 2-mod/group interaction.\n\nFalling back to identify an interaction between 3.")
				culpritInfo = a.binarySearch(primaryMods, groupMap, 3)
			}
		} else {
			a.emitLog("No primary mods could be identified. Aborting scan.", LogError)
		}
	}

	a.restoreAllMods(modsDir)

	a.mu.Lock()
	a.ActiveScan = false
	a.CurrentTestGroup = nil
	a.mu.Unlock()

	if a.getScanCancelled() {
		a.emitLog("Debug scan cancelled by user.", LogWarning)
	} else if culpritInfo != "" {
		a.emitLog(fmt.Sprintf("CULPRIT(S) IDENTIFIED: %s", culpritInfo), LogError)
		wailsRuntime.EventsEmit(a.ctx, "debug-complete", culpritInfo)
	} else {
		a.emitLog("No specific culprit(s) identified.", LogWarning)
		wailsRuntime.EventsEmit(a.ctx, "debug-failed", nil)
	}

	a.emitLog("Cleanup complete. Ready for next session.", LogSuccess)
}

func (a *App) restoreAllMods(modsDir string) {
	a.mu.Lock()
	group := a.CurrentTestGroup
	a.mu.Unlock()

	allOk := true
	for _, mod := range group {
		src := filepath.Join(a.TempDir, mod)
		dst := filepath.Join(modsDir, mod)
		if _, err := os.Stat(src); err == nil {
			if err := moveFile(src, dst); err != nil {
				allOk = false
				a.emitLog(fmt.Sprintf("Failed to restore %s: %v", mod, err), LogError)
			}
		}
	}
	if allOk {
		os.RemoveAll(a.TempDir)
	} else {
		a.emitLog(fmt.Sprintf("Some mods could not be restored. Check %s for remaining files.", a.TempDir), LogWarning)
	}
}

func (a *App) getScanCancelled() bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.ScanCancelled
}

func (a *App) binarySearch(primaryMods []string, groupMap map[string][]string, targetCount int) string {
	current := make([]string, len(primaryMods))
	copy(current, primaryMods)

	for len(current) > targetCount && !a.getScanCancelled() {
		mid := len(current) / 2
		groupA := current[:mid]
		groupB := current[mid:]

		modsAList := flattenGroup(groupA, groupMap)
		a.emitLog(fmt.Sprintf("Testing Group A (%d mods from %d primary groups)...", len(modsAList), len(groupA)), LogInfo)
		result := a.testGroup(modsAList)

		if a.getScanCancelled() {
			return ""
		}

		if result {
			a.emitLog("Group A passed - focusing on Group B", LogSuccess)
			current = groupB
		} else {
			a.emitLog("Group A failed - focusing on Group A", LogError)
			current = groupA
		}
	}

	if a.getScanCancelled() || len(current) > targetCount {
		return ""
	}

	finalList := flattenGroup(current, groupMap)
	a.emitLog(fmt.Sprintf("Final test on suspected culprit(s) (%d mods from %d groups)...", len(finalList), len(current)), LogInfo)
	finalResult := a.testGroup(finalList)

	if a.getScanCancelled() {
		return ""
	}

	if !finalResult {
		sort.Strings(finalList)
		return joinStrings(finalList, ", ")
	}

	a.emitLog("Final test passed. Could not isolate the issue.", LogWarning)
	return ""
}

func flattenGroup(primaryMods []string, groupMap map[string][]string) []string {
	modSet := make(map[string]bool)
	for _, p := range primaryMods {
		for _, m := range groupMap[p] {
			modSet[m] = true
		}
	}
	var list []string
	for m := range modSet {
		list = append(list, m)
	}
	return list
}

func (a *App) testGroup(mods []string) bool {
	a.mu.Lock()
	modsDir := a.ProjectData.ModsDir
	currentGroup := a.CurrentTestGroup
	a.mu.Unlock()

	for _, item := range readDirNames(modsDir) {
		if filepath.Ext(item) != ".jar" {
			continue
		}
		inCurrent := false
		for _, m := range currentGroup {
			if m == item {
				inCurrent = true
				break
			}
		}
		if inCurrent {
			src := filepath.Join(modsDir, item)
			dst := filepath.Join(a.TempDir, item)
			if _, err := os.Stat(src); err == nil {
				if err := moveFile(src, dst); err != nil {
					a.emitLog("Failed to isolate "+item+": "+err.Error(), LogError)
				}
			}
		}
	}

	for _, mod := range mods {
		src := filepath.Join(a.TempDir, mod)
		dst := filepath.Join(modsDir, mod)
		if _, err := os.Stat(src); err == nil {
			if err := moveFile(src, dst); err != nil {
				a.emitLog("Failed to restore "+mod+": "+err.Error(), LogError)
			}
		}
	}

	return a.waitForTestResult(len(mods))
}

func (a *App) waitForTestResult(modCount int) bool {
	wailsRuntime.EventsEmit(a.ctx, "test-group-prompt", map[string]int{"count": modCount})
	result := <-a.testResultChan
	return result
}

func readDirNames(dir string) []string {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}
	var names []string
	for _, e := range entries {
		names = append(names, e.Name())
	}
	return names
}

func joinStrings(items []string, sep string) string {
	if len(items) == 0 {
		return ""
	}
	result := items[0]
	for _, s := range items[1:] {
		result += sep + s
	}
	return result
}
