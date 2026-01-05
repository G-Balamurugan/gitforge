# GitForge

> **A Modern Version Control System Built on Graph Theory and Algorithmic Efficiency**

GitForge is a high-performance version control system implemented in Python that leverages advanced algorithms for superior merge operations and conflict detection. Built from first principles, GitForge demonstrates how fundamental data structures and graph algorithms can power a robust, production-ready VCS.

---

## Table of Contents

- [Key Innovations](#key-innovations)
- [Algorithmic Advantages](#algorithmic-advantages)
  - [Bidirectional BFS for Merge-Base Detection](#1-bidirectional-bfs-for-merge-base-detection-lca)
  - [Three-Way Merge with diff3](#2-three-way-merge-with-diff3-integration)
  - [Typed Conflict Classification](#3-typed-conflict-classification)
  - [Unified Commit Application](#4-unified-commit-application-architecture)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage Guide](#usage-guide)
- [Command Reference](#command-reference)
- [Technical Deep Dive](#technical-deep-dive)
- [Testing](#testing)
- [Project Structure](#project-structure)

---

## Key Innovations

| Feature | GitForge Approach | Technical Advantage |
|---------|-------------------|---------------------|
| **Merge-Base Detection** | Bidirectional BFS | O(b^(d/2)) vs O(b^d) - exponentially faster for deep histories |
| **Conflict Detection** | Typed conflict taxonomy | Precise conflict classification enables targeted resolution strategies |
| **Merge Engine** | True 3-way merge with `diff3` | Produces conflict markers with base context for informed resolution |
| **Index Format** | Rich JSON with state metadata | Supports conflict tracking, type classification, and multi-stage data |
| **Object Storage** | SHA-1 content-addressing with zlib | Efficient deduplication and compression |

---

## Algorithmic Advantages

### 1. Bidirectional BFS for Merge-Base Detection (LCA)

GitForge implements the **Lowest Common Ancestor (LCA)** algorithm using **Bidirectional Breadth-First Search**, a technique that provides exponential speedup over traditional single-direction traversal.

#### The Problem

In version control, finding the merge-base (the most recent common ancestor of two commits) is fundamental to all merge operations. Given the commit DAG (Directed Acyclic Graph), we need to find where two branches diverged.

#### Traditional Approach

Standard BFS from one node toward ancestors has time complexity **O(b^d)** where:
- `b` = average branching factor
- `d` = distance to common ancestor

#### GitForge's Bidirectional BFS

```
                     ┌─────┐
            ┌───────▶│  A  │◀───────┐
            │        └─────┘        │
        ┌───┴───┐               ┌───┴───┐
        │ HEAD  │               │ other │
        └───┬───┘               └───┬───┘
            │                       │
      Frontier 1              Frontier 2
      expands UP              expands UP
            │                       │
            └───────▶ LCA ◀─────────┘
                   (Meeting Point)
```

**Algorithm:**

```python
def get_merge_base(oid1, oid2):
    # Bidirectional BFS - O(b^(d/2)) instead of O(b^d)
    visited1, visited2 = {oid1}, {oid2}
    frontier1, frontier2 = deque([oid1]), deque([oid2])

    while frontier1 or frontier2:
        # Expand from branch 1
        if frontier1:
            current = frontier1.popleft()
            if current in visited2:
                return current  # Found LCA
            for parent in get_commit(current).parents:
                if parent not in visited1:
                    visited1.add(parent)
                    frontier1.append(parent)

        # Expand from branch 2 (symmetric)
        if frontier2:
            current = frontier2.popleft()
            if current in visited1:
                return current  # Found LCA
            for parent in get_commit(current).parents:
                if parent not in visited2:
                    visited2.add(parent)
                    frontier2.append(parent)

    return None  # No common ancestor
```

**Complexity Analysis:**

| Approach | Time Complexity | For d=20, b=2 |
|----------|-----------------|---------------|
| Single-direction BFS | O(b^d) | 1,048,576 nodes |
| Bidirectional BFS | O(b^(d/2)) | 1,024 nodes |

This represents a **1000x improvement** for typical repository depths.

---

### 2. Three-Way Merge with diff3 Integration

GitForge implements **true 3-way merge** using the `diff3` algorithm, which provides superior conflict resolution compared to simple 2-way diff.

#### Why 3-Way Merge?

```
         BASE (common ancestor)
            │
    ┌───────┴───────┐
    │               │
   HEAD          OTHER
 (current)      (incoming)
```

A 3-way merge compares:
1. **BASE ↔ HEAD**: What did the current branch change?
2. **BASE ↔ OTHER**: What did the incoming branch change?
3. **HEAD ↔ OTHER**: Do these changes conflict?

#### Conflict Marker Output

When conflicts occur, GitForge produces clear, contextual markers:

```
<<<<<<< HEAD
current branch content
||||||| BASE
original content (context for resolution)
=======
incoming branch content
>>>>>>> MERGE_HEAD
```

The inclusion of `BASE` content (middle section) provides crucial context that helps developers understand *why* a conflict occurred, not just *what* the conflicting content is.

---

### 3. Typed Conflict Classification

GitForge implements a **typed conflict taxonomy** that precisely categorizes merge conflicts, enabling more intelligent resolution strategies.

#### Conflict Types

| Type | Scenario | Description |
|------|----------|-------------|
| `content_conflict` | Both modified same file | Classic merge conflict with differing changes |
| `add_add` | Both added same file | Same filename, different content |
| `current_delete_target_modify` | HEAD deleted, OTHER modified | File removed locally but changed remotely |
| `current_modify_target_delete` | HEAD modified, OTHER deleted | File changed locally but removed remotely |

#### Rich Index Format

```json
{
  "path/to/file.py": {
    "state": "conflict",
    "type": "content_conflict",
    "oid": "abc123...",
    "base": "def456...",
    "head": "ghi789...",
    "other": "jkl012..."
  }
}
```

This rich metadata enables:
- Precise status reporting
- Type-specific resolution workflows
- Full reconstruction of merge state

---

### 4. Unified Commit Application Architecture

GitForge uses a **shared commit application pattern** for cherry-pick and rebase operations, eliminating code duplication and ensuring consistent behavior.

```
                    ┌─────────────────┐
                    │  _apply_commit  │
                    │  (shared core)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
        ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
        │cherry-pick│  │  rebase   │  │_finish_   │
        │           │  │  replay   │  │  apply    │
        └───────────┘  └───────────┘  └───────────┘
```

**Benefits:**
- Single implementation for 3-way merge logic
- Consistent conflict handling across operations
- Author preservation for both operations
- Unified empty-commit detection

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          CLI Layer                                │
│                         (cli.py)                                  │
│  Argument parsing, command dispatch, user-facing output          │
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│                      Repository Layer                             │
│                      (repository.py)                              │
│  Core VCS operations: commit, merge, rebase, cherry-pick          │
│  Graph algorithms: BFS, LCA, commit iteration                     │
└───────────┬──────────────────────────────────┬───────────────────┘
            │                                  │
┌───────────▼───────────┐          ┌───────────▼───────────────────┐
│   Diff Engine         │          │   Objects Layer               │
│   (diff_engine.py)    │          │   (objects.py)                │
│                       │          │                               │
│ • Tree comparison     │          │ • Content-addressable store   │
│ • 3-way merge         │          │ • Reference management        │
│ • diff3 integration   │          │ • Index (staging area)        │
│ • Conflict detection  │          │ • Configuration               │
└───────────────────────┘          └───────────────────────────────┘
                                               │
┌──────────────────────────────────────────────▼───────────────────┐
│                       Remote Layer                                │
│                       (remotes.py)                                │
│  Object transfer, ref synchronization, push safety               │
└──────────────────────────────────────────────────────────────────┘
```

---

## Installation

### Prerequisites

- Python 3.8+
- `diff` utility (standard on Unix/macOS/Linux)
- `diff3` utility (for merge operations)
- `graphviz` (optional, for commit visualization)

### Install from Source

```bash
# Clone the repository
git clone https://github.com/gitforge/gitforge.git
cd gitforge

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Verify installation
gitforge --help
```

### Install with pip

```bash
pip install gitforge
```

---

## Usage Guide

### Getting Started

```bash
# Initialize a new repository
mkdir my-project && cd my-project
gitforge init

# Configure user identity
gitforge config user.name "Your Name"
gitforge config user.email "you@example.com"

# Create and stage files
echo "Hello, GitForge!" > README.md
gitforge add README.md

# Commit changes
gitforge commit -m "Initial commit"
```

### Branching and Merging

```bash
# Create a new branch
gitforge branch feature-x

# Switch to branch
gitforge checkout feature-x

# Make changes and commit
echo "New feature" > feature.txt
gitforge add feature.txt
gitforge commit -m "Add feature X"

# Switch back and merge
gitforge checkout master
gitforge merge feature-x
```

### Handling Merge Conflicts

```bash
# When merge conflicts occur
gitforge merge feature-branch
# Output: CONFLICT in file.txt

# Check status for conflict details
gitforge status
# Shows: both modified: file.txt (content_conflict)

# Edit conflicted files, resolve markers
# Stage resolved files
gitforge add file.txt

# Complete the merge
gitforge commit -m "Merge feature-branch"
```

### Cherry-Pick Workflow

```bash
# Apply a specific commit to current branch
gitforge cherry-pick abc1234

# If conflicts occur:
# 1. Resolve conflicts
# 2. gitforge add <files>
# 3. gitforge cherry-pick --continue

# Or abort:
gitforge cherry-pick --abort
```

### Interactive Rebase

```bash
# Rebase current branch onto master
gitforge rebase master

# If conflicts during replay:
# 1. Resolve conflicts
# 2. gitforge add <files>
# 3. gitforge rebase --continue

# Or abort entire rebase:
gitforge rebase --abort
```

---

## Command Reference

### Repository Management

| Command | Description |
|---------|-------------|
| `gitforge init` | Initialize new repository in current directory |
| `gitforge config <key> [value]` | Get/set configuration values |

### Staging and Commits

| Command | Description |
|---------|-------------|
| `gitforge add <files...>` | Stage files for commit |
| `gitforge commit -m <message>` | Create new commit with staged changes |
| `gitforge status` | Show working tree and staging status |

### History and Inspection

| Command | Description |
|---------|-------------|
| `gitforge log [commit]` | Show commit history from specified commit |
| `gitforge show [commit]` | Show commit details and diff |
| `gitforge diff [--cached] [commit]` | Show changes between trees |
| `gitforge cat-file <oid>` | Output contents of object |

### Branching and Tags

| Command | Description |
|---------|-------------|
| `gitforge branch [name] [start]` | List or create branches |
| `gitforge checkout <ref>` | Switch HEAD to branch or commit |
| `gitforge tag <name> [oid]` | Create lightweight tag |

### Merging and Integration

| Command | Description |
|---------|-------------|
| `gitforge merge <commit>` | Merge commit into current branch |
| `gitforge merge --abort` | Abort in-progress merge |
| `gitforge merge-base <c1> <c2>` | Find common ancestor (LCA) |
| `gitforge cherry-pick <commit>` | Apply single commit |
| `gitforge rebase <upstream>` | Rebase onto upstream |

### Reset and Undo

| Command | Description |
|---------|-------------|
| `gitforge reset [--soft\|--mixed\|--hard] <commit>` | Reset HEAD to commit |

### Remote Operations

| Command | Description |
|---------|-------------|
| `gitforge fetch <remote>` | Fetch objects and refs from remote |
| `gitforge push <remote> <branch>` | Push branch to remote |

### Low-Level Commands

| Command | Description |
|---------|-------------|
| `gitforge hash-object <file>` | Compute object hash and store |
| `gitforge write-tree` | Write index to tree object |
| `gitforge read-tree <tree>` | Read tree into index |
| `gitforge k` | Visualize commit graph (requires graphviz) |

---

## Technical Deep Dive

### Object Storage

GitForge uses content-addressable storage with SHA-1 hashing:

```
.gitforge/objects/
├── ab/
│   └── cdef1234...  (compressed blob/tree/commit)
├── 12/
│   └── 345678...    (another object)
```

Objects are compressed with zlib and prefixed with type information:

```
<type>\x00<content>
```

### Reference System

References are stored as files with either:
- **Direct reference**: Contains SHA-1 of commit
- **Symbolic reference**: Contains `ref: <other-ref>`

```
.gitforge/
├── HEAD              # ref: refs/heads/master
├── MERGE_HEAD        # SHA1 (during merge)
├── ORIG_HEAD         # SHA1 (backup for abort)
├── CHERRY_PICK_HEAD  # SHA1 (during cherry-pick)
└── refs/
    ├── heads/
    │   ├── master    # SHA1
    │   └── feature   # SHA1
    └── tags/
        └── v1.0      # SHA1
```

### Index (Staging Area)

The index is stored as JSON with rich metadata:

```json
{
  "src/main.py": {
    "state": "clear",
    "oid": "abc123def456..."
  },
  "src/utils.py": {
    "state": "conflict",
    "type": "content_conflict",
    "oid": "merged-with-markers...",
    "base": "original-oid",
    "head": "current-oid",
    "other": "incoming-oid"
  }
}
```

### Commit Format

```
tree <tree-sha1>
parent <parent-sha1>
parent <parent2-sha1>     # For merge commits
author <name> <email> <timestamp> <tz>
committer <name> <email> <timestamp> <tz>

<commit message>
```

---

## Testing

GitForge includes a comprehensive functional test suite covering all operations:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test class
python -m pytest tests/functional/test_gitforge.py::TestMerge -v

# Run with coverage
python -m pytest tests/ --cov=gitforge --cov-report=html
```

### Test Categories

- **Basic Operations**: init, hash-object, cat-file, add, commit
- **Tree Operations**: write-tree, read-tree
- **Branching**: branch, checkout, tag
- **History**: log, show, diff
- **Integration**: merge, cherry-pick, rebase
- **Remotes**: fetch, push
- **Conflict Handling**: All conflict types with resolution

---

## Project Structure

```
gitforge/
├── gitforge/
│   ├── __init__.py       # Package marker
│   ├── cli.py            # Command-line interface and argument parsing
│   ├── repository.py     # Core VCS logic and graph algorithms
│   ├── objects.py        # Object storage, refs, index management
│   ├── diff_engine.py    # Tree comparison and 3-way merge
│   └── remotes.py        # Remote operations (fetch/push)
├── tests/
│   └── functional/
│       └── test_gitforge.py  # Comprehensive functional tests
├── pyproject.toml        # Project configuration and dependencies
└── README.md             # This file
```

### Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| `cli.py` | Argument parsing, command dispatch, output formatting |
| `repository.py` | Commit graph operations, merge logic, rebase/cherry-pick |
| `objects.py` | Object storage, reference management, index, config |
| `diff_engine.py` | Tree comparison, diff generation, 3-way merge |
| `remotes.py` | Object transfer, ref synchronization |

---

## Contributing

1. Fork the repository
2. Create a feature branch (`gitforge checkout -b feature/amazing-feature`)
3. Commit your changes (`gitforge commit -m 'Add amazing feature'`)
4. Push to the branch (`gitforge push origin feature/amazing-feature`)
5. Open a Pull Request

---

## Acknowledgments

GitForge demonstrates that version control systems can be built on solid algorithmic foundations. The bidirectional BFS for LCA detection, true 3-way merge with diff3, and typed conflict classification represent deliberate design choices that prioritize both correctness and performance.

---

<p align="center">
  <strong>GitForge</strong> — Version Control, Reforged
</p>

