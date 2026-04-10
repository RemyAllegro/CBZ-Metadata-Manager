# 📚 CBZ Metadata Manager

A powerful, high-performance GUI application for managing, fetching, and embedding `ComicInfo.xml` metadata into your CBZ/ZIP manga and comic files. 

Built with Tkinter, this tool streamlines the process of organizing large manga libraries by fetching highly accurate metadata from a local database dump (Mangabaka) and pulling rich staff/character data directly from the AniList API.

## ✨ Key Features
- **Drag-and-Drop Interface:** Easily load individual files or entire folders of CBZ files.
- **Smart Title Extraction:** Automatically detects volume and chapter numbers from filenames, even with complex decimal numbering.
- **Batch & Individual Fetching:** Apply the same metadata to an entire series at once, or fetch exact metadata file-by-file for anthologies or mixed folders.
- **Local Series Database:** Save your refined metadata as templates to easily apply to future volumes, complete with custom series alias matching.
- **AniList Integration:** Automatically pulls detailed staff, creators, and characters to enrich your metadata.
- **Multi-threaded Processing:** UI remains perfectly smooth and responsive with progress bars during heavy API calls or bulk XML injections.
- **Filename Search** - By default the program will extract title from the Loaded CBZ to make the search query to Fetch Metadata. 
- **Folder Toggle:** By Checking "Use Folder Name for Search" allows the script to use the parent folder's name (e.g., `One Piece/Chapter 1.cbz` -> searches for "One Piece" instead of "Chapter 1"). Clicking any file in the listbox dynamically updates the search bar to that file's specific title.

---
<img width="2560" height="1387" alt="image" src="https://github.com/user-attachments/assets/4f7679c2-c53f-4e62-b2e4-9f9a7e2c6b4a" />
<img width="2531" height="1377" alt="image" src="https://github.com/user-attachments/assets/f1c6cc23-278b-4f96-80dc-d0a6c8eb4b7e" />

## ⚙️ Requirements & Installation

**Prerequisites:**
- Python 3.8 or higher
- The `series.jsonl` database dump file is placed in the same directory as the script from https://mangabaka.org/database. (Schema - Default, Format JSONL)

**Required Packages:**
Install the required dependencies using pip:
```bash
pip install requests tkinterdnd2
```

*(Alternatively, you can run the script instantly using `uv`):*
```bash
uv run --with tkinterdnd2 cbz_metadata_manager.py
```

---

## 🚀 How to Use: Batch vs. Individual Mode

The application operates in two distinct modes depending on how your files are structured. You can toggle between these modes at the top of the interface.

### 📦 Batch Mode (Default)
**Best for:** Processing an entire folder of chapters or volumes belonging to the *same* series.
- **How it works:** You type the Manga Title into the search bar (or let the script auto-extract it from the first file) and hit "Fetch Metadata". The tool finds the best match and applies that exact same series metadata to **all loaded files** simultaneously.
- **Efficiency:** Only makes a single API/Database query, making it lightning fast for bulk processing.

### 📄 Individual Mode
**Best for:** Processing a mixed folder of different manga series, anthologies, or one-shots.
- **How it works:** The tool reads the filename or folder name of *every single file* loaded into the listbox and fetches unique metadata for each one individually.
- **Efficiency:** Only makes a single API/Database query once per series, making it fast for bulk processing. e.g. If you load a folder with 20 Naruto and 30 Bleach Chapters, it will only make Database Query twice - Once with Naruto Name and once with Bleach Name - Making the process extremely fast in such cases.

---

## 🔄 Fetching Metadata

### 1. Mangabaka Local Dump
The source of metadata is the `series.jsonl` file. Clicking **Fetch Metadata** scans this local dump using an advanced fuzzy-matching algorithm that accounts for romaji, missing characters, and combined text. In Batch Mode, Fetched Metadata is applied to all loaded files; in Individual Mode, Fetched Metadata is applied series-wise (based on Extracted File Names or Folder Name). You can change the Metadata option from the dropdown, and it will only affect that series metadata.

### 2. AniList Enrichment
Once you have the base metadata (which includes an AniList web link), click **Fetch AniList Metadata**. This pulls in highly detailed information (Writers, Pencillers, Cover Artists, Characters) directly from the AniList API. Similar to Fetch Metadata in Individual/Batch Mode.
*Note: This feature uses smart caching, so if you process 50 chapters of the same manga, it only hits the AniList API once!*

### 3. Re-Fetch This File/Series
If you notice an error or want to try a different search term for a specific file, select the file, type a new name into the Search Bar, and click **Refresh Metadata**. This will clear the cached data for that specific file and query the database again using your new search term, updating the dropdown options immediately. In Individual Mode - This will only affect the selected series files (e.g., if you load a folder with 20 Naruto and 30 Bleach Chapters and Refetch Metadata while having Naruto File chosen, it will only change metadata for those 20 Naruto files, leaving Bleach one with its own metadata)

---

## 🗄️ Series Database & Matching

The **Series DB** is a powerful built-in SQLite database that allows you to save perfect metadata templates locally so you don't have to constantly query external sources for your favorite ongoing series.

### Saving & Loading Series
Once you have the metadata looking exactly how you want it for a file, click **Save Series to DB**. This strips out file-specific data (like Volume/Chapter numbers) and saves the core series information.
Later, when downloading a new volume of that series, simply use **Load Series from DB** to instantly apply your perfect metadata without relying on an external fetch.

### Aliases & Smart Matching
Manga often have multiple names (e.g., *Attack on Titan* vs *Shingeki no Kyojin*). When saving a series to the DB, you can assign **Aliases**. 
If you click **Match Files with DB**, the script will compare your filenames against your saved Series names *and* Aliases, automatically mapping the correct metadata to your files with zero manual entry required!

---

## 🔘 Core Operations & Utility Buttons

The application features several one-click utility buttons designed to automate the most tedious parts of metadata entry:

### 🔢 Auto-Fill Volume / Chapter
- **Auto-Fill Volume:** Scans the filename of the currently selected file for volume markers (e.g., `v01`, `Vol 5`) and automatically populates the **Volume** field.
- **Auto-Fill Chapter:** Scans the filename for chapter markers (e.g., `Ch 98.5`, `c02`) and automatically populates the **Number** field.

### 📄 Count Pages
Opens the selected CBZ/ZIP file, counts the exact number of valid image files inside (ignoring structural files like `__MACOSX`), and automatically populates the **PageCount** field.

### 🏷️ Extract Title
Scans the filename and strips away all volume/chapter numbering, scanlator group tags (e.g., `[LuCaZ]`), and file extensions to extract the clean base title, placing it directly into the **Title** field.

### ⚡ Do All
The ultimate time-saver! Clicking this executes a sequence of automated tasks on the **currently selected file** in a single click (USe after Fetch Metadata): 
1. Fetches AniList Metadata
2. Auto-Fills Volume
3. Auto-Fills Chapter
4. Counts Pages
5. Extracts the Title
6. Saves the Series to the Series Database
*Note: If the "Bulk Edit All Files" checkbox is enabled, this will process the entire list at once.*

### 🚀 Do All - Fetch Anilist
Identical to the standard **Do All** button, but skips Anilist Fetching. This is useful when you've already loaded perfect series templates from your Series DB via Match All and simply want to automate the rest of the file-level info in one go.

### 🌐 Refresh Metadata (Web ID)
If you have already fetched metadata but suspect the underlying database has been updated (or you accidentally wiped a field), this button reads the `mangabaka.org(or dev)/manga/ID` link currently sitting in the file's **Web** field. It instantly grabs the most up-to-date metadata directly from that exact ID in your local dump, overriding any manual changes while safely preserving file-specific data like Volume/Chapter numbers.

---

## 🛠️ Configuration (Common Variables)

You can easily customize the tool's behavior by editing the User Configurable Settings block at the very top of `cbz_metadata_manager.py`:

- `MAX_WORKER_THREADS = None` 
  *Controls how many files are written to simultaneously. Leave as `None` to let Python optimize based on your CPU, or set to a hard limit (e.g., `4`) if you experience disk bottlenecking.*
- `WEB_LINK_BLACKLIST = ['amazon.co.jp', 'ja.wikipedia.org']` 
  *Prevents cluttered or unwanted URLs from being embedded into the ComicInfo.xml Web field.*
- `ALLOWED_LOCALIZED_LANGUAGES = {"en", "ja", "ko", ...}` 
  *Restricts which language titles are saved into the `LocalizedSeries` field.*
- `PREFERRED_PUBLISHER_TYPES = ['english', 'en']` 
  *Prioritizes English publishers over raw/native publishers when formatting the Publisher field.*
- `AGE_RATING_MAPPING` 
  *Maps standard Mangabaka content ratings (e.g., "erotica", "suggestive") to standardized ComicRack Age Ratings (e.g., "Mature 17+", "Teen").*

---

## 🧑‍💻 Author
* Built using Python and AI-assisted development.
