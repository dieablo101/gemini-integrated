"""Autonomous project scaffolding engine with Git initialization and Kyle Gallagher copyright."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Dict, Optional, Union

from gemini_app.config import (
    DEFAULT_COPYRIGHT_HOLDER,
    PROJECTS_DIR,
    STATE_FILE,
)


def get_user_realname() -> str:
    """Retrieves the real name of the user from state, defaulting to Kyle Gallagher."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            stored_name = data.get("user_realname") or data.get("user_real_name") or data.get("copyright_name")
            if stored_name and str(stored_name).strip():
                return str(stored_name).strip()
        except Exception:
            pass
    return DEFAULT_COPYRIGHT_HOLDER


get_user_real_name = get_user_realname


def set_user_realname(realname: str) -> str:
    """Persists the user's real name for copyright in state.json."""
    clean_name = realname.strip() if realname else DEFAULT_COPYRIGHT_HOLDER
    try:
        data: dict = {}
        if STATE_FILE.exists():
            try:
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["user_realname"] = clean_name
        data["user_real_name"] = clean_name
        data["copyright_name"] = clean_name
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        STATE_FILE.chmod(0o600)
    except Exception:
        pass
    return clean_name


set_user_real_name = set_user_realname


# Camel / snake-case aliases for consistent access
get_user_real_name = get_user_realname
set_user_real_name = set_user_realname


def generate_mit_license(copyright_holder: str, year: Optional[int] = None) -> str:
    """Generates a standard MIT LICENSE text with the designated copyright holder."""
    yr = year or datetime.now().year
    return f"""MIT License

Copyright (c) {yr} {copyright_holder}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def generate_readme(project_name: str, description: str, copyright_holder: str, year: Optional[int] = None) -> str:
    """Generates a standard clean README.md for a newly scaffolded project."""
    yr = year or datetime.now().year
    desc_block = description.strip() if description else f"{project_name} - Built with Gemini Integrated."
    return f"""# {project_name}

{desc_block}

## Getting Started

This project was scaffolded in `~/Projects/{project_name}` by Gemini Integrated.

### Prerequisites
- Python 3.10+ (or relevant runtime)

### Running
```bash
# Add execution or build instructions here
```

## License

Copyright (c) {yr} {copyright_holder}. All rights reserved.
Licensed under the [MIT License](LICENSE).
"""


def generate_gitignore() -> str:
    """Generates standard sensible default .gitignore."""
    return """# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.venv/
venv/
ENV/
env/

# IDE & Editor configs
.vscode/
.idea/
*.swp
*~

# Environment & local credentials
.env
*.local
"""


def scaffold_project(
    name: str = "",
    project_name: str = "",
    description: str = "",
    realname: Optional[str] = None,
    author: Optional[str] = None,
    git_init: bool = True,
    init_git: bool = True,
    target_dir: Optional[Union[str, Path]] = None,
    license_type: str = "MIT",
) -> Dict[str, Any]:
    """Scaffolds a new project directory with Git, README.md, and MIT LICENSE.

    - Target directory defaults to ~/Projects/<name>
    - Copyright defaults to 'Kyle Gallagher' (or user realname in state)
    - Automatically initializes git repo and creates initial commit if git is available.
    """
    effective_name = (name or project_name).strip()
    if not effective_name:
        return {"status": "error", "message": "Project name cannot be empty."}

    holder = (realname or author or get_user_realname()).strip()
    if not holder:
        holder = DEFAULT_COPYRIGHT_HOLDER

    # Save realname in state
    set_user_realname(holder)

    base_dir = PROJECTS_DIR
    base_dir.mkdir(parents=True, exist_ok=True)

    if target_dir:
        dest_dir = Path(os.path.expanduser(str(target_dir))).resolve()
    else:
        dest_dir = (base_dir / effective_name).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)

    created_files: list[str] = []

    # 1. LICENSE
    license_file = dest_dir / "LICENSE"
    if not license_file.exists():
        license_content = generate_mit_license(holder)
        license_file.write_text(license_content, encoding="utf-8")
        created_files.append("LICENSE")

    # 2. README.md
    readme_file = dest_dir / "README.md"
    if not readme_file.exists():
        readme_content = generate_readme(effective_name, description, holder)
        readme_file.write_text(readme_content, encoding="utf-8")
        created_files.append("README.md")

    # 3. .gitignore
    gitignore_file = dest_dir / ".gitignore"
    if not gitignore_file.exists():
        gitignore_file.write_text(generate_gitignore(), encoding="utf-8")
        created_files.append(".gitignore")

    # 4. Git Initialization & Initial Commit
    effective_git = git_init and init_git
    git_status = "disabled"
    if effective_git:
        git_bin = shutil.which("git")
        if git_bin:
            try:
                # git init
                if not (dest_dir / ".git").exists():
                    subprocess.run([git_bin, "init"], cwd=str(dest_dir), check=True, capture_output=True, text=True)
                    git_status = "initialized"
                else:
                    git_status = "already_initialized"

                # Check if there are commits
                rev_res = subprocess.run([git_bin, "rev-parse", "--verify", "HEAD"], cwd=str(dest_dir), capture_output=True)
                if rev_res.returncode != 0:
                    # Stash / commit initial files
                    subprocess.run([git_bin, "add", "."], cwd=str(dest_dir), check=True, capture_output=True)
                    commit_msg = f"Initial scaffold for {effective_name}"
                    subprocess.run([git_bin, "commit", "-m", commit_msg], cwd=str(dest_dir), check=True, capture_output=True)
                    git_status = "committed"
            except Exception as e:
                git_status = f"error: {e}"
        else:
            git_status = "git_not_installed"

    return {
        "status": "success",
        "project_name": effective_name,
        "path": str(dest_dir),
        "project_path": str(dest_dir),
        "author": holder,
        "realname": holder,
        "copyright_holder": holder,
        "created_files": created_files,
        "git": git_status,
        "git_initialized": git_status in ("initialized", "committed", "already_initialized"),
        "message": f"Project '{effective_name}' successfully scaffolded at {dest_dir} with Copyright {holder}."
    }
