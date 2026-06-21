package main

type ProjectData struct {
	ModsDir            string              `json:"mods_dir"`
	LatestSnapshot     *Snapshot           `json:"latest_snapshot"`
	Dependencies       map[string][]string `json:"dependencies"`
	SavedNewMods       []string            `json:"saved_new_mods"`
	DismissedHangingLibs []string          `json:"dismissed_hanging_libs"`
	RequiredMods       []string            `json:"required_mods"`
	Theme              string              `json:"theme"`
}

type Snapshot struct {
	Name string   `json:"name"`
	Mods []string `json:"mods"`
}

type ModrinthVersionFile struct {
	Hashes      map[string]string `json:"hashes"`
	URL         string            `json:"url"`
	Filename    string            `json:"filename"`
	Primary     bool              `json:"primary"`
	Size        int               `json:"size"`
}

type ModrinthDependency struct {
	VersionID      string `json:"version_id"`
	ProjectID      string `json:"project_id"`
	FileName       string `json:"file_name"`
	DependencyType string `json:"dependency_type"`
}

type ModrinthVersion struct {
	ID           string               `json:"id"`
	ProjectID    string               `json:"project_id"`
	Name         string               `json:"name"`
	VersionNumber string              `json:"version_number"`
	Files        []ModrinthVersionFile `json:"files"`
	Dependencies []ModrinthDependency  `json:"dependencies"`
}

type ModrinthFileInfo struct {
	ID       string            `json:"id"`
	Filename string            `json:"filename"`
	Hashes   map[string]string `json:"hashes"`
	URL      string            `json:"url"`
	Primary  bool              `json:"primary"`
}

type LogMessage struct {
	Message string `json:"message"`
	Level   string `json:"level"`
}

type TestGroupInfo struct {
	Count int      `json:"count"`
	Mods  []string `json:"mods"`
}

const (
	LogInfo    = "INFO"
	LogSuccess = "SUCCESS"
	LogError   = "ERROR"
	LogWarning = "WARNING"
	LogProgress = "PROGRESS"
)
