#!/usr/bin/env python3
"""
Generate a file tree of the repository.
Respects .gitignore patterns and outputs to docs/FILE_TREE.md
"""
import os
import subprocess
from pathlib import Path
from datetime import datetime


def get_git_root():
    """Get the git repository root directory."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            capture_output=True,
            text=True,
            check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return Path.cwd()


def is_ignored(path: Path, git_root: Path) -> bool:
    """Check if a path is ignored by git."""
    try:
        rel_path = path.relative_to(git_root)
        result = subprocess.run(
            ['git', 'check-ignore', str(rel_path)],
            cwd=git_root,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except (subprocess.CalledProcessError, ValueError):
        return False


def get_file_count(directory: Path) -> int:
    """Count files in a directory (non-recursive)."""
    try:
        return len([f for f in directory.iterdir() if f.is_file()])
    except PermissionError:
        return 0


def generate_tree(directory: Path, git_root: Path, prefix: str = "", is_last: bool = True) -> list:
    """Generate tree structure recursively."""
    lines = []
    
    # Get all items in directory
    try:
        items = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return lines
    
    # Filter out ignored items
    items = [item for item in items if not is_ignored(item, git_root)]
    
    for i, item in enumerate(items):
        is_last_item = i == len(items) - 1
        
        # Determine the connector
        connector = "└── " if is_last_item else "├── "
        
        if item.is_dir():
            # Directory
            file_count = get_file_count(item)
            dir_name = f"{item.name}/ ({file_count} files)"
            lines.append(f"{prefix}{connector}{dir_name}")
            
            # Recurse into subdirectory
            extension = "    " if is_last_item else "│   "
            lines.extend(generate_tree(item, git_root, prefix + extension, is_last_item))
        else:
            # File
            try:
                file_size = item.stat().st_size
                size_str = format_size(file_size)
                lines.append(f"{prefix}{connector}{item.name} ({size_str})")
            except (FileNotFoundError, OSError):
                # Broken symlink or inaccessible file
                lines.append(f"{prefix}{connector}{item.name} (broken link)")
    
    return lines


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def count_files_recursive(directory: Path, git_root: Path) -> tuple:
    """Count total files and directories recursively."""
    file_count = 0
    dir_count = 0
    
    try:
        for item in directory.rglob('*'):
            if is_ignored(item, git_root):
                continue
            if item.is_file():
                file_count += 1
            elif item.is_dir():
                dir_count += 1
    except PermissionError:
        pass
    
    return file_count, dir_count


def get_git_info(git_root: Path) -> dict:
    """Get git repository information."""
    info = {
        'remote_url': None,
        'branch': None,
    }
    
    try:
        # Get remote URL
        result = subprocess.run(
            ['git', 'remote', 'get-url', 'origin'],
            cwd=git_root,
            capture_output=True,
            text=True,
            check=True
        )
        info['remote_url'] = result.stdout.strip()
        
        # Get current branch
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=git_root,
            capture_output=True,
            text=True,
            check=True
        )
        info['branch'] = result.stdout.strip()
    except subprocess.CalledProcessError:
        pass
    
    return info


def main():
    git_root = get_git_root()
    output_file = git_root / "docs" / "FILE_TREE.md"
    
    print(f"📁 Generating file tree for: {git_root}")
    print(f"📝 Output file: {output_file}")
    
    # Get git info
    git_info = get_git_info(git_root)
    
    # Count totals
    total_files, total_dirs = count_files_recursive(git_root, git_root)
    
    # Generate tree
    tree_lines = generate_tree(git_root, git_root)
    
    # Format GitHub URL
    github_section = ""
    if git_info['remote_url']:
        # Convert git URL to https if needed
        repo_url = git_info['remote_url'].replace('.git', '')
        if repo_url.startswith('git@github.com:'):
            repo_url = repo_url.replace('git@github.com:', 'https://github.com/')
        
        github_section = f"""
## GitHub Repository

**Repository:** [{repo_url}]({repo_url})  
**Branch:** `{git_info['branch'] or 'unknown'}`  
**MCP Path:** `mcp://github/{repo_url.replace('https://github.com/', '')}`
"""
    
    # Create markdown content
    content = f"""# Repository File Tree

**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}  
**Total Files:** {total_files}  
**Total Directories:** {total_dirs}
{github_section}

## Structure

```
{git_root.name}/
"""
    
    for line in tree_lines:
        content += line + "\n"
    
    content += """```

---

## Notes

- This file is auto-generated by `scripts/docs/generate_file_tree.py`
- Respects `.gitignore` patterns
- File sizes shown in parentheses
- Directory counts show immediate children only

## Regenerate

To update this file:

```bash
python3 scripts/docs/generate_file_tree.py
```

Or add to your git pre-commit hook for automatic updates.
"""
    
    # Write to file
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(content)
    
    print(f"✅ File tree generated successfully!")
    print(f"   Files: {total_files}")
    print(f"   Directories: {total_dirs}")
    print(f"   Output: {output_file}")


if __name__ == "__main__":
    main()
