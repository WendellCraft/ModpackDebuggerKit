//go:build linux || darwin

package main

import (
	"os"
	"path/filepath"
	"runtime"
)

// prismLauncherCandidates lists the locations the Prism Launcher packages and
// archives use when the binary is not on the PATH. The AppImage entries are glob
// patterns because their file names carry the version.
func prismLauncherCandidates() []string {
	home, err := os.UserHomeDir()
	if err != nil {
		home = ""
	}

	if runtime.GOOS == "darwin" {
		// The released build is PrismLauncher.app with a prismlauncher executable
		// inside Contents/MacOS. The other spellings cover renamed copies.
		bundles := []string{
			filepath.Join("/Applications", "PrismLauncher.app"),
			filepath.Join("/Applications", "Prism Launcher.app"),
			filepath.Join(home, "Applications", "PrismLauncher.app"),
			filepath.Join(home, "Applications", "Prism Launcher.app"),
		}

		candidates := make([]string, 0, len(bundles)*2+3)
		for _, bundle := range bundles {
			candidates = append(candidates,
				filepath.Join(bundle, "Contents", "MacOS", "prismlauncher"),
				filepath.Join(bundle, "Contents", "MacOS", "PrismLauncher"),
			)
		}
		candidates = append(candidates,
			"/Applications/Prism*.app/Contents/MacOS/prism*",
			"/opt/homebrew/bin/prismlauncher",
			"/usr/local/bin/prismlauncher",
		)
		return candidates
	}

	return []string{
		"/usr/bin/prismlauncher",
		"/usr/local/bin/prismlauncher",
		"/opt/prismlauncher/PrismLauncher",
		"/opt/PrismLauncher/prismlauncher",
		"/var/lib/flatpak/exports/bin/org.prismlauncher.PrismLauncher",
		filepath.Join(home, ".local", "share", "flatpak", "exports", "bin", "org.prismlauncher.PrismLauncher"),
		filepath.Join(home, ".local", "bin", "prismlauncher"),
		filepath.Join(home, "bin", "prismlauncher"),
		filepath.Join(home, "Applications", "PrismLauncher*.AppImage"),
		filepath.Join(home, "Applications", "PrismLauncher*"),
		filepath.Join(home, "Downloads", "PrismLauncher*.AppImage"),
		filepath.Join(home, "PrismLauncher*.AppImage"),
	}
}

// prismLauncherFromRegistry has no equivalent outside Windows.
func prismLauncherFromRegistry() (string, error) {
	return "", nil
}
