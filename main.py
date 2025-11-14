import os
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl

from utils.auth import create_auth0_verifier


# -----------------------------
# Load environment variables
# -----------------------------
load_dotenv()

auth0_domain = os.getenv("AUTH0_DOMAIN")
resource_server_url = os.getenv("RESOURCE_SERVER_URL")

if not auth0_domain:
    raise ValueError("AUTH0_DOMAIN environment variable is required")

if not resource_server_url:
    raise ValueError("RESOURCE_SERVER_URL environment variable is required")


# -----------------------------
# Load Website Instructions
# -----------------------------
script_dir = os.path.dirname(__file__)
instructions_path = os.path.join(script_dir, "prompts", "website_instructions.md")

with open(instructions_path, "r", encoding="utf-8") as f:
    server_instructions = f.read()


# -----------------------------
# Auth0 verifier
# -----------------------------
token_verifier = create_auth0_verifier()


# -----------------------------
# Initialize MCP server
# -----------------------------
mcp = FastMCP(
    "website-builder-mcp",
    instructions=server_instructions,
    host="0.0.0.0",
    token_verifier=token_verifier,
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(f"https://{auth0_domain}/"),
        resource_server_url=AnyHttpUrl(resource_server_url),
        required_scopes=["openid", "profile", "email", "address", "phone"],
    ),
)


# =============================================================================
# Website Builder Logic
# =============================================================================

WEBSITE_DIR = "website"
FILES = ["index.html", "styles.css", "script.js"]


def ensure_files_exist():
    """Create website folder and required files if missing."""
    if not os.path.exists(WEBSITE_DIR):
        os.makedirs(WEBSITE_DIR)

    created = []
    for file in FILES:
        path = os.path.join(WEBSITE_DIR, file)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("")  # empty file
            created.append(file)

    return {"created": created}


def read_file(file: str):
    """Return full contents of a file."""
    path = os.path.join(WEBSITE_DIR, file)

    if not os.path.exists(path):
        return {"error": f"{file} does not exist"}

    with open(path, "r", encoding="utf-8") as f:
        return {"file": file, "content": f.read()}


def write_file(file: str, content: str):
    """Replace entire file content."""
    path = os.path.join(WEBSITE_DIR, file)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return {"status": "ok", "file": file}


def update_file(file: str, changes: list):
    """
    Apply line-level file updates.

    Each change dict format:
    {
        "action": "replace" | "insert" | "delete",
        "line": <0-indexed line number>,
        "content": "optional string"
    }
    """
    path = os.path.join(WEBSITE_DIR, file)

    if not os.path.exists(path):
        return {"error": f"{file} does not exist"}

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for change in changes:
        action = change.get("action")
        line = change.get("line")
        content = change.get("content", "")

        if action == "replace":
            if 0 <= line < len(lines):
                lines[line] = content + "\n"

        elif action == "insert":
            if 0 <= line <= len(lines):
                lines.insert(line, content + "\n")

        elif action == "delete":
            if 0 <= line < len(lines):
                lines.pop(line)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return {"status": "ok", "file": file, "changes": changes}


def get_website_state():
    """Return contents of all 3 website files."""
    ensure_files_exist()

    state = {}
    for file in FILES:
        path = os.path.join(WEBSITE_DIR, file)
        with open(path, "r", encoding="utf-8") as f:
            state[file] = f.read()

    return {"website": state}


# =============================================================================
# MCP Tools
# =============================================================================

@mcp.tool()
def ensure_website() -> dict:
    """Ensure website directory and 3 code files exist."""
    return ensure_files_exist()


@mcp.tool()
def get_website() -> dict:
    """
    Return full contents of:
    - index.html
    - styles.css
    - script.js

    LLMs should ALWAYS call this before making edits.
    """
    return get_website_state()


@mcp.tool()
def read_file_tool(file: str) -> dict:
    """Read a single file from the website project."""
    if file not in FILES:
        return {"error": f"Invalid file. Choose from: {FILES}"}
    return read_file(file)


@mcp.tool()
def write_file_tool(file: str, content: str) -> dict:
    """Replace entire file content (use for major rewrites)."""
    if file not in FILES:
        return {"error": f"Invalid file. Choose from: {FILES}"}
    return write_file(file, content)


@mcp.tool()
def update_file_tool(file: str, changes: list) -> dict:
    """
    Update small parts of a file line-by-line.

    Example:
    [
        {"action": "replace", "line": 2, "content": "<h1>Hello</h1>"},
        {"action": "insert", "line": 10, "content": "<p>New</p>"}
    ]
    """
    if file not in FILES:
        return {"error": f"Invalid file. Choose from: {FILES}"}
    return update_file(file, changes)


# =============================================================================
# Run MCP Server
# =============================================================================

if __name__ == "__main__":
    ensure_files_exist()
    print("Website Builder MCP running with Auth0 OAuth…")
    mcp.run(transport="streamable-http")
