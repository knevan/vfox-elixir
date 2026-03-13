# --*- coding: utf-8 --*-
"""Fetch all Elixir versions from GitHub API and save to a local file."""

import json
import re
import os
import requests
from packaging import version

# fetch version: -> https://api.github.com/repos/elixir-lang/elixir/tags?per_page=100&sort=pushed
# github api has rate limt
# prefer use local version file
def update_all_version_from_github_api():
    """Fetch all Elixir version tags from GitHub API and save to local JSON file.

    Makes paginated requests to GitHub API to retrieve all available Elixir version tags.
    The fetched data is saved to 'elixir_versions_from_github_api.json' for local use
    to avoid hitting GitHub API rate limits on subsequent runs.

    Note:
        GitHub API has rate limits, so prefer using the local version file when possible.
    """
    all_version = []
    success = False
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {}

    if github_token:
        headers["Authorization"] = f"token {github_token}"
        headers["Accept"] = "application/vnd.github+json"

    for page in range(1, 10):
        url = (
            f"https://api.github.com/repos/elixir-lang/elixir/tags"
            f"?per_page=100&sort=pushed&page={page}"
        )

        try:
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 403:
                print("Hint: GitHub API rate limit reached. Use GITHUB_TOKEN to increase limits.")
                break

            if response.status_code != 200:
                print("Failed to fetch data from github api, status: {response.status_code}")
                break

            data = response.json()

            if not data:
                success = True
                break

            all_version.extend(data)
            success = True
            
        except Exception as e:
            print(f"Error fetching data from github api: {e}")
            break

    if success and all_version:
        with open("elixir_versions_from_github_api.json", "w", encoding="utf-8") as file:
            json.dump(all_version, file, indent=4)
            print(f"Successfully updated elixir_versions_from_github_api.json with {len(all_version)} items.")
    else:
        print("Warning: Skipping update to prevent data loss due to API failure/empty data.")


def get_all_version():
    """Extract all Elixir version numbers from GitHub API data.

    Reads the local JSON file containing GitHub API response data and extracts
    version numbers from tarball URLs that contain 'refs/tags/v' pattern.

    Returns:
        set: A set of version strings extracted from the GitHub API data.
    """
    version_set = set()

    with open("elixir_versions_from_github_api.json", "r", encoding="utf-8") as file:
        data = json.load(file)

        for item in data:
            name = item.get("name", "")
            # Direct extraction using tag name
            if name.startswith("v"):
                version_set.add(name[1:])
            elif name:
                version_set.add(name)
                
    return version_set


def parse_version(version_string):
    """Parse a version string and return parsing result with metadata.

    Attempts to parse a version string using the packaging library's version parser.
    Returns a tuple containing the parsed version (or original string if invalid),
    a boolean indicating parsing success, and the original version string.

    Args:
        version_string (str): The version string to parse.

    Returns:
        tuple: A 3-tuple containing:
            - Parsed version object (or original string if invalid)
            - Boolean indicating if parsing was successful
            - Original version string
    """
    try:
        return version.parse(version_string), True, version_string
    except version.InvalidVersion:
        return version_string, False, version_string

def custom_version_sort_key(ver_tuple):
    """Custom sorting key, prioritize semantic versions, sort invalid versions by string"""
    parsed_ver, is_valid_ver, original_ver = ver_tuple

    # 1st PRIORITY: Hardcode 'main' or 'main-latest' to be at the absolute top
    # The lower the tuple number, the higher it will be in the list
    if original_ver in ("main-latest", "main"):
        return (3, version.parse("99.999"), original_ver)
    
    # 2nd PRIORITY: "<version>-latest" should be sorted after "<version>" SemVer
    if "latest" in original_ver:
        match = re.search(r"(\d+(?:\.\d+)*)", original_ver)
        if match:
            base_ver = match.group(1)
            bump_ver = f"{base_ver}.999"
            return (2, version.parse(bump_ver), original_ver)


    # 3nd PRIORITY: Valid SemVer
    if is_valid_ver:
        return (2, parsed_ver, original_ver)
    
    # 4th PRIORITY: Invalid versions that still have numeric patterns
    # Try to match version pattern, e.g. "1.18-latest" -> "1.18"
    match = re.match(r"^(\d+(?:\.\d+)*)", original_ver)
    if match:
        try:
            # Extract numeric part and parse
            # After valid versions, but sorted by numeric part
            return (1, version.parse(match.group(1)), original_ver)
        
        except version.InvalidVersion:
            pass

    # 5th PRIORITY: Completely unparseable versions, sort by string
    return (0, original_ver, "")


if __name__ == "__main__":
    update_all_version_from_github_api()
    versions = list(get_all_version())
    version_tuples = []

    for v in versions:
        ver, is_valid, original = parse_version(v)
        version_tuples.append((ver, is_valid, original))

    # Sort using custom sorting key
    sorted_versions = sorted(version_tuples, key=custom_version_sort_key, reverse=True)

    with open("versions.txt", "w", encoding="utf-8") as file:
        for v_tuple in sorted_versions:
            _, _, original = v_tuple
            file.write(original + "\n")