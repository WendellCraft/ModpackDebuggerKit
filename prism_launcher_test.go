package main

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestExistingExecutable(t *testing.T) {
	dir := t.TempDir()

	executable := filepath.Join(dir, "prismlauncher")
	if err := os.WriteFile(executable, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatal(err)
	}

	tests := []struct {
		name      string
		candidate string
		wantFound bool
	}{
		{"absolute path", executable, true},
		{"glob pattern", filepath.Join(dir, "prism*"), true},
		{"missing file", filepath.Join(dir, "nope"), false},
		{"directory", dir, false},
		{"empty candidate", "", false},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			path, ok := existingExecutable(tt.candidate)
			if ok != tt.wantFound {
				t.Fatalf("existingExecutable(%q) = %v, want %v", tt.candidate, ok, tt.wantFound)
			}
			if ok && path == "" {
				t.Fatalf("existingExecutable(%q) returned an empty path", tt.candidate)
			}
		})
	}
}

func TestExistingExecutableRejectsNonExecutable(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("the executable bit is not used on Windows")
	}

	path := filepath.Join(t.TempDir(), "prismlauncher")
	if err := os.WriteFile(path, []byte("not runnable"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, ok := existingExecutable(path); ok {
		t.Errorf("existingExecutable(%q) accepted a file without the executable bit", path)
	}
}

func TestEnvPath(t *testing.T) {
	t.Setenv("MDK_TEST_DIR", filepath.Join("base", "dir"))
	if got, want := envPath("MDK_TEST_DIR", "PrismLauncher", "prismlauncher"), filepath.Join("base", "dir", "PrismLauncher", "prismlauncher"); got != want {
		t.Errorf("envPath() = %q, want %q", got, want)
	}

	t.Setenv("MDK_TEST_DIR", "")
	if got := envPath("MDK_TEST_DIR", "prismlauncher"); got != "" {
		t.Errorf("envPath() with unset variable = %q, want %q", got, "")
	}
}

func TestDisplayIconPath(t *testing.T) {
	tests := []struct {
		name  string
		value string
		want  string
	}{
		{"plain path", `C:\PrismLauncher\prismlauncher.exe`, `C:\PrismLauncher\prismlauncher.exe`},
		{"quoted path", `"C:\PrismLauncher\prismlauncher.exe"`, `C:\PrismLauncher\prismlauncher.exe`},
		{"with icon index", `C:\PrismLauncher\prismlauncher.exe,0`, `C:\PrismLauncher\prismlauncher.exe`},
		{"quoted with icon index", `"C:\PrismLauncher\prismlauncher.exe",0`, `C:\PrismLauncher\prismlauncher.exe`},
		{"not an executable", `C:\PrismLauncher\prismlauncher.ico`, ""},
		{"empty", "", ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := displayIconPath(tt.value); got != tt.want {
				t.Errorf("displayIconPath(%q) = %q, want %q", tt.value, got, tt.want)
			}
		})
	}
}

func TestFindPrismLauncherFromPath(t *testing.T) {
	name := "prismlauncher"
	if runtime.GOOS == "windows" {
		name = "prismlauncher.exe"
	}

	path := filepath.Join(t.TempDir(), name)
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PATH", filepath.Dir(path))

	got, err := findPrismLauncher()
	if err != nil {
		t.Fatalf("findPrismLauncher() returned an error for a binary on the PATH: %v", err)
	}
	if filepath.Base(got) != name {
		t.Errorf("findPrismLauncher() = %q, want a path ending in %q", got, name)
	}
}

func TestPrismLauncherCandidates(t *testing.T) {
	candidates := prismLauncherCandidates()
	if len(candidates) == 0 {
		t.Fatal("prismLauncherCandidates() returned no candidates")
	}
	for _, candidate := range candidates {
		if candidate == "" {
			// Environment variables such as LOCALAPPDATA may be unset, which is
			// expected and skipped by findPrismLauncher.
			continue
		}
		if !filepath.IsAbs(candidate) {
			t.Errorf("candidate %q is not an absolute path", candidate)
		}
	}
}
