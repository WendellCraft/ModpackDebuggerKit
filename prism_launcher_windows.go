//go:build windows

package main

import (
	"path/filepath"
	"strings"

	"golang.org/x/sys/windows/registry"
)

// prismLauncherCandidates lists the locations the Prism Launcher installer, winget
// and scoop use. None of them are added to the PATH by default.
func prismLauncherCandidates() []string {
	const exe = "prismlauncher.exe"
	return []string{
		envPath("LOCALAPPDATA", "Programs", "PrismLauncher", exe),
		envPath("LOCALAPPDATA", "PrismLauncher", exe),
		envPath("APPDATA", "PrismLauncher", exe),
		envPath("ProgramFiles", "PrismLauncher", exe),
		envPath("ProgramFiles(x86)", "PrismLauncher", exe),
		envPath("USERPROFILE", "scoop", "apps", "prismlauncher", "current", exe),
	}
}

// prismLauncherFromRegistry finds the install folder recorded by the Prism
// Launcher installer, so installs into a location we do not guess are still
// detected.
func prismLauncherFromRegistry() (string, error) {
	const exe = "prismlauncher.exe"

	// The NSIS installer always records its install folder here.
	if key, err := registry.OpenKey(registry.CURRENT_USER, `Software\PrismLauncher`, registry.READ); err == nil {
		installDir, _, _ := key.GetStringValue("InstallDir")
		key.Close()
		if installDir != "" {
			if path, ok := existingExecutable(filepath.Join(installDir, exe)); ok {
				return path, nil
			}
		}
	}

	// Other install methods only show up in the uninstall keys.
	keyPaths := []string{
		`Software\Microsoft\Windows\CurrentVersion\Uninstall`,
		`Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall`,
	}

	for _, root := range []registry.Key{registry.CURRENT_USER, registry.LOCAL_MACHINE} {
		for _, keyPath := range keyPaths {
			subKeys, err := registrySubKeys(root, keyPath)
			if err != nil {
				continue
			}

			for _, subKey := range subKeys {
				key, err := registry.OpenKey(root, keyPath+`\`+subKey, registry.READ)
				if err != nil {
					continue
				}
				displayName, _, _ := key.GetStringValue("DisplayName")
				installLocation, _, _ := key.GetStringValue("InstallLocation")
				displayIcon, _, _ := key.GetStringValue("DisplayIcon")
				key.Close()

				if !strings.Contains(strings.ToLower(displayName), "prism launcher") {
					continue
				}
				if installLocation != "" {
					if path, ok := existingExecutable(filepath.Join(installLocation, exe)); ok {
						return path, nil
					}
				}
				if path, ok := existingExecutable(displayIconPath(displayIcon)); ok {
					return path, nil
				}
			}
		}
	}
	return "", nil
}

func registrySubKeys(root registry.Key, keyPath string) ([]string, error) {
	key, err := registry.OpenKey(root, keyPath, registry.READ)
	if err != nil {
		return nil, err
	}
	defer key.Close()
	return key.ReadSubKeyNames(-1)
}
