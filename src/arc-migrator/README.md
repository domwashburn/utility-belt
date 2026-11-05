# Arc sidebar exporter

A small, local-only Python 3 script that exports Arc Spaces and nested folders into browser bookmarks and portable files. No packages, account, or network connection are required. Arc is only read; it is never modified.

## Quick start

1. Quit Arc so its sidebar file is fully saved. Keep a separate backup of `StorableSidebar.json`.
2. Open Terminal in the folder containing `arc_export.py` and run:

   ```sh
   python3 arc_export.py
   ```

3. The `arc-export` folder will contain combined HTML, Markdown, JSON, CSV, TSV, and text files. The `spaces` subfolder also contains a numbered folder for each Space, with its own files in each format. Detected shared Favorites get their own folder too. To import into Chrome, open Bookmark Manager, choose its three-dot menu, select **Import bookmarks**, and select `arc-bookmarks.html`. Review the imported folders before removing anything from Arc. Importing twice can create duplicates.

The script detects the sidebar at `~/Library/Application Support/Arc/StorableSidebar.json` on macOS and in the Arc package's `LocalCache/Local/Arc` directory on Windows. Alternatively, select a copied file or backup with `--input`.

```sh
python3 arc_export.py --list
python3 arc_export.py --format html,json,md --today --output ./my-arc
python3 arc_export.py --input /path/to/StorableSidebar.json --output ./my-arc
python3 arc_export.py --help
```

`--today` adds currently open unpinned tabs in a Today folder per Space. By default, only pinned roots and detected Favorites are exported. Use `--combined-only` to skip individual folders. Existing outputs are protected unless `--force` is given; `--force` replaces matching files but does not remove old Space folders from earlier runs. Use a fresh output directory for a clean archive. CSV/TSV include folder records and a JSON-encoded `path_json` array so names containing separators remain unambiguous. JSON retains nested folders and ordering. Empty folders are retained.

## Scope and compatibility

The parser handles the known `sidebar.containers` layout with alternating ID/object arrays, Space `newContainerIDs`, item `childrenIds` and `parentID`, and tabs, lists, containers, and split views. Arc's sidebar format is internal and undocumented; future or variant versions may differ. Warnings signal missing or unsupported items, and counts help you compare against Arc. Because no personal Arc sidebar was supplied, compatibility with your specific installation has not been verified. If the output seems incomplete, retain your original sidebar backup and try `--today` or provide a copy for diagnosis.

Bookmarks HTML represents links and folders, not live browser Spaces, sessions, profiles, saved passwords, cookies, history, Easels, or other Arc-specific features. Split views become folders when recognizable. Favorites are included when Arc's favorite root IDs are present and understood; compare them manually. Browser imports may place the hierarchy inside an imported-bookmarks folder.

Your exported files contain your browsing links and may include sensitive URLs. Keep them somewhere private.

## Check and restore an individual archive

Keep `arc_restore.py` alongside `arc_export.py`. To check a Space's JSON against its HTML, CSV, and TSV (when those files exist), run:

```sh
python3 arc_restore.py "arc-export/spaces/01 - Work"
```

For this check, include JSON when exporting (the default includes it). The check verifies internal agreement and structure; it cannot prove that Arc's source was interpreted completely. Compare counts and folders with Arc before archiving or deleting anything. Markdown and text are not checked.

To regenerate browser-importable bookmarks HTML from an archived JSON file:

```sh
python3 arc_restore.py "arc-export/spaces/01 - Work" --prepare ./work-restore.html
```

To bring links back to Arc, a possible manual route is to import that HTML into Chrome's Bookmark Manager, then use Arc's **Import from another browser** flow to import from Chrome and organize the resulting folders into a Space. Arc's import and Space creation steps can vary by version; check the result. This is a links-and-folders recovery path, not a native Space restore, and it has not been tested with your Arc installation. Arc's own [import walkthrough](https://www.youtube.com/watch?v=sXzHXHzJMmU) shows importing bookmarks and creating Spaces from folders.

For a broader recovery option, separately retain a copy of the original `StorableSidebar.json` and any Arc backups. The per-Space files are portable link archives, not complete native Arc backups. Arc's own restore feature, if available in your version, may restore a whole sidebar rather than merge an individual Space. Do not replace Arc's live data file with a per-Space export.
