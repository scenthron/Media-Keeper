# 🔍 Duplicate Finder

A powerful tool for cleaning your disk from duplicate files based on hash sum calculations (even if the files have been renamed).

---

### 🚀 Workflow
1.  **Choose Sources:** Add folders to search for duplicates in the "Search Sources" section.
2.  **Configure Types:** Select file types to scan in the matrix filter. By default, only media files are scanned.
3.  **Scan:** Click **Scan** to find duplicates.
4.  **Clean:** Apply quick filters (e.g., "Select all with shortest name"). Selected files can be either deleted or moved to a separate folder after configuring it.
5.  **Filters:** The final results of detected duplicates can be sorted using the filter in the table header.
6.  **Sorting:** Convenient sorting of duplicate groups is available when processing results. By clicking the "up-down" arrow button in the table header, groups will be ordered by their processing state. At the very bottom of the list, you will find groups where all "extra" duplicates are correctly selected (meaning exactly one original file remains unmarked). In the middle of the list, groups where no files are selected will be placed. At the very top will be groups where some duplicates are already selected, but not all extra files have been marked yet. For user convenience, sorting occurs only when clicking the button.

### 🛡️ Iron Rule of Safety (N-1)
During any automatic or manual operations, the program **never** allows marking and deleting all files from a duplicate group. At least one original file will always remain unmarked (the "survivor"). This rule exists to preserve user data. If necessary, you can navigate to the folder containing the file and delete it manually using your operating system tools.

### ⚙️ Key Features
*   **Folder Protection:** The ability to mark a folder as "Protected" (files from it will never be deleted).
*   **Search by Reference (Reference Mode):** The program will only search for duplicates of files stored in the directory marked as "Reference". This is useful if you want to find duplicates of specific files only, without being distracted by others. You need to add multiple directories and assign one of them as "Reference". Files in the "Reference" category are also protected from deletion.
*   **Automatic Conflict Resolution:** Rules for incrementing names when moving files with duplicate names.
*   **Preserve Original Paths:** When moving duplicate files to a folder for temporary analysis, the option to preserve the paths of the original files is enabled by default. This allows you to move files back if necessary without changing their original folder structure.
*   **Search for Corrupt Files and Empty Folders:** During scanning, the program automatically finds empty files (0 bytes) and folders containing no files, which you can delete if needed. However, remember that 0-byte files can be used as system files in some applications and structures, so use these tools with caution.
