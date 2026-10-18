// SPDX-FileCopyrightText: 2026 wendellmeset
// SPDX-License-Identifier: GPL-3.0-or-later

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
)

// prismLauncherExecutableNames are the names the Prism Launcher binary can have on
// the PATH, depending on platform and install method.
func prismLauncherExecutableNames() []string {
	switch runtime.GOOS {
	case "windows":
		return []string{"prismlauncher.exe", "prismlauncher"}
	case "darwin":
		return []string{"prismlauncher", "PrismLauncher"}
	default:
		return []string{"prismlauncher", "PrismLauncher", "prism-launcher"}
	}
}

// findPrismLauncher locates the Prism Launcher binary. It looks on the PATH first,
// then falls back to the well known install locations of the platform and the
// install folder recorded by the Windows installer, because none of them are
// guaranteed to be on the PATH (see issue #24).
func findPrismLauncher() (string, error) {
	for _, name := range prismLauncherExecutableNames() {
		if path, err := exec.LookPath(name); err == nil {
			return path, nil
		}
	}

	for _, candidate := range prismLauncherCandidates() {
		if path, ok := existingExecutable(candidate); ok {
			return path, nil
		}
	}

	if path, err := prismLauncherFromRegistry(); err == nil && path != "" {
		return path, nil
	}

	return "", fmt.Errorf("Prism Launcher not found. Install it, add it to your PATH, or turn off Auto Launch Game.")
}

// existingExecutable reports whether the candidate is a runnable file. A candidate
// may be a glob pattern, which is how the AppImage builds are matched because their
// file name carries the version.
func existingExecutable(candidate string) (string, bool) {
	if candidate == "" {
		return "", false
	}

	matches := []string{candidate}
	if strings.ContainsAny(candidate, "*?[") {
		globbed, err := filepath.Glob(candidate)
		if err != nil {
			return "", false
		}
		matches = globbed
	}

	for _, match := range matches {
		info, err := os.Stat(match)
		if err != nil || info.IsDir() {
			continue
		}
		if runtime.GOOS != "windows" && info.Mode().Perm()&0o111 == 0 {
			continue
		}
		return match, true
	}
	return "", false
}

// envPath joins the value of an environment variable with the given path elements
// and returns an empty string when the variable is not set.
func envPath(envVar string, elements ...string) string {
	base := os.Getenv(envVar)
	if base == "" {
		return ""
	}
	return filepath.Join(append([]string{base}, elements...)...)
}

// displayIconPath normalises a Windows DisplayIcon value, which may be quoted and
// may carry a trailing icon index such as ",0". It returns an empty string when
// the value does not point at an executable.
func displayIconPath(value string) string {
	icon := strings.TrimSpace(value)
	if idx := strings.LastIndex(icon, ","); idx != -1 && strings.Trim(icon[idx+1:], "0123456789") == "" {
		icon = icon[:idx]
	}
	icon = strings.Trim(strings.TrimSpace(icon), `"`)
	if !strings.HasSuffix(strings.ToLower(icon), ".exe") {
		return ""
	}
	return icon
}
