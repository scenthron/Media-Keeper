# 📊 Disk Space Analyzer

**This section visualizes the use of disk space, folders, and files. It helps to quickly find "heavy" directories and files using TreeMap and Sunburst charts.**

### 🚀 Workflow
1.  **Directory Selection:** Drag and drop a folder directly onto the chart area, or choose a path in the top input line.
2.  **Scanning:** The selected drive or folder will be scanned automatically, and the chart will be displayed upon completion. The nesting level setting in the top panel limits the depth of directories shown (can be changed using the mouse scroll on hover).
3.  **Chart Design:** You can change the chart design by choosing between circular (Sunburst) and tile (TreeMap) views. A button for randomly changing the color palette is also available.
4.  **Analysis:** Click on the orange-colored sectors of the interactive chart to navigate inside folders for a more detailed analysis. Navigation buttons help you go back or move up one folder level.

### ⚙️ Key Features
*   **Interactive Charts:** Clear visualization of the directory structure.
*   **Central Overlay:** Shows the size and name of the selected folder, and contains navigation buttons (Back, Up one level).
*   **Category Details:** The right table groups files by extensions found in the scanned directory, displaying the total count and size of all files per extension.
*   **Extension Details:** The bottom table displays detailed information for files in the category selected in the right table. Files can be grouped by their storage directories.
*   **Target Folder for Move:** You can set a target folder in the header of the bottom table to move selected files for subsequent analysis.
*   **Move to Specified Directories:** Files can be moved to a user-specified directory via the chart's context menu or the file table.
*   **Context Menu:** A context menu with various useful functions is available by right-clicking on the chart or table files.
*   **Batch Operations:** Select files using checkboxes for quick deletion or relocation to another folder.
*   **Search:** Quick "smart" search by file names is available within the scanned directory.
