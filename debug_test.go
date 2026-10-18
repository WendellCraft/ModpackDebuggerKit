// SPDX-FileCopyrightText: 2026 wendellmeset
// SPDX-License-Identifier: GPL-3.0-or-later

package main

import (
	"reflect"
	"sort"
	"testing"
)

func sortedKeys(set map[string]bool) []string {
	keys := make([]string, 0, len(set))
	for key := range set {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func TestCollectDependencies(t *testing.T) {
	dependencies := map[string][]string{
		"a.jar": {"b.jar"},
		"b.jar": {"c.jar"},
		"c.jar": nil,
		"d.jar": {"missing.jar"},
	}

	tests := []struct {
		name  string
		start []string
		only  map[string]bool
		want  []string
	}{
		{
			name:  "single mod without dependencies",
			start: []string{"c.jar"},
			want:  []string{"c.jar"},
		},
		{
			name:  "dependencies are collected transitively",
			start: []string{"a.jar"},
			want:  []string{"a.jar", "b.jar", "c.jar"},
		},
		{
			name:  "dependencies missing from the folder are recorded",
			start: []string{"d.jar"},
			want:  []string{"d.jar", "missing.jar"},
		},
		{
			name:  "only limits traversal to the given mods",
			start: []string{"a.jar"},
			only:  map[string]bool{"a.jar": true, "b.jar": true},
			want:  []string{"a.jar", "b.jar"},
		},
		{
			name:  "duplicates and empty names are ignored",
			start: []string{"a.jar", "a.jar", "", ""},
			want:  []string{"a.jar", "b.jar", "c.jar"},
		},
		{
			name:  "no required mods",
			start: nil,
			want:  []string{},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := sortedKeys(collectDependencies(tt.start, dependencies, tt.only))
			if !reflect.DeepEqual(got, tt.want) {
				t.Errorf("collectDependencies() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestCollectDependenciesHandlesCyclesAndNilGraph(t *testing.T) {
	cyclic := map[string][]string{
		"a.jar": {"b.jar"},
		"b.jar": {"a.jar"},
	}
	if got := sortedKeys(collectDependencies([]string{"a.jar"}, cyclic, nil)); !reflect.DeepEqual(got, []string{"a.jar", "b.jar"}) {
		t.Errorf("collectDependencies() with a cycle = %v, want [a.jar b.jar]", got)
	}

	if got := sortedKeys(collectDependencies([]string{"a.jar"}, nil, nil)); !reflect.DeepEqual(got, []string{"a.jar"}) {
		t.Errorf("collectDependencies() with a nil graph = %v, want [a.jar]", got)
	}
}

func TestGetPrimaryModsAndGroupMap(t *testing.T) {
	tests := []struct {
		name        string
		deps        map[string][]string
		allMods     []string
		wantPrimary []string
		wantGroups  map[string][]string
	}{
		{
			name: "dependencies become part of their primary mod group",
			deps: map[string][]string{
				"a.jar": {"b.jar"},
				"b.jar": {"c.jar"},
			},
			allMods:     []string{"a.jar", "b.jar", "c.jar", "standalone.jar"},
			wantPrimary: []string{"a.jar", "standalone.jar"},
			wantGroups: map[string][]string{
				"a.jar":          {"a.jar", "b.jar", "c.jar"},
				"standalone.jar": {"standalone.jar"},
			},
		},
		{
			name: "dependencies outside the scan are ignored",
			deps: map[string][]string{
				"a.jar": {"external.jar"},
			},
			allMods:     []string{"a.jar", "b.jar"},
			wantPrimary: []string{"a.jar", "b.jar"},
			wantGroups: map[string][]string{
				"a.jar": {"a.jar"},
				"b.jar": {"b.jar"},
			},
		},
		{
			name: "circular dependencies fall back to testing every mod",
			deps: map[string][]string{
				"x.jar": {"y.jar"},
				"y.jar": {"x.jar"},
			},
			allMods:     []string{"y.jar", "x.jar"},
			wantPrimary: []string{"x.jar", "y.jar"},
			wantGroups: map[string][]string{
				"x.jar": {"x.jar", "y.jar"},
				"y.jar": {"x.jar", "y.jar"},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			app := &App{ProjectData: &ProjectData{Dependencies: tt.deps}}
			primary, groups := app.getPrimaryModsAndGroupMap(tt.allMods)

			if !reflect.DeepEqual(primary, tt.wantPrimary) {
				t.Errorf("primary mods = %v, want %v", primary, tt.wantPrimary)
			}
			if !reflect.DeepEqual(groups, tt.wantGroups) {
				t.Errorf("groups = %v, want %v", groups, tt.wantGroups)
			}
		})
	}
}

// TestRequiredModsKeepDependencies covers issue #25: the dependencies of a required
// mod must not be filtered out of the mods that the debugger disables.
func TestRequiredModsKeepDependencies(t *testing.T) {
	dependencies := map[string][]string{
		"required.jar": {"library.jar"},
		"library.jar":  {"core.jar"},
	}

	requiredSet := collectDependencies([]string{"required.jar"}, dependencies, nil)

	modsOnDisk := []string{"required.jar", "library.jar", "core.jar", "tested.jar"}
	var disabled []string
	for _, mod := range modsOnDisk {
		if !requiredSet[mod] {
			disabled = append(disabled, mod)
		}
	}

	if want := []string{"tested.jar"}; !reflect.DeepEqual(disabled, want) {
		t.Errorf("disabled mods = %v, want %v", disabled, want)
	}
}
