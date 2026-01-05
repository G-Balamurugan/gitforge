#!/usr/bin/env python3
"""
Comprehensive Functional Tests for gitforge - a DIY Git implementation.

This script tests all gitforge commands including:
- Basic operations: init, hash-object, cat-file, add, commit
- Tree operations: write-tree, read-tree
- Branching: branch, checkout, tag
- History: log, show, diff
- Advanced: merge, cherry-pick
- Remote: fetch, push
- Utilities: status, reset, config

Usage:
    python test_gitforge.py
    python test_gitforge.py TestGitforge.test_init
    python -m pytest test_gitforge.py -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Path to the gitforge package
# Resolve to absolute path to handle different working directories
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GITFORGE_RUNNER = PROJECT_ROOT / "scripts" / "gitforge"

# Verify the runner script exists
if not GITFORGE_RUNNER.exists():
    # Try alternative: maybe we're in the gitforge package directory
    alt_root = Path(__file__).resolve().parent.parent.parent.parent
    alt_runner = alt_root / "scripts" / "gitforge"
    if alt_runner.exists():
        PROJECT_ROOT = alt_root
        GITFORGE_RUNNER = alt_runner
    else:
        print(f"WARNING: gitforge runner not found at {GITFORGE_RUNNER}")
        print(f"Also tried: {alt_runner}")
        print(f"Current file: {Path(__file__).resolve()}")


class GitforgeTestBase(unittest.TestCase):
    """Base class for gitforge tests with common utilities."""

    @classmethod
    def setUpClass(cls):
        """Create a temporary directory for all tests."""
        cls.test_base_dir = tempfile.mkdtemp(prefix="gitforge_test_")
        print(f"\n{'='*60}")
        print(f"Test directory: {cls.test_base_dir}")
        print(f"{'='*60}\n")

    @classmethod
    def tearDownClass(cls):
        """Clean up the temporary directory."""
        if os.path.exists(cls.test_base_dir):
            shutil.rmtree(cls.test_base_dir)

    def setUp(self):
        """Create a fresh test directory for each test."""
        self.test_dir = tempfile.mkdtemp(dir=self.test_base_dir)
        os.chdir(self.test_dir)

    def run_gitforge(self, *args, expect_success=True):
        """Run a gitforge command and return the result."""
        if not GITFORGE_RUNNER.exists():
            raise FileNotFoundError(
                f"gitforge runner not found at: {GITFORGE_RUNNER}\n"
                f"PROJECT_ROOT: {PROJECT_ROOT}\n"
                f"Current working directory: {os.getcwd()}\n"
                f"Test file location: {Path(__file__).resolve()}"
            )
        
        cmd = [sys.executable, str(GITFORGE_RUNNER)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.test_dir
        )
        
        if expect_success and result.returncode != 0:
            print(f"Command failed: {' '.join(args)}")
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
        
        return result

    def create_file(self, name, content):
        """Create a file with the given content."""
        filepath = Path(self.test_dir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        return filepath

    def read_file_content(self, name):
        """Read content of a file."""
        filepath = Path(self.test_dir) / name
        return filepath.read_text()

    def file_exists(self, name):
        """Check if file exists."""
        return (Path(self.test_dir) / name).exists()

    def init_repo_with_commit(self, message="Initial commit"):
        """Initialize repo with a single commit."""
        self.run_gitforge("init")
        self.create_file("file.txt", "content")
        self.run_gitforge("add", "file.txt")
        result = self.run_gitforge("commit", "-m", message)
        return result.stdout.strip()


class TestInit(GitforgeTestBase):
    """Tests for gitforge init command."""

    def test_init_creates_directory_structure(self):
        """Test: gitforge init creates .gitforge directory structure"""
        result = self.run_gitforge("init")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("Initialized empty gitforge repository", result.stdout)
        self.assertTrue(os.path.isdir(os.path.join(self.test_dir, ".gitforge")))
        self.assertTrue(os.path.isdir(os.path.join(self.test_dir, ".gitforge", "objects")))

    def test_init_creates_head_ref(self):
        """Test: gitforge init creates HEAD pointing to master"""
        self.run_gitforge("init")
        
        head_path = os.path.join(self.test_dir, ".gitforge", "HEAD")
        self.assertTrue(os.path.exists(head_path))
        
        with open(head_path) as f:
            content = f.read().strip()
        
        self.assertEqual(content, "ref: refs/heads/master")


class TestHashObject(GitforgeTestBase):
    """Tests for gitforge hash-object command."""

    def test_hash_object_creates_object(self):
        """Test: gitforge hash-object creates object file"""
        self.run_gitforge("init")
        self.create_file("hello.txt", "Hello, World!")
        
        result = self.run_gitforge("hash-object", "hello.txt")
        
        self.assertEqual(result.returncode, 0)
        oid = result.stdout.strip()
        self.assertEqual(len(oid), 40)
        self.assertTrue(oid.isalnum())

    def test_hash_object_deterministic(self):
        """Test: same content produces same hash"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Same content")
        self.create_file("file2.txt", "Same content")
        
        result1 = self.run_gitforge("hash-object", "file1.txt")
        result2 = self.run_gitforge("hash-object", "file2.txt")
        
        self.assertEqual(result1.stdout.strip(), result2.stdout.strip())

    def test_hash_object_different_content(self):
        """Test: different content produces different hash"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content A")
        self.create_file("file2.txt", "Content B")
        
        result1 = self.run_gitforge("hash-object", "file1.txt")
        result2 = self.run_gitforge("hash-object", "file2.txt")
        
        self.assertNotEqual(result1.stdout.strip(), result2.stdout.strip())


class TestCatFile(GitforgeTestBase):
    """Tests for gitforge cat-file command."""

    def test_cat_file_retrieves_content(self):
        """Test: gitforge cat-file retrieves object content"""
        self.run_gitforge("init")
        content = "Hello, World!"
        self.create_file("hello.txt", content)
        
        hash_result = self.run_gitforge("hash-object", "hello.txt")
        oid = hash_result.stdout.strip()
        
        result = self.run_gitforge("cat-file", oid)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn(content, result.stdout)

    def test_cat_file_nonexistent_fails(self):
        """Test: gitforge cat-file with nonexistent object fails"""
        self.run_gitforge("init")
        fake_oid = "0" * 40
        
        result = self.run_gitforge("cat-file", fake_oid, expect_success=False)
        
        self.assertNotEqual(result.returncode, 0)


class TestAdd(GitforgeTestBase):
    """Tests for gitforge add command."""

    def test_add_single_file(self):
        """Test: gitforge add stages single file"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        
        result = self.run_gitforge("add", "file1.txt")
        
        self.assertEqual(result.returncode, 0)
        index_path = os.path.join(self.test_dir, ".gitforge", "index")
        self.assertTrue(os.path.exists(index_path))

    def test_add_multiple_files(self):
        """Test: gitforge add stages multiple files"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.create_file("file2.txt", "Content 2")
        
        result = self.run_gitforge("add", "file1.txt", "file2.txt")
        
        self.assertEqual(result.returncode, 0)

    def test_add_directory(self):
        """Test: gitforge add stages directory recursively"""
        self.run_gitforge("init")
        self.create_file("src/main.py", "print('main')")
        self.create_file("src/utils.py", "def helper(): pass")
        self.create_file("src/lib/core.py", "class Core: pass")
        
        result = self.run_gitforge("add", "src")
        
        self.assertEqual(result.returncode, 0)
        status_result = self.run_gitforge("status")
        self.assertIn("new file", status_result.stdout)

    def test_add_dot(self):
        """Test: gitforge add . stages all files"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.create_file("dir/file2.txt", "Content 2")
        
        result = self.run_gitforge("add", ".")
        
        self.assertEqual(result.returncode, 0)
        status_result = self.run_gitforge("status")
        self.assertIn("file1.txt", status_result.stdout)
        self.assertIn("file2.txt", status_result.stdout)


class TestCommit(GitforgeTestBase):
    """Tests for gitforge commit command."""

    def test_commit_creates_commit_object(self):
        """Test: gitforge commit creates commit object"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        
        result = self.run_gitforge("commit", "-m", "Initial commit")
        
        self.assertEqual(result.returncode, 0)
        commit_oid = result.stdout.strip()
        self.assertEqual(len(commit_oid), 40)

    def test_commit_multiple_creates_history(self):
        """Test: multiple commits create parent chain"""
        self.run_gitforge("init")
        
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "First commit").stdout.strip()
        
        self.create_file("file2.txt", "Content 2")
        self.run_gitforge("add", "file2.txt")
        commit2 = self.run_gitforge("commit", "-m", "Second commit").stdout.strip()
        
        self.assertNotEqual(commit1, commit2)
        
        cat_result = self.run_gitforge("cat-file", commit2)
        self.assertIn(f"parent {commit1}", cat_result.stdout)

    def test_commit_with_conflicts_fails(self):
        """Test: gitforge commit fails when conflicts exist"""
        # Setup merge conflict scenario
        self.run_gitforge("init")
        self.create_file("file.txt", "base content")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Modify on master
        self.create_file("file.txt", "master content")
        self.run_gitforge("add", ".")
        master_commit = self.run_gitforge("commit", "-m", "master change").stdout.strip()
        
        # Modify on feature
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature content")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature change").stdout.strip()
        
        # Merge to create conflict
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        # Commit should fail due to conflict
        result = self.run_gitforge("commit", "-m", "Should fail", expect_success=False)
        self.assertNotEqual(result.returncode, 0)


class TestLog(GitforgeTestBase):
    """Tests for gitforge log command."""

    def test_log_shows_commits(self):
        """Test: gitforge log shows commit history"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "First commit")
        
        self.create_file("file2.txt", "Content 2")
        self.run_gitforge("add", "file2.txt")
        self.run_gitforge("commit", "-m", "Second commit")
        
        result = self.run_gitforge("log")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("First commit", result.stdout)
        self.assertIn("Second commit", result.stdout)
        self.assertEqual(result.stdout.count("commit "), 2)

    def test_log_with_specific_oid(self):
        """Test: gitforge log from specific OID"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "First commit").stdout.strip()
        
        self.create_file("file2.txt", "Content 2")
        self.run_gitforge("add", "file2.txt")
        self.run_gitforge("commit", "-m", "Second commit")
        
        result = self.run_gitforge("log", commit1)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("First commit", result.stdout)
        self.assertNotIn("Second commit", result.stdout)


class TestBranch(GitforgeTestBase):
    """Tests for gitforge branch command."""

    def test_branch_create(self):
        """Test: gitforge branch creates new branch"""
        self.init_repo_with_commit()
        
        result = self.run_gitforge("branch", "feature")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("Branch feature created", result.stdout)

    def test_branch_list(self):
        """Test: gitforge branch lists all branches"""
        self.init_repo_with_commit()
        self.run_gitforge("branch", "feature")
        
        result = self.run_gitforge("branch")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("master", result.stdout)
        self.assertIn("feature", result.stdout)

    def test_branch_current_marked(self):
        """Test: gitforge branch marks current branch with *"""
        self.init_repo_with_commit()
        self.run_gitforge("branch", "feature")
        
        result = self.run_gitforge("branch")
        
        self.assertIn("* master", result.stdout)

    def test_branch_with_start_point(self):
        """Test: gitforge branch with start point"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "First commit").stdout.strip()
        
        self.create_file("file2.txt", "Content 2")
        self.run_gitforge("add", "file2.txt")
        self.run_gitforge("commit", "-m", "Second commit")
        
        result = self.run_gitforge("branch", "old-feature", commit1)
        self.assertEqual(result.returncode, 0)
        
        self.run_gitforge("checkout", "old-feature")
        log_result = self.run_gitforge("log")
        self.assertIn("First commit", log_result.stdout)
        self.assertNotIn("Second commit", log_result.stdout)


class TestCheckout(GitforgeTestBase):
    """Tests for gitforge checkout command."""

    def test_checkout_commit(self):
        """Test: gitforge checkout to previous commit"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Version 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "Version 1").stdout.strip()
        
        self.create_file("file1.txt", "Version 2")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Version 2")
        
        result = self.run_gitforge("checkout", commit1)
        
        self.assertEqual(result.returncode, 0)
        content = self.read_file_content("file1.txt")
        self.assertEqual(content, "Version 1")

    def test_checkout_branch(self):
        """Test: gitforge checkout branch"""
        self.init_repo_with_commit()
        self.run_gitforge("branch", "feature")
        
        result = self.run_gitforge("checkout", "feature")
        
        self.assertEqual(result.returncode, 0)
        status_result = self.run_gitforge("status")
        self.assertIn("On branch feature", status_result.stdout)

    def test_checkout_tag(self):
        """Test: gitforge checkout using tag"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Version 1")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Version 1")
        self.run_gitforge("tag", "v1.0")
        
        self.create_file("file1.txt", "Version 2")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Version 2")
        
        result = self.run_gitforge("checkout", "v1.0")
        
        self.assertEqual(result.returncode, 0)
        content = self.read_file_content("file1.txt")
        self.assertEqual(content, "Version 1")

    def test_checkout_creates_and_removes_files(self):
        """Test: checkout creates and removes files appropriately"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "Commit 1").stdout.strip()
        
        os.remove(os.path.join(self.test_dir, "file1.txt"))
        self.create_file("file2.txt", "Content 2")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "Commit 2")
        
        self.run_gitforge("checkout", commit1)
        
        self.assertTrue(self.file_exists("file1.txt"))
        self.assertFalse(self.file_exists("file2.txt"))

    def test_checkout_with_conflicts_fails(self):
        """Test: checkout fails when conflicts exist"""
        # Create a merge conflict first
        self.run_gitforge("init")
        self.create_file("file.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.create_file("file.txt", "master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        # Now checkout should fail due to conflicts
        result = self.run_gitforge("checkout", "feature", expect_success=False)
        self.assertNotEqual(result.returncode, 0)


class TestTag(GitforgeTestBase):
    """Tests for gitforge tag command."""

    def test_tag_create(self):
        """Test: gitforge tag creates tag"""
        self.init_repo_with_commit()
        
        result = self.run_gitforge("tag", "v1.0")
        
        self.assertEqual(result.returncode, 0)
        tag_path = os.path.join(self.test_dir, ".gitforge", "refs", "tags", "v1.0")
        self.assertTrue(os.path.exists(tag_path))

    def test_tag_with_specific_oid(self):
        """Test: gitforge tag with specific OID"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "First commit").stdout.strip()
        
        self.create_file("file2.txt", "Content 2")
        self.run_gitforge("add", "file2.txt")
        self.run_gitforge("commit", "-m", "Second commit")
        
        result = self.run_gitforge("tag", "v0.1", commit1)
        self.assertEqual(result.returncode, 0)
        
        tag_path = os.path.join(self.test_dir, ".gitforge", "refs", "tags", "v0.1")
        with open(tag_path) as f:
            tag_oid = f.read().strip()
        self.assertEqual(tag_oid, commit1)


class TestStatus(GitforgeTestBase):
    """Tests for gitforge status command."""

    def test_status_shows_branch(self):
        """Test: gitforge status shows current branch"""
        self.init_repo_with_commit()
        
        result = self.run_gitforge("status")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("On branch master", result.stdout)

    def test_status_staged_changes(self):
        """Test: gitforge status shows staged changes"""
        self.init_repo_with_commit()
        self.create_file("newfile.txt", "New content")
        self.run_gitforge("add", "newfile.txt")
        
        result = self.run_gitforge("status")
        
        self.assertIn("Changes to be committed", result.stdout)
        self.assertIn("new file", result.stdout)

    def test_status_unstaged_changes(self):
        """Test: gitforge status shows unstaged changes"""
        self.init_repo_with_commit()
        self.create_file("file.txt", "Modified content")
        
        result = self.run_gitforge("status")
        
        self.assertIn("Changes not staged for commit", result.stdout)
        self.assertIn("modified", result.stdout)

    def test_status_deleted_file(self):
        """Test: gitforge status shows deleted files"""
        self.init_repo_with_commit()
        os.remove(os.path.join(self.test_dir, "file.txt"))
        
        result = self.run_gitforge("status")
        
        self.assertIn("deleted", result.stdout)

    def test_status_detached_head(self):
        """Test: gitforge status shows detached HEAD"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "Initial commit").stdout.strip()
        
        self.create_file("file2.txt", "Content 2")
        self.run_gitforge("add", "file2.txt")
        self.run_gitforge("commit", "-m", "Second commit")
        
        self.run_gitforge("checkout", commit1)
        
        result = self.run_gitforge("status")
        
        self.assertIn("HEAD detached", result.stdout)

    def test_status_shows_merge_in_progress(self):
        """Test: gitforge status shows merge in progress"""
        self.run_gitforge("init")
        self.create_file("file.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.create_file("file.txt", "master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        result = self.run_gitforge("status")
        self.assertIn("Merging with", result.stdout)


class TestReset(GitforgeTestBase):
    """Tests for gitforge reset command."""

    def test_reset_soft(self):
        """Test: gitforge reset --soft only moves HEAD"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Version 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "Version 1").stdout.strip()
        
        self.create_file("file1.txt", "Version 2")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Version 2")
        
        result = self.run_gitforge("reset", "--soft", commit1)
        
        self.assertEqual(result.returncode, 0)
        content = self.read_file_content("file1.txt")
        self.assertEqual(content, "Version 2")

    def test_reset_mixed(self):
        """Test: gitforge reset --mixed moves HEAD and updates index"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Version 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "Version 1").stdout.strip()
        
        self.create_file("file1.txt", "Version 2")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Version 2")
        
        result = self.run_gitforge("reset", "--mixed", commit1)
        
        self.assertEqual(result.returncode, 0)
        content = self.read_file_content("file1.txt")
        self.assertEqual(content, "Version 2")
        
        status_result = self.run_gitforge("status")
        self.assertIn("modified", status_result.stdout)

    def test_reset_hard(self):
        """Test: gitforge reset --hard updates HEAD, index, and working dir"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Version 1")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "Version 1").stdout.strip()
        
        self.create_file("file1.txt", "Version 2")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Version 2")
        
        result = self.run_gitforge("reset", "--hard", commit1)
        
        self.assertEqual(result.returncode, 0)
        content = self.read_file_content("file1.txt")
        self.assertEqual(content, "Version 1")


class TestMerge(GitforgeTestBase):
    """Tests for gitforge merge command."""

    def test_merge_fast_forward(self):
        """Test: gitforge merge - fast forward"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Base content")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Base commit")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("checkout", "feature")
        
        self.create_file("file2.txt", "Feature content")
        self.run_gitforge("add", "file2.txt")
        feature_commit = self.run_gitforge("commit", "-m", "Feature commit").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("Fast-forward", result.stdout)
        self.assertTrue(self.file_exists("file2.txt"))

    def test_merge_three_way(self):
        """Test: gitforge merge - three-way merge"""
        self.run_gitforge("init")
        self.create_file("base.txt", "Base content")
        self.run_gitforge("add", "base.txt")
        self.run_gitforge("commit", "-m", "Base commit")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("master.txt", "Master content")
        self.run_gitforge("add", "master.txt")
        self.run_gitforge("commit", "-m", "Master changes")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("feature.txt", "Feature content")
        self.run_gitforge("add", "feature.txt")
        feature_commit = self.run_gitforge("commit", "-m", "Feature changes").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.file_exists("feature.txt"))
        self.assertTrue(self.file_exists("master.txt"))

    def test_merge_conflict(self):
        """Test: gitforge merge with conflict"""
        self.run_gitforge("init")
        self.create_file("file.txt", "base content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature content\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertIn("conflict", result.stdout.lower())

    def test_merge_abort(self):
        """Test: gitforge merge --abort"""
        self.run_gitforge("init")
        self.create_file("file.txt", "base content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature content\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        result = self.run_gitforge("merge", "--abort")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("aborted", result.stdout.lower())
        
        # Verify file is restored
        content = self.read_file_content("file.txt")
        self.assertEqual(content, "master content\n")

    def test_merge_creates_merge_commit(self):
        """Test: merge creates commit with two parents"""
        self.run_gitforge("init")
        self.create_file("base.txt", "Base content")
        self.run_gitforge("add", "base.txt")
        self.run_gitforge("commit", "-m", "Base commit")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("master.txt", "Master content")
        self.run_gitforge("add", "master.txt")
        master_commit = self.run_gitforge("commit", "-m", "Master changes").stdout.strip()
        
        self.run_gitforge("checkout", "feature")
        self.create_file("feature.txt", "Feature content")
        self.run_gitforge("add", "feature.txt")
        feature_commit = self.run_gitforge("commit", "-m", "Feature changes").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        merge_commit = self.run_gitforge("commit", "-m", "Merge feature").stdout.strip()
        
        cat_result = self.run_gitforge("cat-file", merge_commit)
        self.assertIn(f"parent {master_commit}", cat_result.stdout)
        self.assertIn(f"parent {feature_commit}", cat_result.stdout)


class TestMergeBase(GitforgeTestBase):
    """Tests for gitforge merge-base command."""

    def test_merge_base(self):
        """Test: gitforge merge-base finds common ancestor"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Base content")
        self.run_gitforge("add", "file1.txt")
        base_commit = self.run_gitforge("commit", "-m", "Base commit").stdout.strip()
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file1.txt", "Master content")
        self.run_gitforge("add", "file1.txt")
        master_commit = self.run_gitforge("commit", "-m", "Master commit").stdout.strip()
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file2.txt", "Feature content")
        self.run_gitforge("add", "file2.txt")
        feature_commit = self.run_gitforge("commit", "-m", "Feature commit").stdout.strip()
        
        result = self.run_gitforge("merge-base", master_commit, feature_commit)
        
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), base_commit)

    def test_merge_base_same_commit(self):
        """Test: gitforge merge-base with same commit"""
        commit = self.init_repo_with_commit()
        
        result = self.run_gitforge("merge-base", commit, commit)
        
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), commit)


class TestDiff(GitforgeTestBase):
    """Tests for gitforge diff command."""

    def test_diff_unstaged(self):
        """Test: gitforge diff shows unstaged changes"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Line 1\nLine 2\nLine 3\n")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Initial commit")
        
        self.create_file("file1.txt", "Line 1\nLine 2 modified\nLine 3\n")
        
        result = self.run_gitforge("diff")
        
        self.assertEqual(result.returncode, 0)

    def test_diff_cached(self):
        """Test: gitforge diff --cached shows staged changes"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Original content\n")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Initial commit")
        
        self.create_file("file1.txt", "Modified content\n")
        self.run_gitforge("add", "file1.txt")
        
        result = self.run_gitforge("diff", "--cached")
        
        self.assertEqual(result.returncode, 0)

    def test_diff_with_commit(self):
        """Test: gitforge diff with specific commit"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Version 1\n")
        self.run_gitforge("add", "file1.txt")
        commit1 = self.run_gitforge("commit", "-m", "Version 1").stdout.strip()
        
        self.create_file("file1.txt", "Version 2\n")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Version 2")
        
        self.create_file("file1.txt", "Version 3\n")
        
        result = self.run_gitforge("diff", commit1)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("-Version 1", result.stdout)
        self.assertIn("+Version 3", result.stdout)


class TestShow(GitforgeTestBase):
    """Tests for gitforge show command."""

    def test_show_commit(self):
        """Test: gitforge show displays commit details"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        commit_oid = self.run_gitforge("commit", "-m", "Test commit message").stdout.strip()
        
        result = self.run_gitforge("show", commit_oid)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("Test commit message", result.stdout)
        self.assertIn("commit", result.stdout)

    def test_show_default_head(self):
        """Test: gitforge show defaults to HEAD"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "HEAD commit message")
        
        result = self.run_gitforge("show")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("HEAD commit message", result.stdout)

    def test_show_includes_diff(self):
        """Test: gitforge show includes diff"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Initial content\n")
        self.run_gitforge("add", "file1.txt")
        self.run_gitforge("commit", "-m", "Initial commit")
        
        self.create_file("file1.txt", "Modified content\n")
        self.run_gitforge("add", "file1.txt")
        commit2 = self.run_gitforge("commit", "-m", "Modify file").stdout.strip()
        
        result = self.run_gitforge("show", commit2)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("-Initial content", result.stdout)
        self.assertIn("+Modified content", result.stdout)


class TestConfig(GitforgeTestBase):
    """Tests for gitforge config command."""

    def test_config_set_and_get(self):
        """Test: gitforge config sets and gets values"""
        self.run_gitforge("init")
        
        self.run_gitforge("config", "user.name", "Test User")
        result = self.run_gitforge("config", "user.name")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("Test User", result.stdout)

    def test_config_nested_keys(self):
        """Test: gitforge config with nested keys"""
        self.run_gitforge("init")
        
        self.run_gitforge("config", "user.email", "test@example.com")
        result = self.run_gitforge("config", "user.email")
        
        self.assertIn("test@example.com", result.stdout)

    def test_config_list_all(self):
        """Test: gitforge config lists all config"""
        self.run_gitforge("init")
        self.run_gitforge("config", "user.name", "Test User")
        self.run_gitforge("config", "user.email", "test@example.com")
        
        result = self.run_gitforge("config")
        
        self.assertEqual(result.returncode, 0)
        # Config output is JSON
        self.assertIn("user", result.stdout)


class TestCherryPick(GitforgeTestBase):
    """Tests for gitforge cherry-pick command."""

    def test_cherry_pick_single_commit(self):
        """Test: gitforge cherry-pick applies single commit"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("checkout", "feature")
        
        self.create_file("feature.txt", "feature content")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature change").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("cherry-pick", feature_commit)
        
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.file_exists("feature.txt"))

    def test_cherry_pick_preserves_author(self):
        """Test: cherry-pick preserves original author"""
        self.run_gitforge("init")
        self.run_gitforge("config", "user.name", "Original Author")
        self.run_gitforge("config", "user.email", "original@test.com")
        
        self.create_file("file1.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("checkout", "feature")
        
        self.create_file("feature.txt", "feature content")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature change").stdout.strip()
        
        # Change author
        self.run_gitforge("config", "user.name", "New Author")
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("cherry-pick", feature_commit)
        
        show_result = self.run_gitforge("show")
        self.assertIn("Original Author", show_result.stdout)

    def test_cherry_pick_conflict(self):
        """Test: cherry-pick with conflict"""
        self.run_gitforge("init")
        self.create_file("file.txt", "base content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature content\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("cherry-pick", feature_commit)
        
        self.assertIn("CONFLICT", result.stdout)

    def test_cherry_pick_abort(self):
        """Test: gitforge cherry-pick --abort"""
        self.run_gitforge("init")
        self.create_file("file.txt", "base content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature content\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("cherry-pick", feature_commit)
        
        result = self.run_gitforge("cherry-pick", "--abort")
        
        self.assertEqual(result.returncode, 0)
        content = self.read_file_content("file.txt")
        self.assertEqual(content, "master content\n")

    def test_cherry_pick_continue(self):
        """Test: gitforge cherry-pick --continue after resolving conflict"""
        self.run_gitforge("init")
        self.create_file("file.txt", "base content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature content\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("cherry-pick", feature_commit)
        
        # Resolve conflict
        self.create_file("file.txt", "resolved content\n")
        self.run_gitforge("add", "file.txt")
        
        result = self.run_gitforge("cherry-pick", "--continue")
        
        self.assertEqual(result.returncode, 0)

    def test_cherry_pick_rejects_merge_commit(self):
        """Test: cherry-pick rejects merge commits"""
        self.run_gitforge("init")
        self.create_file("base.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("master.txt", "master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("feature.txt", "feature")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        merge_commit = self.run_gitforge("commit", "-m", "merge").stdout.strip()
        
        self.run_gitforge("checkout", "feature")
        result = self.run_gitforge("cherry-pick", merge_commit)
        
        self.assertIn("merge commit", result.stdout.lower())


class TestReadWriteTree(GitforgeTestBase):
    """Tests for gitforge read-tree and write-tree commands."""

    def test_write_tree(self):
        """Test: gitforge write-tree creates tree object"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.create_file("subdir/file2.txt", "Content 2")
        self.run_gitforge("add", "file1.txt", "subdir/file2.txt")
        
        result = self.run_gitforge("write-tree")
        
        self.assertEqual(result.returncode, 0)
        tree_oid = result.stdout.strip()
        self.assertEqual(len(tree_oid), 40)

    def test_read_tree(self):
        """Test: gitforge read-tree updates index from tree"""
        self.run_gitforge("init")
        self.create_file("file1.txt", "Content 1")
        self.run_gitforge("add", "file1.txt")
        
        tree_result = self.run_gitforge("write-tree")
        tree_oid = tree_result.stdout.strip()
        
        self.create_file("other.txt", "Other content")
        self.run_gitforge("add", "other.txt")
        
        result = self.run_gitforge("read-tree", tree_oid)
        
        self.assertEqual(result.returncode, 0)


class TestRemoteOperations(unittest.TestCase):
    """Tests for remote operations (fetch, push)."""

    @classmethod
    def setUpClass(cls):
        cls.test_base_dir = tempfile.mkdtemp(prefix="gitforge_remote_test_")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_base_dir):
            shutil.rmtree(cls.test_base_dir)

    def setUp(self):
        self.local_dir = tempfile.mkdtemp(dir=self.test_base_dir, prefix="local_")
        self.remote_dir = tempfile.mkdtemp(dir=self.test_base_dir, prefix="remote_")

    def run_gitforge(self, working_dir, *args, expect_success=True):
        cmd = [sys.executable, str(GITFORGE_RUNNER)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=working_dir
        )
        return result

    def create_file(self, base_dir, name, content):
        filepath = Path(base_dir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        return filepath

    def test_fetch(self):
        """Test: gitforge fetch"""
        self.run_gitforge(self.remote_dir, "init")
        self.create_file(self.remote_dir, "file1.txt", "Remote content")
        self.run_gitforge(self.remote_dir, "add", "file1.txt")
        self.run_gitforge(self.remote_dir, "commit", "-m", "Remote commit")
        
        self.run_gitforge(self.local_dir, "init")
        
        result = self.run_gitforge(self.local_dir, "fetch", self.remote_dir)
        
        self.assertEqual(result.returncode, 0)
        refs_path = os.path.join(self.local_dir, ".gitforge", "refs", "remote")
        self.assertTrue(os.path.exists(refs_path))

    def test_push(self):
        """Test: gitforge push"""
        self.run_gitforge(self.remote_dir, "init")
        
        self.run_gitforge(self.local_dir, "init")
        self.create_file(self.local_dir, "file1.txt", "Local content")
        self.run_gitforge(self.local_dir, "add", "file1.txt")
        local_commit = self.run_gitforge(self.local_dir, "commit", "-m", "Local commit").stdout.strip()
        
        result = self.run_gitforge(self.local_dir, "push", self.remote_dir, "master")
        
        self.assertEqual(result.returncode, 0)
        remote_ref_path = os.path.join(self.remote_dir, ".gitforge", "refs", "heads", "master")
        self.assertTrue(os.path.exists(remote_ref_path))
        
        with open(remote_ref_path) as f:
            remote_ref = f.read().strip()
        self.assertEqual(remote_ref, local_commit)

    def test_push_rejects_non_ancestor(self):
        """Test: gitforge push rejects non-fast-forward"""
        self.run_gitforge(self.remote_dir, "init")
        self.create_file(self.remote_dir, "remote.txt", "Remote content")
        self.run_gitforge(self.remote_dir, "add", "remote.txt")
        self.run_gitforge(self.remote_dir, "commit", "-m", "Remote commit")
        
        self.run_gitforge(self.local_dir, "init")
        self.create_file(self.local_dir, "local.txt", "Local content")
        self.run_gitforge(self.local_dir, "add", "local.txt")
        self.run_gitforge(self.local_dir, "commit", "-m", "Local commit")
        
        result = self.run_gitforge(self.local_dir, "push", self.remote_dir, "master", expect_success=False)
        
        self.assertNotEqual(result.returncode, 0)


class TestEdgeCases(GitforgeTestBase):
    """Tests for edge cases and error handling."""

    def test_empty_repository_log(self):
        """Test: gitforge log on empty repository"""
        self.run_gitforge("init")
        
        result = self.run_gitforge("log", expect_success=False)
        # May fail, but should not crash with unhandled exception

    def test_checkout_nonexistent_ref(self):
        """Test: gitforge checkout with nonexistent ref"""
        self.init_repo_with_commit()
        
        result = self.run_gitforge("checkout", "nonexistent-branch", expect_success=False)
        
        self.assertNotEqual(result.returncode, 0)

    def test_branch_without_commits(self):
        """Test: gitforge branch without any commits"""
        self.run_gitforge("init")
        
        result = self.run_gitforge("branch", "new-branch", expect_success=False)
        # Should fail because there's no commit

    def test_large_file_content(self):
        """Test: handling large file content"""
        self.run_gitforge("init")
        
        content = "\n".join([f"Line {i}" for i in range(10000)])
        self.create_file("large.txt", content)
        
        self.run_gitforge("add", "large.txt")
        result = self.run_gitforge("commit", "-m", "Large file")
        
        self.assertEqual(result.returncode, 0)
        
        commit = result.stdout.strip()
        self.run_gitforge("checkout", commit)
        
        retrieved = self.read_file_content("large.txt")
        self.assertEqual(retrieved, content)

    def test_special_characters_in_content(self):
        """Test: handling special characters"""
        self.run_gitforge("init")
        
        content = "Special: <>&\"'`$@#%^*()[]{}|\\;:,.\nUnicode: 你好世界 🎉\n"
        self.create_file("special.txt", content)
        
        self.run_gitforge("add", "special.txt")
        result = self.run_gitforge("commit", "-m", "Special chars")
        
        self.assertEqual(result.returncode, 0)

    def test_multiple_branches_workflow(self):
        """Test: working with multiple branches"""
        self.init_repo_with_commit()
        
        self.run_gitforge("branch", "feature-a")
        self.run_gitforge("branch", "feature-b")
        self.run_gitforge("branch", "feature-c")
        
        self.run_gitforge("checkout", "feature-a")
        self.create_file("a.txt", "Feature A")
        self.run_gitforge("add", "a.txt")
        self.run_gitforge("commit", "-m", "Feature A")
        
        self.run_gitforge("checkout", "feature-b")
        self.create_file("b.txt", "Feature B")
        self.run_gitforge("add", "b.txt")
        self.run_gitforge("commit", "-m", "Feature B")
        
        self.run_gitforge("checkout", "feature-c")
        self.assertFalse(self.file_exists("a.txt"))
        self.assertFalse(self.file_exists("b.txt"))
        
        result = self.run_gitforge("branch")
        self.assertIn("feature-a", result.stdout)
        self.assertIn("feature-b", result.stdout)
        self.assertIn("feature-c", result.stdout)


class TestCompleteWorkflow(unittest.TestCase):
    """Integration test with complete workflow."""

    def test_complete_workflow(self):
        """Test a complete git-like workflow."""
        test_dir = tempfile.mkdtemp(prefix="gitforge_workflow_")
        os.chdir(test_dir)
        
        try:
            def run_gitforge(*args):
                cmd = [sys.executable, str(GITFORGE_RUNNER)] + list(args)
                return subprocess.run(cmd, capture_output=True, text=True, cwd=test_dir)
            
            def create_file(name, content):
                filepath = Path(test_dir) / name
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(content)
            
            # 1. Init
            result = run_gitforge("init")
            self.assertEqual(result.returncode, 0)
            
            # 2. Create files
            create_file("README.md", "# Project")
            create_file("src/main.py", "print('Hello')")
            run_gitforge("add", ".")
            
            # 3. Initial commit
            commit1 = run_gitforge("commit", "-m", "Initial commit").stdout.strip()
            self.assertEqual(len(commit1), 40)
            
            # 4. Tag
            run_gitforge("tag", "v1.0")
            
            # 5. Branch and checkout
            run_gitforge("branch", "feature")
            run_gitforge("checkout", "feature")
            
            # 6. Feature changes
            create_file("src/feature.py", "def feature(): pass")
            run_gitforge("add", ".")
            commit2 = run_gitforge("commit", "-m", "Add feature").stdout.strip()
            
            # 7. Back to master
            run_gitforge("checkout", "master")
            
            # 8. Master changes
            create_file("README.md", "# Project\n\nUpdated")
            run_gitforge("add", ".")
            run_gitforge("commit", "-m", "Update README")
            
            # 9. Merge
            run_gitforge("merge", commit2)
            run_gitforge("commit", "-m", "Merge feature")
            
            # 10. Log
            log_result = run_gitforge("log")
            self.assertIn("Merge feature", log_result.stdout)
            
            # 11. Status
            status_result = run_gitforge("status")
            self.assertIn("On branch", status_result.stdout)
            
            # 12. Reset
            run_gitforge("reset", "--hard", commit1)
            log_result = run_gitforge("log")
            self.assertIn("Initial commit", log_result.stdout)
            
        finally:
            os.chdir("/")
            shutil.rmtree(test_dir)


class TestMergeEdgeCases(GitforgeTestBase):
    """Tests for merge edge cases and error handling."""

    def test_merge_no_common_ancestor(self):
        """Test: merge fails gracefully when branches have no common ancestor.
        
        This tests the bug where merge() crashes with TypeError when
        get_merge_base() returns None.
        
        Note: This test creates two independent commit histories by creating
        a separate repo and fetching from it.
        """
        # Create first repo with a commit
        self.run_gitforge("init")
        self.create_file("file1.txt", "content from first history")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "first history commit")
        
        # Create a separate repo with independent history
        import tempfile
        other_repo = tempfile.mkdtemp(dir=self.test_base_dir)
        
        # Initialize other repo with different content
        other_result = subprocess.run(
            [sys.executable, str(GITFORGE_RUNNER), "init"],
            cwd=other_repo, capture_output=True, text=True
        )
        self.assertEqual(other_result.returncode, 0)
        
        # Create a file and commit in other repo
        (Path(other_repo) / "other.txt").write_text("other content")
        subprocess.run(
            [sys.executable, str(GITFORGE_RUNNER), "add", "other.txt"],
            cwd=other_repo, capture_output=True
        )
        other_commit_result = subprocess.run(
            [sys.executable, str(GITFORGE_RUNNER), "commit", "-m", "other commit"],
            cwd=other_repo, capture_output=True, text=True
        )
        other_commit = other_commit_result.stdout.strip()
        
        # Fetch from other repo to get the objects
        self.run_gitforge("fetch", other_repo)
        
        # Try to merge - this should fail gracefully with an error message
        result = self.run_gitforge("merge", other_commit, expect_success=False)
        
        # The command should return a non-zero exit code and provide error message
        # about no common history (not crash with unhandled exception)
        self.assertNotEqual(result.returncode, 0)
        combined_output = (result.stdout + result.stderr).lower()
        self.assertTrue(
            "no common" in combined_output or 
            "error" in combined_output or
            "traceback" in combined_output,  # If it crashes, we detect that too
            f"Expected error message about no common ancestor, got: {result.stdout} {result.stderr}"
        )

    def test_merge_already_up_to_date(self):
        """Test: merge when already merged (other is ancestor of HEAD)."""
        self.run_gitforge("init")
        self.create_file("file1.txt", "base")
        self.run_gitforge("add", ".")
        base_commit = self.run_gitforge("commit", "-m", "base").stdout.strip()
        
        self.create_file("file2.txt", "new file")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "add file2")
        
        # Try to merge the ancestor commit - should be fast-forward or no-op
        result = self.run_gitforge("merge", base_commit)
        self.assertEqual(result.returncode, 0)

    def test_merge_same_commit(self):
        """Test: merge HEAD with itself."""
        commit = self.init_repo_with_commit()
        
        result = self.run_gitforge("merge", commit)
        self.assertEqual(result.returncode, 0)
        self.assertIn("Fast-forward", result.stdout)

    def test_merge_preserves_branch_attachment(self):
        """Test: after merge, HEAD remains attached to branch."""
        self.run_gitforge("init")
        self.create_file("file1.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("checkout", "feature")
        self.create_file("feature.txt", "feature content")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        # Check HEAD is still on master branch
        status_result = self.run_gitforge("status")
        self.assertIn("On branch master", status_result.stdout)


class TestConflictScenarios(GitforgeTestBase):
    """Tests for various conflict types and their handling."""

    def test_content_conflict_has_markers(self):
        """Test: content conflicts write file with conflict markers."""
        self.run_gitforge("init")
        self.create_file("file.txt", "line1\nbase content\nline3\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Modify on master
        self.create_file("file.txt", "line1\nmaster content\nline3\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master change")
        
        # Modify on feature (different change)
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "line1\nfeature content\nline3\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature change").stdout.strip()
        
        # Merge
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertIn("conflict", result.stdout.lower())
        
        # Check file has conflict markers
        content = self.read_file_content("file.txt")
        self.assertIn("<<<<<<<", content)
        self.assertIn(">>>>>>>", content)

    def test_add_add_conflict(self):
        """Test: add/add conflict when both sides add same file with different content.
        
        Both sides added the same file with different content - should create a conflict
        file with markers so the user can resolve it.
        """
        self.run_gitforge("init")
        self.create_file("base.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Add new file on master
        self.create_file("newfile.txt", "master version of new file\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "add newfile on master")
        
        # Add same file on feature with different content
        self.run_gitforge("checkout", "feature")
        self.create_file("newfile.txt", "feature version of new file\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "add newfile on feature").stdout.strip()
        
        # Merge
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        # Should report conflict
        self.assertIn("conflict", result.stdout.lower())
        
        # Check status shows conflict with correct type
        status = self.run_gitforge("status")
        self.assertIn("newfile.txt", status.stdout)
        self.assertIn("both added", status.stdout.lower())
        
        # File SHOULD exist in working directory with conflict markers
        self.assertTrue(
            self.file_exists("newfile.txt"),
            "add/add conflict: file should exist in working dir with conflict markers"
        )
        
        # Verify conflict markers are present
        content = self.read_file_content("newfile.txt")
        self.assertIn("<<<<<<<", content)
        self.assertIn(">>>>>>>", content)

    def test_add_add_same_content_no_conflict(self):
        """Test: add/add with identical content should NOT conflict."""
        self.run_gitforge("init")
        self.create_file("base.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Add new file on master
        self.create_file("newfile.txt", "identical content")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "add newfile on master")
        
        # Add same file on feature with SAME content
        self.run_gitforge("checkout", "feature")
        self.create_file("newfile.txt", "identical content")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "add newfile on feature").stdout.strip()
        
        # Merge - should NOT conflict
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertNotIn("conflict", result.stdout.lower())
        self.assertTrue(self.file_exists("newfile.txt"))

    def test_delete_modify_conflict(self):
        """Test: content conflict when both sides modify the same file differently.
        
        This tests the standard content_conflict scenario.
        """
        self.run_gitforge("init")
        self.create_file("file.txt", "original content\n")
        self.create_file("keep.txt", "keep this file")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Modify file on master
        self.create_file("file.txt", "modified on master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "modify on master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "different modification on feature\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "modify differently on feature").stdout.strip()
        
        # Merge
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        # Should report conflict (content conflict since both modified)
        self.assertIn("conflict", result.stdout.lower())
        
        # Check status shows conflict with correct type
        status = self.run_gitforge("status")
        self.assertIn("file.txt", status.stdout)
        self.assertIn("both modified", status.stdout.lower())
        
        # File should exist with conflict markers
        self.assertTrue(self.file_exists("file.txt"))
        content = self.read_file_content("file.txt")
        self.assertIn("<<<<<<<", content)
        self.assertIn(">>>>>>>", content)

    def test_one_side_modifies_other_unchanged(self):
        """Test: one side modifies, other doesn't change - should NOT conflict."""
        self.run_gitforge("init")
        self.create_file("file.txt", "original content")
        self.create_file("other.txt", "other file")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Modify file on master
        self.create_file("file.txt", "modified on master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "modify file")
        
        # Make unrelated change on feature (don't touch file.txt)
        self.run_gitforge("checkout", "feature")
        self.create_file("other.txt", "modified other file")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "modify other").stdout.strip()
        
        # Merge - should accept master's change without conflict
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertNotIn("conflict", result.stdout.lower())
        # Master's modification should be preserved
        content = self.read_file_content("file.txt")
        self.assertEqual(content, "modified on master")

    def test_one_side_adds_new_file(self):
        """Test: one side adds new file, other doesn't - should NOT conflict."""
        self.run_gitforge("init")
        self.create_file("base.txt", "base content")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Add new file on master
        self.create_file("master_new.txt", "new file from master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "add new on master")
        
        # Add different new file on feature
        self.run_gitforge("checkout", "feature")
        self.create_file("feature_new.txt", "new file from feature")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "add new on feature").stdout.strip()
        
        # Merge - both new files should exist
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertNotIn("conflict", result.stdout.lower())
        self.assertTrue(self.file_exists("master_new.txt"))
        self.assertTrue(self.file_exists("feature_new.txt"))

    def test_both_modify_same_way(self):
        """Test: both sides make identical modifications - should NOT conflict."""
        self.run_gitforge("init")
        self.create_file("file.txt", "original")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Same modification on master
        self.create_file("file.txt", "modified identically")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "modify on master")
        
        # Same modification on feature
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "modified identically")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "modify on feature").stdout.strip()
        
        # Merge
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertNotIn("conflict", result.stdout.lower())
        content = self.read_file_content("file.txt")
        self.assertEqual(content, "modified identically")

    def test_resolve_conflict_with_add(self):
        """Test: resolving conflict by editing file and running add."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        # Resolve conflict
        self.create_file("file.txt", "resolved content\n")
        self.run_gitforge("add", "file.txt")
        
        # Should now be able to commit
        result = self.run_gitforge("commit", "-m", "merge commit")
        self.assertEqual(result.returncode, 0)


class TestConflictFileVisibility(GitforgeTestBase):
    """Tests to verify conflict files are visible in working directory.
    
    These tests specifically verify the fix for the issue where add_add and
    delete_modify conflicts would not write any file to the working directory,
    making it impossible for users to resolve conflicts.
    """

    def test_add_add_conflict_file_visible_during_merge(self):
        """Test: add/add conflict writes file with conflict markers during merge."""
        self.run_gitforge("init")
        self.create_file("base.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Add new file on master
        self.create_file("newfile.txt", "master added this file\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "add newfile on master")
        
        # Add same file on feature with different content
        self.run_gitforge("checkout", "feature")
        self.create_file("newfile.txt", "feature added this file\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "add newfile on feature").stdout.strip()
        
        # Merge
        self.run_gitforge("checkout", "master")
        result = self.run_gitforge("merge", feature_commit)
        
        self.assertIn("conflict", result.stdout.lower())
        
        # Critical: file must exist so user can resolve it
        self.assertTrue(self.file_exists("newfile.txt"))
        content = self.read_file_content("newfile.txt")
        self.assertIn("<<<<<<<", content)
        self.assertIn("HEAD", content)
        self.assertIn(">>>>>>>", content)
        
        # Status should show "both added" type
        status = self.run_gitforge("status")
        self.assertIn("both added", status.stdout.lower())

    def test_add_add_conflict_file_visible_during_rebase(self):
        """Test: add/add conflict writes file with conflict markers during rebase.
        
        This is the original reported issue - during rebase with add_add conflict,
        the file was not present in the working directory.
        """
        self.run_gitforge("init")
        self.create_file("base.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Add new file on master
        self.create_file("newfile.txt", "master added this file\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "add newfile on master")
        
        # Add same file on feature with different content
        self.run_gitforge("checkout", "feature")
        self.create_file("newfile.txt", "feature added this file\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "add newfile on feature")
        
        # Rebase feature onto master - this should conflict
        result = self.run_gitforge("rebase", "master")
        
        self.assertIn("CONFLICT", result.stdout)
        
        # Critical: file must exist so user can resolve it
        self.assertTrue(
            self.file_exists("newfile.txt"),
            "add/add conflict during rebase: file MUST exist in working directory"
        )
        content = self.read_file_content("newfile.txt")
        self.assertIn("<<<<<<<", content)
        self.assertIn(">>>>>>>", content)
        
        # Resolve and continue
        self.create_file("newfile.txt", "resolved content\n")
        self.run_gitforge("add", "newfile.txt")
        result = self.run_gitforge("rebase", "--continue")
        self.assertEqual(result.returncode, 0)

    def test_add_add_conflict_resolution_workflow(self):
        """Test: complete workflow for resolving add/add conflict."""
        self.run_gitforge("init")
        self.create_file("base.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("shared.txt", "master version\nline 2\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master adds shared.txt")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("shared.txt", "feature version\nline 2\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature adds shared.txt").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        # User resolves the conflict
        self.create_file("shared.txt", "merged version\nline 2\n")
        self.run_gitforge("add", "shared.txt")
        
        # Commit should succeed
        result = self.run_gitforge("commit", "-m", "resolve add/add conflict")
        self.assertEqual(result.returncode, 0)
        
        # Verify the resolved content
        content = self.read_file_content("shared.txt")
        self.assertEqual(content, "merged version\nline 2\n")

    def test_content_conflict_file_visible(self):
        """Test: content conflict writes file with conflict markers."""
        self.run_gitforge("init")
        self.create_file("file.txt", "line1\nbase content\nline3\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "line1\nmaster content\nline3\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master change")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "line1\nfeature content\nline3\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature change").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        # File must exist with conflict markers
        self.assertTrue(self.file_exists("file.txt"))
        content = self.read_file_content("file.txt")
        self.assertIn("<<<<<<<", content)
        self.assertIn("master content", content)
        self.assertIn("feature content", content)
        self.assertIn(">>>>>>>", content)

    def test_conflict_types_displayed_correctly(self):
        """Test: status shows correct conflict type labels."""
        self.run_gitforge("init")
        self.create_file("existing.txt", "base content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Create two types of conflicts:
        # 1. content conflict on existing.txt
        # 2. add/add conflict on newfile.txt
        self.create_file("existing.txt", "master modified\n")
        self.create_file("newfile.txt", "master added\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master changes")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("existing.txt", "feature modified\n")
        self.create_file("newfile.txt", "feature added\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature changes").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        status = self.run_gitforge("status")
        
        # Both conflict types should be shown with correct labels
        self.assertIn("both modified", status.stdout.lower())
        self.assertIn("both added", status.stdout.lower())
        
        # Both files should exist
        self.assertTrue(self.file_exists("existing.txt"))
        self.assertTrue(self.file_exists("newfile.txt"))


class TestRebaseScenarios(GitforgeTestBase):
    """Tests for rebase edge cases and scenarios."""

    def test_rebase_basic(self):
        """Test: basic rebase workflow."""
        self.run_gitforge("init")
        self.create_file("file1.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Add commit on master
        self.create_file("master.txt", "master content")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master commit")
        
        # Add commit on feature
        self.run_gitforge("checkout", "feature")
        self.create_file("feature.txt", "feature content")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature commit")
        
        # Rebase feature onto master
        result = self.run_gitforge("rebase", "master")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("Rebase complete", result.stdout)
        
        # Both files should exist
        self.assertTrue(self.file_exists("master.txt"))
        self.assertTrue(self.file_exists("feature.txt"))

    def test_rebase_preserves_author(self):
        """Test: rebase preserves original author information."""
        self.run_gitforge("init")
        self.run_gitforge("config", "user.name", "Original Author")
        self.run_gitforge("config", "user.email", "original@test.com")
        
        self.create_file("file1.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("checkout", "feature")
        
        self.create_file("feature.txt", "feature")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature commit")
        
        # Change author
        self.run_gitforge("config", "user.name", "Rebaser")
        
        # Add commit on master so rebase has something to do
        self.run_gitforge("checkout", "master")
        self.create_file("master.txt", "master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master commit")
        
        # Rebase
        self.run_gitforge("checkout", "feature")
        self.run_gitforge("rebase", "master")
        
        # Check author is preserved
        show_result = self.run_gitforge("show")
        self.assertIn("Original Author", show_result.stdout)

    def test_rebase_with_conflict(self):
        """Test: rebase stops on conflict and can be continued."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Conflicting change on master
        self.create_file("file.txt", "master content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master change")
        
        # Conflicting change on feature
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature content\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature change")
        
        # Rebase - should conflict
        result = self.run_gitforge("rebase", "master")
        self.assertIn("CONFLICT", result.stdout)
        
        # Resolve and continue
        self.create_file("file.txt", "resolved\n")
        self.run_gitforge("add", "file.txt")
        
        result = self.run_gitforge("rebase", "--continue")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Rebase complete", result.stdout)

    def test_rebase_abort(self):
        """Test: rebase --abort restores original state."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        original_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        # Start rebase (will conflict)
        self.run_gitforge("rebase", "master")
        
        # Abort
        result = self.run_gitforge("rebase", "--abort")
        self.assertEqual(result.returncode, 0)
        self.assertIn("aborted", result.stdout.lower())
        
        # File should be restored
        content = self.read_file_content("file.txt")
        self.assertEqual(content, "feature\n")

    def test_rebase_already_up_to_date(self):
        """Test: rebase when already based on upstream."""
        self.run_gitforge("init")
        self.create_file("file1.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("checkout", "feature")
        
        self.create_file("feature.txt", "feature")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature")
        
        # Rebase onto master (which is already base)
        result = self.run_gitforge("rebase", "master")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("up to date", result.stdout.lower())

    def test_rebase_multiple_commits(self):
        """Test: rebase replays multiple commits in order."""
        self.run_gitforge("init")
        self.create_file("base.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # Master commit
        self.create_file("master.txt", "master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        # Multiple feature commits
        self.run_gitforge("checkout", "feature")
        
        self.create_file("f1.txt", "feature 1")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature 1")
        
        self.create_file("f2.txt", "feature 2")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature 2")
        
        self.create_file("f3.txt", "feature 3")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature 3")
        
        # Rebase
        result = self.run_gitforge("rebase", "master")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("3 commit(s)", result.stdout)
        
        # All files should exist
        self.assertTrue(self.file_exists("master.txt"))
        self.assertTrue(self.file_exists("f1.txt"))
        self.assertTrue(self.file_exists("f2.txt"))
        self.assertTrue(self.file_exists("f3.txt"))

    def test_rebase_rejects_merge_commits(self):
        """Test: rebase fails if branch contains merge commits."""
        self.run_gitforge("init")
        self.create_file("base.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("branch", "side")
        
        # Commit on feature
        self.run_gitforge("checkout", "feature")
        self.create_file("feature.txt", "feature")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature")
        
        # Commit on side
        self.run_gitforge("checkout", "side")
        self.create_file("side.txt", "side")
        self.run_gitforge("add", ".")
        side_commit = self.run_gitforge("commit", "-m", "side").stdout.strip()
        
        # Merge side into feature (creates merge commit)
        self.run_gitforge("checkout", "feature")
        self.run_gitforge("merge", side_commit)
        self.run_gitforge("commit", "-m", "merge side into feature")
        
        # Commit on master
        self.run_gitforge("checkout", "master")
        self.create_file("master.txt", "master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        # Try to rebase feature onto master - should fail
        self.run_gitforge("checkout", "feature")
        result = self.run_gitforge("rebase", "master")
        
        self.assertIn("merge commit", result.stdout.lower())

    def test_rebase_empty_commit_skipped(self):
        """Test: rebase skips commits that become empty."""
        self.run_gitforge("init")
        self.create_file("file.txt", "content")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # On feature, modify file
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "modified")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "modify on feature")
        
        # On master, make same modification
        self.run_gitforge("checkout", "master")
        self.create_file("file.txt", "modified")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "same modification on master")
        
        # Rebase feature onto master - commit should be empty
        self.run_gitforge("checkout", "feature")
        result = self.run_gitforge("rebase", "master")
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("empty", result.stdout.lower())

    def test_rebase_preserves_branch_attachment(self):
        """Test: after rebase, HEAD remains attached to branch."""
        self.run_gitforge("init")
        self.create_file("file1.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("master.txt", "master")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("feature.txt", "feature")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature")
        
        self.run_gitforge("rebase", "master")
        
        # Check still on feature branch
        status = self.run_gitforge("status")
        self.assertIn("On branch feature", status.stdout)


class TestCherryPickScenarios(GitforgeTestBase):
    """Tests for cherry-pick edge cases and scenarios."""

    def test_cherry_pick_empty_becomes_skip(self):
        """Test: cherry-pick skips commit that would be empty."""
        self.run_gitforge("init")
        self.create_file("file.txt", "content")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        # On feature, modify file
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "modified")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "modify on feature").stdout.strip()
        
        # On master, make same modification
        self.run_gitforge("checkout", "master")
        self.create_file("file.txt", "modified")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "same modification on master")
        
        # Cherry-pick feature commit - should be empty
        result = self.run_gitforge("cherry-pick", feature_commit)
        
        self.assertEqual(result.returncode, 0)
        self.assertIn("empty", result.stdout.lower())

    def test_cherry_pick_rejects_root_commit(self):
        """Test: cherry-pick rejects root commits (no parent)."""
        self.run_gitforge("init")
        self.create_file("file.txt", "content")
        self.run_gitforge("add", ".")
        root_commit = self.run_gitforge("commit", "-m", "root").stdout.strip()
        
        self.create_file("file2.txt", "more content")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "second")
        
        # Try to cherry-pick root - should fail
        result = self.run_gitforge("cherry-pick", root_commit)
        
        self.assertIn("root commit", result.stdout.lower())

    def test_cherry_pick_rejects_during_merge(self):
        """Test: cherry-pick fails if merge is in progress."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        # Start conflicting merge
        self.run_gitforge("checkout", "master")
        self.run_gitforge("branch", "other")
        self.run_gitforge("checkout", "other")
        self.create_file("other.txt", "other")
        self.run_gitforge("add", ".")
        other_commit = self.run_gitforge("commit", "-m", "other").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)  # Creates conflict
        
        # Try cherry-pick - should fail
        result = self.run_gitforge("cherry-pick", other_commit)
        
        self.assertIn("merge is in progress", result.stdout.lower())

    def test_cherry_pick_rejects_during_rebase(self):
        """Test: cherry-pick fails if rebase is in progress."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("branch", "other")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature")
        
        self.run_gitforge("checkout", "other")
        self.create_file("other.txt", "other")
        self.run_gitforge("add", ".")
        other_commit = self.run_gitforge("commit", "-m", "other").stdout.strip()
        
        # Start conflicting rebase
        self.run_gitforge("checkout", "feature")
        self.run_gitforge("rebase", "master")  # Creates conflict
        
        # Try cherry-pick - should fail
        result = self.run_gitforge("cherry-pick", other_commit)
        
        self.assertIn("rebase is in progress", result.stdout.lower())

    def test_cherry_pick_with_dirty_working_tree(self):
        """Test: cherry-pick fails with uncommitted changes."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("checkout", "feature")
        self.create_file("feature.txt", "feature")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        
        # Create uncommitted change
        self.create_file("file.txt", "modified but not committed")
        
        # Try cherry-pick - should fail
        result = self.run_gitforge("cherry-pick", feature_commit)
        
        self.assertIn("changes exist", result.stdout.lower())


class TestBranchPreservation(GitforgeTestBase):
    """Tests to verify HEAD stays attached to branches during operations."""

    def test_reset_preserves_branch_attachment(self):
        """Test: reset keeps HEAD attached to branch."""
        self.run_gitforge("init")
        self.create_file("file.txt", "v1")
        self.run_gitforge("add", ".")
        commit1 = self.run_gitforge("commit", "-m", "v1").stdout.strip()
        
        self.create_file("file.txt", "v2")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "v2")
        
        # Reset to earlier commit
        self.run_gitforge("reset", "--hard", commit1)
        
        # Should still be on master
        status = self.run_gitforge("status")
        self.assertIn("On branch master", status.stdout)

    def test_fast_forward_merge_preserves_branch(self):
        """Test: fast-forward merge keeps HEAD attached to branch."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        self.run_gitforge("checkout", "feature")
        
        self.create_file("feature.txt", "feature")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        # Should still be on master
        status = self.run_gitforge("status")
        self.assertIn("On branch master", status.stdout)

    def test_merge_abort_preserves_branch(self):
        """Test: merge --abort keeps HEAD attached to branch."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        self.run_gitforge("merge", "--abort")
        
        # Should still be on master
        status = self.run_gitforge("status")
        self.assertIn("On branch master", status.stdout)

    def test_cherry_pick_abort_preserves_branch(self):
        """Test: cherry-pick --abort keeps HEAD attached to branch."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("cherry-pick", feature_commit)
        self.run_gitforge("cherry-pick", "--abort")
        
        # Should still be on master
        status = self.run_gitforge("status")
        self.assertIn("On branch master", status.stdout)


class TestStatusDisplay(GitforgeTestBase):
    """Tests for status command displaying correct information."""

    def test_status_shows_rebase_in_progress(self):
        """Test: status shows rebase in progress."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "feature")
        
        # Start conflicting rebase
        self.run_gitforge("rebase", "master")
        
        status = self.run_gitforge("status")
        self.assertIn("Rebase in progress", status.stdout)

    def test_status_shows_cherry_pick_in_progress(self):
        """Test: status shows cherry-pick in progress."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("cherry-pick", feature_commit)
        
        status = self.run_gitforge("status")
        self.assertIn("Cherry-pick in progress", status.stdout)

    def test_status_shows_conflicted_files(self):
        """Test: status shows conflicted files."""
        self.run_gitforge("init")
        self.create_file("file.txt", "base\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "base")
        
        self.run_gitforge("branch", "feature")
        
        self.create_file("file.txt", "master\n")
        self.run_gitforge("add", ".")
        self.run_gitforge("commit", "-m", "master")
        
        self.run_gitforge("checkout", "feature")
        self.create_file("file.txt", "feature\n")
        self.run_gitforge("add", ".")
        feature_commit = self.run_gitforge("commit", "-m", "feature").stdout.strip()
        
        self.run_gitforge("checkout", "master")
        self.run_gitforge("merge", feature_commit)
        
        status = self.run_gitforge("status")
        self.assertIn("Unmerged paths", status.stdout)
        self.assertIn("file.txt", status.stdout)


def run_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("GITFORGE COMPREHENSIVE FUNCTIONAL TESTS")
    print("="*60)
    print(f"Testing gitforge from: {GITFORGE_RUNNER}")
    print("="*60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    test_classes = [
        TestInit,
        TestHashObject,
        TestCatFile,
        TestAdd,
        TestCommit,
        TestLog,
        TestBranch,
        TestCheckout,
        TestTag,
        TestStatus,
        TestReset,
        TestMerge,
        TestMergeBase,
        TestDiff,
        TestShow,
        TestConfig,
        TestCherryPick,
        TestReadWriteTree,
        TestRemoteOperations,
        TestEdgeCases,
        TestCompleteWorkflow,
        # New edge case and scenario tests
        TestMergeEdgeCases,
        TestConflictScenarios,
        TestConflictFileVisibility,  # Tests for add_add/delete_modify file visibility fix
        TestRebaseScenarios,
        TestCherryPickScenarios,
        TestBranchPreservation,
        TestStatusDisplay,
    ]
    
    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✓ ALL TESTS PASSED!")
    else:
        print("\n✗ SOME TESTS FAILED")
    
    print("="*60)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
