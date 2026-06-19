package main

import (
	"crypto/sha1"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
)

const modrinthAPIBase = "https://api.modrinth.com/v2"

func getSHA1Hash(filePath string) (string, error) {
	f, err := os.Open(filePath)
	if err != nil {
		return "", fmt.Errorf("error opening file %s: %w", filePath, err)
	}
	defer f.Close()

	h := sha1.New()
	if _, err := io.CopyBuffer(h, f, make([]byte, 65536)); err != nil {
		return "", fmt.Errorf("error reading file %s: %w", filePath, err)
	}
	return fmt.Sprintf("%x", h.Sum(nil)), nil
}

func getModInfo(sha1Hash string) (*ModrinthVersion, error) {
	url := fmt.Sprintf("%s/version_file/%s", modrinthAPIBase, sha1Hash)
	resp, err := http.Get(url)
	if err != nil {
		return nil, fmt.Errorf("error fetching mod info for hash %s: %w", sha1Hash, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API returned status %d for hash %s", resp.StatusCode, sha1Hash)
	}

	var info ModrinthVersion
	if err := json.NewDecoder(resp.Body).Decode(&info); err != nil {
		return nil, fmt.Errorf("error decoding response for hash %s: %w", sha1Hash, err)
	}
	return &info, nil
}

func getProjectVersions(projectID string) ([]ModrinthVersion, error) {
	url := fmt.Sprintf("%s/project/%s/version", modrinthAPIBase, projectID)
	resp, err := http.Get(url)
	if err != nil {
		return nil, fmt.Errorf("error fetching project versions for ID %s: %w", projectID, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API returned status %d for project %s", resp.StatusCode, projectID)
	}

	var versions []ModrinthVersion
	if err := json.NewDecoder(resp.Body).Decode(&versions); err != nil {
		return nil, fmt.Errorf("error decoding versions for project %s: %w", projectID, err)
	}
	return versions, nil
}
