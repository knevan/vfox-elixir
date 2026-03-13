import json
import requests
import re
import os
from packaging import version

def slim_down_releases(raw_release):
    slim_releases = []
    MAIN_IDENTIFIERS = {"main", "main-latest"}

    for release in raw_release:
        if release.get("draft", True):
            continue

        slim_assets = [
            {
                "name": asset.get("name", ""),
                "browser_download_url": asset.get("browser_download_url", "")
            }
            for asset in release.get("assets", [])
            if (
                (name := asset.get("name", "")).endswith((".zip", ".exe"))
                and not name.startswith("Docs")
            )
        ]

        tag_name = release.get("tag_name", "")
        release_name = release.get("name", "")

        is_main_release = tag_name in MAIN_IDENTIFIERS or release_name in MAIN_IDENTIFIERS

        if slim_assets or is_main_release:
            slim_releases.append({
                "id": release.get("id"),
                "tag_name": tag_name,
                "target_commitish": release.get("target_commitish"),
                "name": release_name,
                "prerelease": release.get("prerelease", False),
                "published_at": release.get("published_at", ""),
                "tarball_url": release.get("tarball_url"),
                "zipball_url": release.get("zipball_url"),
                "assets": slim_assets
            })
            
    return slim_releases

# fetch version: -> https://docs.github.com/en/rest/releases/releases?apiVersion=2022-11-28
# github api has rate limt
# prefer use local version file
def update_all_version_from_github_api():
    all_version = []
    success = False
    github_token = os.getenv("GITHUB_TOKEN")
    headers = {}

    if github_token:
        headers["Authorization"] = f"token {github_token}"
        headers["Accept"] = "application/vnd.github+json"
    
    for page in range(1, 10):
        url = f"https://api.github.com/repos/elixir-lang/elixir/releases?page={page}&per_page=100"
        try:
            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code == 403:
                print("Hint: GitHub API rate limit reached. Use GITHUB_TOKEN to increase limits.")
                break

            if response.status_code != 200:
                print(f"Failed to fetch data from github api, status: {response.status_code}")
                break
        
            data = response.json()

            if not data:
                success = True
                break

            optimized_data = slim_down_releases(data)
            all_version.extend(optimized_data)
            success = True
        
        except requests.exceptions.RequestException as e:
            print(f"Network error occurred: {e}")
            break

    if success and all_version:
        with open(
            "elixir_windows_versions_from_github_api.json", "w", encoding="utf-8"
        ) as file:
            json.dump(all_version, file, indent=4)
            print(f"Successfully updated elixir_windows_versions_from_github_api.json with {len(all_version)} items.")
    else:
        print("Warning: Skipping update to prevent data loss due to API failure/empty data.")


def get_all_version():
    version_set = set()
    IDENTIFIER = {"main", "main-latest"}

    with open(
        "elixir_windows_versions_from_github_api.json", "r", encoding="utf-8"
    ) as file:
        data = json.load(file)

        for item in data:
            is_main = item.get("tag_name", "") in IDENTIFIER or item.get("name", "") in IDENTIFIER

            for asset in item.get("assets", []):
                url = asset.get("browser_download_url", "")
                name = asset.get("name", "")

                if not url.endswith(".exe"):
                    continue

                # Handle special case for 'main' release assets
                if is_main:
                    # Target asset: 'elixir-otp-*.exe'
                    # Convert to string: 'main-latest-elixir-otp-*'
                    pure_asset_name = name.removesuffix(".exe")
                    version_set.add(f"main-latest-{pure_asset_name}")
                    continue

                # Handle normal semantic releases
                # Extract URL into structured string e.g: v1.19.0/elixir-otp-26.exe
                _, separator, after_separator = url.partition("releases/download/")
                if separator:
                    pure_version = after_separator.removesuffix(".exe").replace("/", "-").lstrip("v")
                    
                    version_set.add(pure_version)

    return version_set

def extract_otp_value(ver_str):
    """Extract OTP integer from version string. Returns 0 if not found."""
    match = re.search(r"otp-(\d+)", ver_str)
    return int(match.group(1)) if match else 0

def custom_win_version_sort_key(ver_str):
    """Sort key appropriately handling Semantic Versioning appending with OTP prefixes.
    
    Instead of standard string sorting (`sorted(v, reverse=True)`) which will fail 
    when comparing 1.9 > 1.20, this properly maps combinations.
    """
    otp_val = extract_otp_value(ver_str)

    # 1st PRIORITY: 'main-latest' block at the absolute top
    if ver_str.startswith("main-latest") or ver_str.startswith("main"):
        # Priority 3 (Highest integer priority) -> Valid SemVers use 2.
        # This guarantees it sits above any standard versions during a reverse sort.
        return (3, "main-latest", otp_val)

    # 2nd PRIORITY: Valid Semantic Versions patterns like: 1.20.0-rc.2-elixir-otp-28
    match = re.match(r"^(.*?)-elixir-(otp-.*)$", ver_str)
    if match:
        sem_ver = match.group(1)
        otp = match.group(2)

        try:
            return (2, version.parse(sem_ver), otp)
        except version.InvalidVersion:
            return (1, ver_str, "")

    # Fallback sequentially without OTP pattern
    try:
        return (2, version.parse(ver_str), "")
    except version.InvalidVersion:
        return (0, ver_str, "")

if __name__ == "__main__":
    update_all_version_from_github_api()
    versions = list(get_all_version())

    versions = sorted(versions, key=custom_win_version_sort_key, reverse=True)
    
    with open("versions_win.txt", "w") as file:
        for v in versions:
            file.write(v + "\n")