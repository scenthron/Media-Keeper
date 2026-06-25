"""
In-memory selection handling for duplicate groups.
Implements the iron rules:
1. At least one survivor per group (protected files count as a single survivor).
2. Cumulative filter – each filter marks files that should be removed while preserving the survivor(s).
"""

from __future__ import annotations

from typing import Dict, Set, List, Callable


class InMemorySelection:
    """Store selection state completely in RAM.

    Args:
        group_files: Mapping ``group_id -> list[dict]`` for all files.
                     Each dict must have at least: id, path, is_protected, size, mtime.
        protected_files: Set of ``file_id`` that are marked as protected.
    """

    def __init__(self, group_files: Dict[int, List[dict]], protected_files: Set[int]):
        # Store full item dicts so filters have access to all metadata
        self._group_files: Dict[int, List[dict]] = {
            gid: list(files) for gid, files in group_files.items()
        }
        self._protected_files: Set[int] = set(protected_files)
        # Files that have been marked (i.e. selected for removal/move)
        self._marked: Set[int] = set()

    # ------------------------------------------------------------------
    # Helper utilities
    # ------------------------------------------------------------------
    def _survivors(self, group_id: int) -> Set[int]:
        """Return the set of file ids that are considered *survivors* in a group.

        Iron Rule 1:
        - If the group contains protected files, the whole protected set is the survivor.
        - Otherwise a single arbitrary unmarked file acts as the survivor.
        """
        files = self._group_files.get(group_id, [])
        if not files:
            return set()

        protected_ids = {f['id'] for f in files if f['id'] in self._protected_files}
        if protected_ids:
            return protected_ids

        # No protected files – keep exactly one normal unmarked file as survivor.
        # Prefer already-unmarked files so cumulative filters don't displace the survivor.
        unmarked = [f for f in files if f['id'] not in self._marked]
        if unmarked:
            return {unmarked[0]['id']}
        # All files were somehow marked (shouldn't happen under iron rules) – keep first
        return {files[0]['id']}

    def _can_mark_more(self, group_id: int) -> bool:
        """True if the group still has at least 2 effective survivors after accounting for marks."""
        files = self._group_files.get(group_id, [])
        if not files:
            return False
        protected_ids = {f['id'] for f in files if f['id'] in self._protected_files}
        if protected_ids:
            # With protected files: group is blocked only when ALL non-protected are marked
            non_protected_unmarked = [f for f in files
                                      if f['id'] not in self._protected_files
                                      and f['id'] not in self._marked]
            return len(non_protected_unmarked) > 0
        else:
            # No protected: need at least 2 unmarked so after marking one, one survives
            unmarked_count = sum(1 for f in files if f['id'] not in self._marked)
            return unmarked_count > 1

    # ------------------------------------------------------------------
    # Public API used by UI
    # ------------------------------------------------------------------
    def can_mark(self, file_id: int, group_id: int) -> bool:
        """Check whether ``file_id`` may be marked according to the iron rules."""
        files = self._group_files.get(group_id, [])
        if not files:
            return False

        # Protected files cannot be marked
        if file_id in self._protected_files:
            return False

        # Already marked – technically can un-mark, but this method is for marking only
        if file_id in self._marked:
            return True  # Already marked, idempotent

        protected_ids = {f['id'] for f in files if f['id'] in self._protected_files}
        if protected_ids:
            # With protected survivors: can always mark any non-protected file
            return file_id not in self._protected_files
        else:
            # No protected: ensure at least one non-marked file remains besides this one
            other_unmarked = [f for f in files
                              if f['id'] not in self._marked and f['id'] != file_id]
            return len(other_unmarked) > 0

    def mark_file(self, file_id: int, group_id: int) -> bool:
        """Mark ``file_id`` for removal if rules allow it.

        Returns ``True`` on success, ``False`` otherwise.
        """
        if not self.can_mark(file_id, group_id):
            return False
        self._marked.add(file_id)
        return True

    def unmark_file(self, file_id: int) -> None:
        """Explicitly un-mark a file."""
        self._marked.discard(file_id)

    def toggle_file(self, file_id: int, group_id: int) -> bool:
        """Toggle mark state. Returns resulting state (True = marked)."""
        if file_id in self._marked:
            self.unmark_file(file_id)
            return False
        else:
            return self.mark_file(file_id, group_id)

    def clear_all(self) -> None:
        """Remove all marks – used for 'deselect all' operation."""
        self._marked.clear()

    # ------------------------------------------------------------------
    # Bulk operations – used by UI filters (cumulative)
    # ------------------------------------------------------------------
    def select_all_except_survivor(self) -> None:
        """Select all files except the survivor(s) of each group.
        Iron Rule 2: cumulative – will not mark the last file in a group.
        """
        for gid, files in self._group_files.items():
            survivors = self._survivors(gid)
            for f in files:
                fid = f['id']
                if fid not in survivors and fid not in self._protected_files:
                    self._marked.add(fid)

    def select_group_except_survivor(self, group_id: int) -> None:
        """Select all files in a single group except its survivor."""
        files = self._group_files.get(group_id, [])
        survivors = self._survivors(group_id)
        for f in files:
            fid = f['id']
            if fid not in survivors and fid not in self._protected_files:
                self._marked.add(fid)

    def deselect_group(self, group_id: int) -> None:
        """Remove marks from all files in a single group."""
        files = self._group_files.get(group_id, [])
        for f in files:
            self._marked.discard(f['id'])

    def apply_smart_filter(self, mode: str) -> None:
        """Apply one of the named smart-select strategies (cumulative).

        Each call preserves already-marked files and marks additional ones
        according to the mode, while strictly respecting Iron Rule 1.

        Supported modes:
        - keep_first:    keep the first file (by order in group), mark the rest
        - keep_last:     keep the last file, mark the rest
        - keep_shortest: keep the file with the shortest path, mark the rest
        - keep_longest:  keep the file with the longest path, mark the rest
        - keep_newest:   keep the file with the largest mtime, mark the rest
        - keep_oldest:   keep the file with the smallest mtime, mark the rest
        - keep_shallow:  keep the file with the shallowest folder depth, mark the rest
        - keep_deep:     keep the file with the deepest folder depth, mark the rest
        - protected_dupes: mark protected files that are duplicated outside protected dirs
        - reference_dupes: mark reference files that are duplicated outside reference dirs
        """
        import os

        for gid, files in self._group_files.items():
            if not self._can_mark_more(gid):
                continue

            # --- Special modes that use protected/reference files as survivors ---
            # These modes require at least 1 non-protected candidate (not 2),
            # because the survivor is the protected/reference file itself.
            if mode == 'protected_dupes':
                protected_ids = {f['id'] for f in files if f['id'] in self._protected_files}
                if not protected_ids:
                    continue
                # Mark all non-protected, currently unmarked files
                candidates = [f for f in files
                              if f['id'] not in self._protected_files
                              and f['id'] not in self._marked]
                for f in candidates:
                    self.mark_file(f['id'], gid)
                continue

            elif mode == 'reference_dupes':
                ref_files = [f for f in files if f.get('is_reference')]
                if not ref_files:
                    continue
                # Mark all non-reference, currently unmarked files
                candidates = [f for f in files
                              if not f.get('is_reference')
                              and f['id'] not in self._protected_files
                              and f['id'] not in self._marked]
                for f in candidates:
                    self.mark_file(f['id'], gid)
                continue

            # --- Standard modes: need at least 2 candidates to keep one survivor ---
            # Candidates: non-protected, currently unmarked
            candidates = [f for f in files
                          if f['id'] not in self._protected_files
                          and f['id'] not in self._marked]
            if len(candidates) < 2:
                continue

            # Select which candidate to keep (survivor of this filter pass)
            keeper_id = None

            if mode == 'keep_first':
                keeper_id = candidates[0]['id']
            elif mode == 'keep_last':
                keeper_id = candidates[-1]['id']
            elif mode == 'keep_shortest':
                keeper_id = min(candidates, key=lambda f: len(f['path']))['id']
            elif mode == 'keep_longest':
                keeper_id = max(candidates, key=lambda f: len(f['path']))['id']
            elif mode == 'keep_newest':
                keeper_id = max(candidates, key=lambda f: f.get('mtime', 0))['id']
            elif mode == 'keep_oldest':
                keeper_id = min(candidates, key=lambda f: f.get('mtime', 0))['id']
            elif mode == 'keep_shallow':
                keeper_id = min(candidates,
                                key=lambda f: f['path'].count(os.sep))['id']
            elif mode == 'keep_deep':
                keeper_id = max(candidates,
                                key=lambda f: f['path'].count(os.sep))['id']
            else:
                continue

            # Mark all candidates except the keeper
            for f in candidates:
                if f['id'] != keeper_id:
                    self.mark_file(f['id'], gid)

    def apply_path_filter(self, condition_func: Callable[[str], bool]) -> None:
        """Apply a path-based cumulative filter.

        ``condition_func`` receives a file path and returns ``True`` for files
        that should be marked for removal.
        """
        for gid, files in self._group_files.items():
            if not self._can_mark_more(gid):
                continue
            for f in files:
                if f['id'] in self._protected_files:
                    continue
                if condition_func(f['path']):
                    self.mark_file(f['id'], gid)

    # ------------------------------------------------------------------
    # Accessors for UI rendering and move worker
    # ------------------------------------------------------------------
    def is_marked(self, file_id: int) -> bool:
        return file_id in self._marked

    def get_marked(self) -> Set[int]:
        """Return a copy of the set of currently marked file ids."""
        return set(self._marked)

    def get_marked_items(self) -> List[dict]:
        """Return full item dicts for all marked files (used by move worker)."""
        result = []
        for gid, files in self._group_files.items():
            for f in files:
                if f['id'] in self._marked:
                    result.append(f)
        return result

    def get_marked_count(self) -> int:
        return len(self._marked)

    def get_group_files(self) -> Dict[int, List[dict]]:
        return {gid: list(files) for gid, files in self._group_files.items()}

    def remove_marked_from_groups(self, marked_ids: Set[int]) -> None:
        """Remove successfully moved/deleted files from the in-memory state.
        Called after a move operation completes.
        """
        self._marked -= marked_ids
        for gid in list(self._group_files.keys()):
            self._group_files[gid] = [f for f in self._group_files[gid]
                                      if f['id'] not in marked_ids]
            # Remove empty groups
            if not self._group_files[gid]:
                del self._group_files[gid]
        self._protected_files -= marked_ids
