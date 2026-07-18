#To Run via UV - pip install uv and then uv run --with tkinterdnd2 cbz_metadata_manager.py

# Requires-Python: >=3.8
# Requires-Dist: requests
# Requires-Dist: tkinterdnd2

import os
import html
import zipfile
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import tkinterdnd2 as tkdnd
import json
import requests
import logging
from difflib import get_close_matches, SequenceMatcher
import re
from urllib.parse import quote
import webbrowser
from urllib.parse import urlparse, parse_qs
import sqlite3
from datetime import datetime
import tkinter.simpledialog
from threading import Thread
import unicodedata
from collections import defaultdict
import time
from functools import wraps
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread, Lock

# ==============================================================================
# USER CONFIGURABLE SETTINGS
# ==============================================================================

# Maximum number of threads for bulk metadata insertion. (e.g., 4, 8, 16)
# Set to None to let Python auto-calculate based on your CPU.
MAX_WORKER_THREADS = None 

WEB_LINK_BLACKLIST = ['amazon.co.jp', 'ja.wikipedia.org', 'pocket.shonenmagazine.com', 'noeve-grafx.com', 's.accessbooks.jp', 'animate-onlineshop.jp', 'bookpass.auone.jp', 'product.kyobobook.co.kr', 'ebookjapan.yahoo.co.jp', 'booksmart.jp', 'comipo.app', 'galapagosstore.com', 'dbook.docomo.ne.jp', 'comic.k-manga.jp', 'mechacomic.jp', 'books.rakuten.co.jp', 'honto.jp', 'renta.papy.co.jp', 'mangazenkan.com', 'nadeshiko-shoten.jp', 'yamadashoten.com', 'tower.jp', 'video.unext.jp', 'mechacomi.jp', 'maruzenjunkudo.co.jp', 'kinokuniya.co.jp', 'comic.iowl.jp', 'honyaclub.com', 'sp.handycomic.jp', 'galcomi.jp', 'animatebookstore.com', 'ebookstore.sony.jp', 'rakurakucomic.com', 'happycomic.jp', 'paburi.com', 'sokuyomi.jp', 'coicomi.com', 'j-pop.it', 'comic-days.com', 'x.com']

# Allowed 'type' and 'language' values for Mangabaka's Weblinks API
# Allowed Type Inputs = retailer, publisher, webplatform, info, social, news, other
ALLOWED_WEBLINK_TYPES = {"retailer", "publisher", "webplatform", "info"}
ALLOWED_WEBLINK_LANGUAGES = {"en", "fr", "zh", "ja", "ko"}
# --------------------------------------

# Allowed languages for the LocalizedSeries field
ALLOWED_LOCALIZED_LANGUAGES = {"en", "zh", "ja", "ko", "zh-Latn", "ko-Latn", "ja-Latn", "fr", "mr"}

# Title extraction priority for the main 'Series' name (Mangabaka API v2 format)
# The script will try these rules from top to bottom.
SERIES_TITLE_PRIORITY = [
    {"lang": "en", "trait": "official", "is_primary": True},
    {"lang": "en", "trait": "alternative", "is_primary": True},
    {"lang": "en", "trait": None, "is_primary": True},
    {"lang": "ja-Latn", "trait": None, "is_primary": True},
    {"lang": "ko-Latn", "trait": None, "is_primary": True},
    {"lang": "zh-Latn", "trait": None, "is_primary": True},
]

# Publisher language preference for the main Publisher field
PREFERRED_PUBLISHER_TYPES = ['english', 'en']

# Age Rating mapping from Mangabaka content_rating
AGE_RATING_MAPPING = {
    "safe": "Everyone",
    "suggestive": "Teen", 
    "erotica": "Mature 17+",
    "pornographic": "Adults Only 18+"
}

# AniList Character & Staff Parsing Rules
ANILIST_CHARACTER_ROLES = ['MAIN', 'SUPPORTING', 'BACKGROUND']

ANILIST_STAFF_ROLE_MAPPINGS = {
    'story': 'Writer', 'story & art': 'Writer', 'original creator': 'Writer',
    'original story': 'Writer', 'author': 'Writer', 'writer': 'Writer',
    'artist': 'CoverArtist', 'illustrator': 'CoverArtist', 
    'inking': 'Inker', 'color': 'Colorist', 'coloring': 'Colorist',
    'lettering (english)': 'Letterer', 'touch-up art & lettering (english)': 'Letterer',
    'editor': 'Editor', 'editorial': 'Editor', 
    'assistant': 'Penciller', 'assistant (former)': 'Penciller', 'assistant (Former)': 'Penciller', 
    'translation': 'Translator', 'translator (english)': 'Translator'
}

ANILIST_STAFF_REGEX_MAPPINGS = [
    (r'touch-up art & lettering.*', 'Letterer'),
    (r'^translator \(english.*', 'Translator'),
    (r'editing \(.*\)', 'Editor')
]

ANILIST_ART_ROLES = ['character design', 'art', 'story & art']

# The exact ComicInfo.xml fields supported by the GUI (Order matters for UI layout)
METADATA_FIELDS = [
    "Title", "Series", "LocalizedSeries", "AgeRating", "Number", "Count", "Volume",
    "PageCount", "Summary", "Year", "Month", "Day", "Writer", "Penciller", "Inker", "Colorist", 
    "Letterer", "CoverArtist", "Editor", "Translator", "Publisher", "Imprint", "GTIN", "Genre", 
    "Tags", "LanguageISO", "Web", "Notes", "Format", "Characters", "CommunityRating", "Review", 
    "AlternateSeries", "AlternateNumber", "AlternateCount", "Teams", "Locations", "ScanInformation", 
    "StoryArc", "StoryArcNumber", "SeriesGroup", "MainCharacterOrTeam"
]

# UI Tooltips for the metadata fields
FIELD_TOOLTIPS = {
    "Title": "The title of this specific issue or volume (e.g., 'Attack on Titan #1')",
    "Series": "The name of the manga/comic series (e.g., 'Attack on Titan')",
    "LocalizedSeries": "Series name in local language or alternate region name",
    "Number": "Issue number within the series (e.g., 1, 2, 3.5)",
    "Count": "Total number of issues in the series (if known)",
    "Volume": "Volume number for collected editions or multi-volume series",
    "Summary": "Brief description or synopsis of this issue's content",
    "Year": "Publication year (YYYY format)",
    "Month": "Publication month (1-12)",
    "Day": "Publication day (1-31)",
    "LanguageISO": "Language code (e.g., 'en' for English, 'ja' for Japanese)",
    "Web": "Related website URL or online resource",
    "PageCount": "Total number of pages in this issue",
    "Format": "Publication format (e.g., 'TPB', 'One-Shot', 'Annual')",
    "Characters": "Characters featured - separate with commas",
    "SeriesGroup": "Group or Collection this series belongs to",
    "AgeRating": "Content rating indicating appropriate age group"
}

# Dropdown choices for the AgeRating field
AGE_RATING_OPTIONS = [
    "Unknown", "Rating Pending", "Early Childhood", "Everyone", "G", "Everyone 10+", 
    "PG", "Kids to Adults", "Teen", "MA15+", "Mature 17+", "M", "R18+", 
    "Adults Only 18+", "X18+"
]

# Dropdown choices for the Format field
FORMAT_OPTIONS = [
    "Special", "Reference", "Director's Cut", "Box Set", "Box-Set", "Annual", 
    "Anthology", "Epilogue", "One Shot", "One-Shot", "Prologue", "TPB", 
    "Trade Paper Back", "Omnibus", "Compendium", "Absolute", "Graphic Novel", 
    "GN", "FCBD"
]

# Folders containing any of these keywords will prefer 'total_chapters' over 'final_volume' for Manhwa/Manhua/OEL
WEBCOMIC_COUNT_KEYWORDS = ["manhwa", "pornhwa", "manhua", "webcomic", "webtoon"]

# ==============================================================================
# PATTERNS
# ==============================================================================

# External source URL patterns
SOURCE_URL_PATTERNS = {
    "manga_updates": "https://www.mangaupdates.com/series/",
    "my_anime_list": "https://myanimelist.net/manga/",
    "anilist": "https://anilist.co/manga/",
    "anime_planet": "https://www.anime-planet.com/manga/",
    "kitsu": "https://kitsu.app/manga/",
    "shikimori": "https://shikimori.one/mangas/",
    "anime_news_network": "https://www.animenewsnetwork.com/encyclopedia/manga.php?id="
}

APOSTROPHE_MAP = str.maketrans({
    "\u2018": "'",  # ‘
    "\u2019": "'",  # ’
    "\u201B": "'",  # ‛
    "\u02BC": "'",  # ʼ
    "\uFF07": "'",  # ＇
    "`": "'",       # `
    "´": "'",       # ´
})

# Pre-compiled Regex and Function Patterns
VOLUME_PATTERN = re.compile(r'v(?:ol)?\.?\s*(\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?)', re.IGNORECASE)
SEASON_PATTERN = re.compile(r's(?:eason)?\.?\s*(\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?)', re.IGNORECASE)
CHAPTER_PATTERN = re.compile(r'\bc(?:h(?:ap(?:ter)?)?)?\.?\s*(\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?)', re.IGNORECASE)
EPISODE_PATTERN = re.compile(r'\be(?:p(?:isode)?)?\.?\s*(\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?)', re.IGNORECASE)
HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
WHITESPACE_PATTERN = re.compile(r'\s+')
NEWLINE_CLEANUP_PATTERN = re.compile(r'\n\s*\n\s*\n+')
YEAR_PATTERN = re.compile(r'\b(19|20)\d{2}\b')
BRACKET_CONTENT_PATTERN = re.compile(r'\[([^\]]+)\]')
PAREN_CONTENT_PATTERN = re.compile(r'\(([^)]+)\)')
SPECIAL_CHARS_PATTERN = re.compile(r'[^a-zA-Z0-9\s]')
ANILIST_ID_PATTERN = re.compile(r'anilist\.co/manga/(\d+)', re.IGNORECASE)
REVERSED_VOLUME_PATTERN = re.compile(r'(\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?)(?:st|nd|rd|th)?\s*(?:vol|volume)', re.IGNORECASE)
VOLUME_START_PATTERN = re.compile(r'^(?:volume|vol)\.?\s*(\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?)', re.IGNORECASE)
STANDALONE_V_PATTERN = re.compile(r'\bv\.?\s*0*(\d+(?:\.\d+)*(?:-\d+(?:\.\d+)*)?)\b', re.IGNORECASE)
SEPARATOR_PATTERN = re.compile(r'[_\-]+')
EXTENSION_PATTERN = re.compile(r'\.(cbz|cbr|zip|rar|pdf)$', re.IGNORECASE)
TITLE_FALLBACK_PATTERN = re.compile(r'\b(?:v|vol|volume)\.?\s*-?\s*\d+(?:\.\d+)?', re.IGNORECASE)
ANILIST_URL_PATTERN = re.compile(r'anilist\.co/manga/(\d+)')
TITLE_CLEANUP_PATTERNS = [
    re.compile(r'^(.*?)\s*v(?:ol)?(?:ume)?\.?\s*\d+(?:\.\d+)?', re.IGNORECASE),     # V01, Vol01, Vol. 1, Vol 1.5, Vol 1.25, Volume 1, Volume 1.5
    re.compile(r'^(.*?)\s*ch?(?:ap)?(?:ter)?\.?\s*\d+(?:\.\d+)?', re.IGNORECASE), # C1, ch01, chapter 1, ch98.5, ch92.17
    # NEW: Handle combined Season/Side Story + Chapter with multi-decimal support (S01 C07.5, SS C15.17)
    re.compile(r'^(.*?)\s+(?:S\d+|SS\d*)\s+C\d+(?:\.\d+)?', re.IGNORECASE),
    # NEW: Handle standalone Season or Side Story markers (S01, SS, SS2)
    re.compile(r'^(.*?)\s+(?:S\d+|SS\d*)(?:\s|$|\-)', re.IGNORECASE),
    re.compile(r'^(.*?)\s*\d{4}', re.IGNORECASE),                        # year fallback
]
TRAILING_HYPHEN_PATTERN = re.compile(r'[\s\-]+$')
BRACKET_REMOVAL_PATTERN = re.compile(r'\s*\(.*?\)|\s*\[.*?\]')
SCANLATOR_REMOVAL_PATTERN = re.compile(r'\s+(Digital|LuCaZ|1r0n|.*?Scan).*$', re.IGNORECASE)
SPECIAL_CHARS_REMOVAL = re.compile(r'[^\w\s]')
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.jxl', '.gif', '.bmp'}

_API_SESSION = None
_SESSION_LOCK = Lock()

def get_api_session():
    """Get or create shared requests session for connection pooling"""
    global _API_SESSION
    if _API_SESSION is None:
        with _SESSION_LOCK:
            if _API_SESSION is None:
                _API_SESSION = requests.Session()
                _API_SESSION.headers.update({
                    'User-Agent': 'CBZ-Metadata-Manager/4.0',
                    'Accept': 'application/json'
                })
    return _API_SESSION


# Setup logging
logging.basicConfig(filename='cbz_metadata.log', level=logging.INFO, format='%(asctime)s %(levelname)s:%(message)s')

DUMP_PATH = "series.jsonl"
CACHE_PATH = "api_cache.json"
DATABASE_PATH = "metadata_database.db"

# Database initialization
def init_database():
    """Initialize the SQLite database for storing series metadata"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Create series_metadata table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_name TEXT UNIQUE NOT NULL,
            metadata_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create series_aliases table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS series_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            series_name TEXT NOT NULL,
            alias TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (series_name) REFERENCES series_metadata (series_name) ON DELETE CASCADE,
            UNIQUE(series_name, alias)
        )
    ''')
    
    # Create indexes for faster lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_series_name ON series_metadata(series_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_aliases_series ON series_aliases(series_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_aliases_alias ON series_aliases(alias)')
    
    conn.commit()
    conn.close()

def is_valid_source_id(source_id, source_name):
    if source_id is None or str(source_id).strip() in ['', 'null', 'None', '0']:
        return False
    
    # Numeric IDs for most sources
    if source_name in ['my_anime_list', 'anilist', 'kitsu', 'shikimori', 'anime_news_network']:
        return str(source_id).strip('"').replace('-', '').replace('_', '').isalnum()
    
    # Anime-planet, Mangaupdates uses slugs
    if source_name in ['manga_updates', 'anime_planet']:
        return bool(re.match(r'^[a-zA-Z0-9-]+$', str(source_id).strip('"')))
    
    return True


def center_window(window, width=None, height=None):
    window.update_idletasks()
    window.update()
    
    if width and height:
        window_width = width
        window_height = height
    else:
        window_width = window.winfo_reqwidth()
        window_height = window.winfo_reqheight()
        
        if window_width < 100:
            window_width = width or 400
        if window_height < 100:
            window_height = height or 300
    
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    
    x = max(0, x)
    y = max(0, y)
    
    window.geometry(f"{window_width}x{window_height}+{x}+{y}")

class ToolTip:
    """Create a tooltip for a given widget"""
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
    
    def enter(self, event=None):
        self.schedule()
    
    def leave(self, event=None):
        self.unschedule()
        self.hidetip()
    
    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)
    
    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)
    
    def showtip(self, event=None):
        x = self.widget.winfo_rootx() + 25
        y = self.widget.winfo_rooty() + 20
        
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(tw, text=self.text, justify='left',
                      background="#ffffe0", relief='solid', borderwidth=1,
                      font=("tahoma", "8", "normal"), wraplength=300)
        label.pack(ipadx=1)
    
    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()
            
# ==============================================================================
# SERIES DATABASE DIALOG
# ==============================================================================

class SeriesDatabase:
    """Class to handle series metadata database operations using a persistent connection"""
    
    def __init__(self, db_path="series.db"):
        self.db_path = db_path
        # Create a single, persistent connection. check_same_thread=False allows background workers
        # (like the auto-match threaded functions) to safely query the database.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # Enable write-ahead logging (WAL) mode for better concurrent read/write performance
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.init_database()
    
    def __del__(self):
        """Ensure connection is closed when the object is destroyed"""
        if hasattr(self, 'conn'):
            try:
                self.conn.close()
            except Exception:
                pass

    def _normalize_series_name(self, series_name):
        """Remove decimal numbers from series name (e.g., '2.5' but keep '7th', 'Lv. 9999')"""
        if not series_name:
            return series_name
        
        normalized = re.sub(r'\b\d+\.\d+\b\s*', '', series_name)
        normalized = WHITESPACE_PATTERN.sub(' ', normalized).strip()
        
        return normalized
    
    def init_database(self):
        """Initialize the database with required tables"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS series_metadata (
                    series_name TEXT PRIMARY KEY,
                    metadata_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS series_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    series_name TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    FOREIGN KEY (series_name) REFERENCES series_metadata (series_name) ON DELETE CASCADE,
                    UNIQUE(series_name, alias)
                )
            ''')
            
            self.conn.commit()
        except Exception as e:
            logging.error(f"Error initializing database: {e}")
    
    def save_series_metadata(self, series_name, metadata):
        """Save or update series metadata in the database"""
        if not series_name or not series_name.strip():
            raise ValueError("Series name cannot be empty")
        
        series_name = self._normalize_series_name(series_name.strip())
        
        if not series_name:
            raise ValueError("Series name cannot be empty after normalization")
        
        metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO series_metadata 
                (series_name, metadata_json, updated_at) 
                VALUES (?, ?, ?)
            ''', (series_name, metadata_json, datetime.now().isoformat()))
            
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error saving series metadata: {e}")
            return False
    
    def load_series_metadata(self, series_name):
        """Load series metadata from the database"""
        if not series_name or not series_name.strip():
            return None
        
        series_name = series_name.strip()
        cursor = self.conn.cursor()
        
        try:
            cursor.execute(
                'SELECT metadata_json FROM series_metadata WHERE series_name = ?',
                (series_name,)
            )
            result = cursor.fetchone()
            
            if result:
                return json.loads(result[0])
            return None
        except Exception as e:
            logging.error(f"Error loading series metadata: {e}")
            return None
       
    def delete_series(self, series_name):
        """Delete a series from the database (aliases are deleted automatically via CASCADE)"""
        if not series_name or not series_name.strip():
            return False
        
        series_name = series_name.strip()
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('DELETE FROM series_metadata WHERE series_name = ?', (series_name,))
            self.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error deleting series metadata: {e}")
            return False
    
    def search_series(self, search_term):
        """Search for series by name (case-insensitive partial match)"""
        if not search_term or not search_term.strip():
            return []
        
        search_term = f"%{search_term.strip()}%"
        cursor = self.conn.cursor()
        
        try:
            cursor.execute(
                'SELECT series_name, updated_at FROM series_metadata WHERE series_name LIKE ? ORDER BY updated_at DESC',
                (search_term,)
            )
            return [(row[0], row[1]) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error searching series: {e}")
            return []
    
    def save_series_aliases(self, series_name, aliases):
        """Save aliases for a series (replaces all existing aliases)"""
        if not series_name or not series_name.strip():
            raise ValueError("Series name cannot be empty")
        
        series_name = series_name.strip()
        cursor = self.conn.cursor()
        
        try:
            cursor.execute('DELETE FROM series_aliases WHERE series_name = ?', (series_name,))
            
            if aliases:
                alias_data = [(series_name, alias.strip()) for alias in aliases if alias.strip()]
                cursor.executemany(
                    'INSERT INTO series_aliases (series_name, alias) VALUES (?, ?)',
                    alias_data
                )
            
            self.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error saving series aliases: {e}")
            return False
    
    def load_series_aliases(self, series_name):
        """Load aliases for a series"""
        if not series_name or not series_name.strip():
            return []
        
        series_name = series_name.strip()
        cursor = self.conn.cursor()
        
        try:
            cursor.execute(
                'SELECT alias FROM series_aliases WHERE series_name = ? ORDER BY alias',
                (series_name,)
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error loading series aliases: {e}")
            return []
    
    def get_all_series_with_aliases(self):
        """Get all series with their aliases for matching"""
        cursor = self.conn.cursor()
        
        try:
            cursor.execute("""
                SELECT sm.series_name, sm.updated_at, GROUP_CONCAT(sa.alias, '|') as aliases
                FROM series_metadata sm
                LEFT JOIN series_aliases sa ON sm.series_name = sa.series_name
                GROUP BY sm.series_name, sm.updated_at
                ORDER BY sm.updated_at DESC
            """)
            
            results = []
            for row in cursor.fetchall():
                series_name = row[0]
                updated_at = row[1]
                aliases = row[2].split('|') if row[2] else []
                results.append((series_name, updated_at, aliases))
            return results
        except Exception as e:
            logging.error(f"Error getting all series with aliases: {e}")
            return []

    def search_series_with_aliases(self, search_term):
        if not search_term or not search_term.strip():
            return self.get_all_series_with_aliases()
            
        search_pattern = f"%{search_term.strip()}%"
        cursor = self.conn.cursor()
        
        try:
            # Matches search term against series name OR any of its aliases
            cursor.execute("""
                SELECT sm.series_name, sm.updated_at, GROUP_CONCAT(sa.alias, '|') as aliases
                FROM series_metadata sm
                LEFT JOIN series_aliases sa ON sm.series_name = sa.series_name
                WHERE sm.series_name LIKE ? OR sm.series_name IN (
                    SELECT series_name FROM series_aliases WHERE alias LIKE ?
                )
                GROUP BY sm.series_name, sm.updated_at
                ORDER BY sm.updated_at DESC
            """, (search_pattern, search_pattern))
            
            results = []
            for row in cursor.fetchall():
                series_name = row[0]
                updated_at = row[1]
                aliases = row[2].split('|') if row[2] else []
                results.append((series_name, updated_at, aliases))
            return results
        except Exception as e:
            logging.error(f"Error searching series with aliases: {e}")
            return []

# ==============================================================================
# ALIAS EDITOR DIALOG
# ==============================================================================


class AliasEditorDialog(tk.Toplevel):
    
    def __init__(self, parent, series_name, current_aliases=None):
        super().__init__(parent)
        self.parent = parent
        self.series_name = series_name
        self.aliases = current_aliases or []
        self.result = None
        
        self.title(f"Edit Aliases - {series_name}")
        self.transient(parent)
        self.grab_set()
        
        self.create_widgets()
        self.populate_aliases()
        
        self.geometry("500x400")
        self.update_idletasks()
        center_window(self, 500, 400)

        
    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill='both', expand=True)
        
        info_label = ttk.Label(main_frame, text=f"Series: {self.series_name}")
        info_label.pack(anchor='w', pady=(0, 10))
        ToolTip(info_label, f"Editing aliases for the series: {self.series_name}")
        
        aliases_frame = ttk.LabelFrame(main_frame, text="Aliases (one per line)", padding=5)
        aliases_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        self.aliases_text = tk.Text(aliases_frame, height=15, width=50)
        scrollbar = ttk.Scrollbar(aliases_frame, orient='vertical', command=self.aliases_text.yview)
        self.aliases_text.configure(yscrollcommand=scrollbar.set)
        
        self.aliases_text.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        ToolTip(self.aliases_text, "Enter alternative names for this series, one per line.\nThese will be used for automatic file matching.")
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x')
        
        save_btn = ttk.Button(button_frame, text="Save", command=self.save_aliases)
        save_btn.pack(side='left', padx=(0, 5))
        ToolTip(save_btn, "Save the aliases and close the dialog")
        
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.cancel)
        cancel_btn.pack(side='left')
        ToolTip(cancel_btn, "Cancel editing and close the dialog without saving")

    def populate_aliases(self):
        if self.aliases:
            self.aliases_text.insert('1.0', '\n'.join(self.aliases))

    def save_aliases(self):
        content = self.aliases_text.get('1.0', 'end-1c')
        self.result = [line.strip() for line in content.split('\n') if line.strip()]
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

series_db = SeriesDatabase()

local_dump = []
if os.path.exists(DUMP_PATH):
    logging.info("Building lightweight memory index from dump...")
    try:
        # Open in binary mode ('rb') to perfectly track exact file byte offsets
        with open(DUMP_PATH, 'rb') as f:
            offset = 0
            for line in f:
                if not line.strip():
                    offset += len(line)
                    continue
                
                raw = json.loads(line.decode('utf-8'))
                
                # Store ONLY what the fuzzy matcher needs + the file offset
                slim_entry = {
                    "id": raw.get("id"),
                    "state": raw.get("state"),
                    "merged_with": raw.get("merged_with"),
                    "title": raw.get("title"),
                    "native_title": raw.get("native_title"),
                    "romanized_title": raw.get("romanized_title"),
                    "secondary_titles": raw.get("secondary_titles"),
                    "_offset": offset  # <-- The magic key to find this data later
                }
                local_dump.append(slim_entry)
                offset += len(line)
                
        logging.info(f"Loaded {len(local_dump)} series into lightweight index.")
    except Exception as e:
        logging.error(f"Failed to load local dump: {e}")
 
def normalize_romaji_cached(text, cache={}):
    """Normalize romaji with caching for performance - IMPROVED VERSION"""
    if not text or text in cache:
        return cache.get(text, "")
    
    original_text = text
    text = text.lower()
    
    text = text.translate(APOSTROPHE_MAP)
    
    macron_map = {
        'Ã„Â': 'aa', 'Ã„Â«': 'ii', 'Ã…Â«': 'uu', 'Ã„â€œ': 'ee', 'Ã…Â': 'ou',
        'ÃƒÂ¢': 'aa', 'ÃƒÂª': 'ee', 'ÃƒÂ®': 'ii', 'ÃƒÂ´': 'ou', 'ÃƒÂ»': 'uu',
        'Ãƒ ': 'a', 'ÃƒÂ¨': 'e', 'ÃƒÂ¬': 'i', 'ÃƒÂ²': 'o', 'ÃƒÂ¹': 'u',
        'ÃƒÂ¡': 'a', 'ÃƒÂ©': 'e', 'ÃƒÂ­': 'i', 'ÃƒÂ³': 'o', 'ÃƒÂº': 'u',
    }
    for k, v in macron_map.items():
        text = text.replace(k, v)
    
    text = unicodedata.normalize("NFKD", text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.replace("–", " ").replace("—", " ").replace("-", " ")
    text = re.sub(r"[^\w\s'.!?:;]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    cache[original_text] = text
    return text

def build_merge_map(local_dump):
    """Build a map of merged entries to avoid duplicates"""
    merge_map = {}  # merged_id -> target_id
    active_ids = set()
    
    for entry in local_dump:
        entry_id = entry.get("id")
        state = entry.get("state", "").lower()
        merged_with = entry.get("merged_with")
        
        if state == "merged" and merged_with:
            merge_map[entry_id] = merged_with
        elif state == "active":
            active_ids.add(entry_id)
    
    return merge_map, active_ids

def resolve_merged_entry(entry_id, merge_map):
    """Resolve a merged entry to its final target"""
    original_id = entry_id
    visited = set()
    
    while entry_id in merge_map and entry_id not in visited:
        visited.add(entry_id)
        entry_id = merge_map[entry_id]
        
        if len(visited) > 10:
            logging.warning(f"Merge chain too long for ID {original_id}, stopping at {entry_id}")
            break
    
    return entry_id

# Global cache for merge map to avoid rebuilding it every time
_merge_map_cache = None
_merge_map_cache_size = 0

def get_cached_merge_map():
    """Get cached merge map or build it if needed"""
    global _merge_map_cache, _merge_map_cache_size
    
    if not local_dump:
        return {}, set()
    
    current_size = len(local_dump)
    
    # Rebuild cache if dump size changed
    if _merge_map_cache is None or _merge_map_cache_size != current_size:
        logging.info("Building merge map cache...")
        _merge_map_cache = build_merge_map(local_dump)
        _merge_map_cache_size = current_size
        merge_map, active_ids = _merge_map_cache
        logging.info(f"Merge map built: {len(merge_map)} merges, {len(active_ids)} active entries")
    
    return _merge_map_cache

@lru_cache(maxsize=1000)

def find_best_match_cached_merge_aware(title):
    """IMPROVED: Version that uses cached merge map with optimized sorting and strict matching"""
    if not local_dump:
        return []
    
    search_term = title.strip()
    if not search_term:
        return []
    
    # 1. USE THE CACHED MAP FOR PERFORMANCE
    merge_map, active_ids = get_cached_merge_map()
    
    search_term_norm = normalize_romaji_cached(search_term)
    search_words = set(search_term_norm.split())
    search_len = len(search_term_norm)
    
    matches = []
    processed_final_ids = set()  # Track final IDs to avoid duplicates
    
    for entry in local_dump:
        entry_id = entry.get("id")
        state = entry.get("state", "").lower()
        
        # Completely skip merged entries early
        if state == "merged":
            continue
        
        final_id = resolve_merged_entry(entry_id, merge_map)
        
        if final_id in processed_final_ids:
            continue
        
        if final_id != entry_id:
            actual_entry = next((e for e in local_dump if e.get("id") == final_id), None)
            if not actual_entry:
                continue
        else:
            actual_entry = entry
        
        texts_to_check = []
        
        for field in ["title", "native_title", "romanized_title"]:
            val = actual_entry.get(field)
            if val:
                texts_to_check.append(val)
        
        secondary = actual_entry.get("secondary_titles")
        if isinstance(secondary, dict):
            for lang_titles in secondary.values():
                if isinstance(lang_titles, list):
                    for t in lang_titles:
                        if isinstance(t, dict) and t.get("title"):
                            texts_to_check.append(t["title"])
        
        best_score = 0
        best_match_text = None
        
        for text in texts_to_check:
            text_norm = normalize_romaji_cached(text)
            
            # Exact match
            if text_norm == search_term_norm:
                best_score = 100
                best_match_text = text
                break
            
            # Substring matching
            elif search_term_norm in text_norm:
                ratio = search_len / len(text_norm)
                if ratio > 0.4:
                    score = min(95, int(65 + (ratio * 30)))
                    if score > best_score:
                        best_score = score
                        best_match_text = text
            
            # Reverse substring
            elif text_norm in search_term_norm and len(text_norm) >= 4:
                ratio = len(text_norm) / search_len
                if ratio > 0.4:
                    score = min(85, int(50 + (ratio * 35)))
                    if score > best_score:
                        best_score = score
                        best_match_text = text
            
            # Word overlap (Restored strict `len(overlap) >= min(2, len(search_words))` rule)
            else:
                text_words = set(text_norm.split())
                overlap = search_words & text_words
                
                # Strict overlap rule prevents false positives from single-word matches
                if overlap and len(overlap) >= min(2, len(search_words)):
                    overlap_ratio = len(overlap) / len(search_words) if search_words else 0
                    text_coverage = len(overlap) / len(text_words) if text_words else 0
                    
                    if overlap_ratio >= 0.5:
                        word_score = int(45 + (overlap_ratio * 30))
                        if word_score > best_score:
                            best_score = word_score
                            best_match_text = text
                    elif text_coverage >= 0.6 and overlap_ratio >= 0.3:
                        word_score = int(40 + (text_coverage * 25))
                        if word_score > best_score:
                            best_score = word_score
                            best_match_text = text
                
                # Character-level fuzzy matching for short terms
                if best_score < 50 and len(search_term_norm) <= 6:
                    search_chars = set(search_term_norm.replace(' ', ''))
                    text_chars = set(text_norm.replace(' ', ''))
                    char_overlap = len(search_chars & text_chars)
                    
                    if char_overlap >= max(3, len(search_chars) * 0.8):
                        char_score = int(30 + (char_overlap / len(search_chars)) * 20)
                        if char_score > best_score:
                            best_score = char_score
                            best_match_text = text
        
        if best_score >= 65:
            matches.append((actual_entry, best_score, best_match_text))
            processed_final_ids.add(final_id)
            
            # Fast break for exact matches
            if best_score == 100 and len(matches) >= 30:
                break
                
    # Sort ONCE at the very end
    matches.sort(key=lambda x: x[1], reverse=True)
    
    result_entries = [m[0] for m in matches[:30]]
    return result_entries


def get_metadata_from_dump(title):
    """Fixed version using byte-offsets for massive RAM reduction"""
    if not title or not title.strip():
        return []
    
    logging.info(f"Fetching metadata for: {title}")
    
    matches = find_best_match_cached_merge_aware(title)
    if matches:
        try:
            metadata_results = []
            # Open the file once to grab the full JSON for our top matches
            with open(DUMP_PATH, 'rb') as f:
                for match in matches:
                    # Jump to the exact byte in the 3.3GB file!
                    f.seek(match["_offset"])
                    full_raw_json = json.loads(f.readline().decode('utf-8'))
                    
                    # Extract using the FULL json, not the slim match
                    metadata = MetadataGUI.extract_metadata(full_raw_json)
                    metadata_results.append(metadata)
            
            logging.info(f"Found {len(metadata_results)} local matches")
            return metadata_results
            
        except Exception as e:
            logging.error(f"Error processing local matches: {e}")
    
    logging.info(f"No metadata found locally for: {title}")
    return []

def get_metadata_from_dump_by_id(entry_id):
    """Fetch exact match from local dump using the Mangabaka numeric ID and byte-offset"""
    if not local_dump:
        return None
        
    try:
        entry_id = int(entry_id)
        merge_map, _ = get_cached_merge_map()
        final_id = resolve_merged_entry(entry_id, merge_map)
        
        for entry in local_dump:
            if entry.get("id") == final_id:
                # We found the ID, jump to the file offset and grab the full data
                with open(DUMP_PATH, 'rb') as f:
                    f.seek(entry["_offset"])
                    full_raw_json = json.loads(f.readline().decode('utf-8'))
                    return MetadataGUI.extract_metadata(full_raw_json)
    except Exception as e:
        logging.error(f"Error fetching by ID: {e}")
        
    return None

def create_comicinfo_xml(metadata):
    """Create ComicInfo.xml ensuring no string literal 'None' or '[]' values slip in"""
    comic_info = ET.Element("ComicInfo")
    comic_info.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    comic_info.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    
    invalid_literals = {"none", "null", "[]", "{}"}
    
    for key, value in metadata.items():
        if value is not None:
            str_val = str(value).strip()
            # Prevent literal 'None' strings from writing to the XML
            if str_val and str_val.lower() not in invalid_literals:
                element = ET.SubElement(comic_info, key)
                element.text = str_val
    
    xml_str = ET.tostring(comic_info, encoding='unicode', method='xml')
    return f'<?xml version="1.0" encoding="utf-8"?>\n{xml_str}'

def insert_comicinfo_into_cbz(cbz_path, xml_data):
    """Insert ComicInfo.xml into CBZ with proper resource management"""
    temp_path = cbz_path + '.tmp'
    try:
        with zipfile.ZipFile(cbz_path, 'r') as original:
            with zipfile.ZipFile(temp_path, 'w', compression=zipfile.ZIP_DEFLATED) as new_zip:
                for item in original.infolist():
                    if item.filename != "ComicInfo.xml":
                        data = original.read(item.filename)
                        new_zip.writestr(item, data)
                new_zip.writestr("ComicInfo.xml", xml_data.encode('utf-8'))
        
        os.replace(temp_path, cbz_path)
        logging.info(f"Successfully inserted metadata into {cbz_path}")
    except Exception as e:
        logging.error(f"Failed to insert metadata into {cbz_path}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        raise

def extract_volume_from_filename(filename):
    for pattern in [VOLUME_PATTERN, VOLUME_START_PATTERN, STANDALONE_V_PATTERN, REVERSED_VOLUME_PATTERN, SEASON_PATTERN]:
        match = pattern.search(filename)
        if match:
            return match.group(1)
    return None


def extract_chapter_from_filename(filename):
    for pattern in [CHAPTER_PATTERN, EPISODE_PATTERN]:
        match = pattern.search(filename)
        if match:
            return match.group(1)
    return None

def extract_anilist_id_from_url(url):
    """Dramatically simplified, bulletproof regex extraction"""
    if not url or not isinstance(url, str):
        raise ValueError("URL is empty or not a string")
        
    match = ANILIST_URL_PATTERN.search(url)
    if not match:
        raise ValueError(f"No valid AniList manga ID found in URL: {url}")
        
    return match.group(1)

def rate_limit(max_calls_per_minute=60):
    """Decorator to limit API calls per minute"""
    min_interval = 60.0 / max_calls_per_minute
    last_called = [0.0]
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            left_to_wait = min_interval - elapsed
            if left_to_wait > 0:
                time.sleep(left_to_wait)
            ret = func(*args, **kwargs)
            last_called[0] = time.time()
            return ret
        return wrapper
    return decorator

@rate_limit(max_calls_per_minute=85)  # 90 rate limit for AniList

def make_anilist_request(query, variables, max_retries=3):
    """Make a rate-limited request to AniList API with retry logic"""
    for attempt in range(max_retries):
        try:
            response = get_api_session().post(
                'https://graphql.anilist.co',
                json={'query': query, 'variables': variables},
                timeout=15,  # Increased timeout
                headers={'User-Agent': 'CBZ-Metadata-Tool/2.0'}
            )
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                print(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            print(f"Request timeout on attempt {attempt + 1}/{max_retries}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
        except requests.exceptions.RequestException as e:
            print(f"Request error on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
    
    return None

def fetch_anilist_metadata(anilist_id, max_pages_per_type=50):
    """Fetch metadata from AniList GraphQL API with pagination for both staff and characters"""
    if not anilist_id or not str(anilist_id).isdigit():
        logging.error(f"Invalid or missing AniList ID: '{anilist_id}'")
        return None

    def fetch_pages(query_template, field_name, initial_edges, initial_page_info):
        """Helper to paginate any edge type without repeating loop logic"""
        edges = initial_edges.copy()
        page_info = initial_page_info
        page = page_info['currentPage']
        fetched = 0

        while page_info['hasNextPage'] and fetched < max_pages_per_type:
            page += 1
            fetched += 1
            print(f"Fetching {field_name} page {page}...")

            try:
                data = make_anilist_request(query_template, {'id': int(anilist_id), 'page': page})
                if not data or 'data' not in data or not data['data']['Media']:
                    break
                page_data = data['data']['Media'][field_name]
                edges.extend(page_data['edges'])
                page_info = page_data['pageInfo']
            except Exception as e:
                print(f"Error fetching {field_name} page {page}: {e}")
                break

        if fetched >= max_pages_per_type and page_info.get('hasNextPage'):
            print(f"Reached maximum limit ({max_pages_per_type}). Some {field_name} may not be included.")

        return edges, fetched

    initial_query = """
    query ($id: Int) {
        Media(id: $id, type: MANGA) {
            id title { romaji english native }
            characters(perPage: 100, sort: FAVOURITES_DESC) {
                pageInfo { hasNextPage currentPage }
                edges { role node { name { first middle last full native alternative } } }
            }
            staff(perPage: 100, sort: FAVOURITES_DESC) {
                pageInfo { hasNextPage currentPage }
                edges { role node { name { full } } }
            }
        }
    }"""

    page_query = """
    query ($id: Int, $page: Int) {
        Media(id: $id, type: MANGA) {
            %s(page: $page, perPage: 100, sort: FAVOURITES_DESC) {
                pageInfo { hasNextPage currentPage }
                edges { role node { name { %s } } }
            }
        }
    }"""

    try:
        print(f"Fetching initial data for AniList ID: {anilist_id}")
        data = make_anilist_request(initial_query, {'id': int(anilist_id)})

        if not data or 'data' not in data or not data['data']['Media']:
            logging.error(f"No data found for AniList ID: {anilist_id}")
            return None

        media = data['data']['Media']

        # Paginate Staff
        staff_query = page_query % ("staff", "full")
        all_staff, staff_pages = fetch_pages(staff_query, "staff", media['staff']['edges'], media['staff']['pageInfo'])

        # Paginate Characters
        char_query = page_query % ("characters", "first middle last full native alternative")
        all_chars, char_pages = fetch_pages(char_query, "characters", media['characters']['edges'], media['characters']['pageInfo'])

        media['staff']['edges'] = all_staff
        media['characters']['edges'] = all_chars

        print(f"Result: Total staff: {len(all_staff)} (from {staff_pages + 1} pages)")
        print(f"Result: Total characters: {len(all_chars)} (from {char_pages + 1} pages)")

        return parse_anilist_data(media)

    except Exception as e:
        logging.error(f"AniList API error: {e}")
        return None

def construct_character_name(name_obj):
    """Construct the most complete character name from available fields"""
    if not name_obj:
        return None
    
    first = (name_obj.get('first') or '').strip()
    middle = (name_obj.get('middle') or '').strip()
    last = (name_obj.get('last') or '').strip()
    
    if first or middle or last:
        name_parts = []
        if first:
            name_parts.append(first)
        if middle:
            name_parts.append(middle)
        if last:
            name_parts.append(last)
        
        if name_parts:
            constructed_name = ' '.join(name_parts)
            full_name = (name_obj.get('full') or '').strip()
            if len(constructed_name) > len(full_name):
                return constructed_name
    
    full_name = (name_obj.get('full') or '').strip()
    if full_name:
        return full_name
    
    alternatives = name_obj.get('alternative', [])
    if alternatives and alternatives[0]:
        alt_name = alternatives[0]
        if alt_name:  # Check if alternative name is not None
            return alt_name.strip()
    
    return None

def parse_anilist_data(media_data):
    """Parse AniList API response and extract relevant metadata"""
    metadata = {}
    
    try:
        characters = []
        if media_data.get('characters', {}).get('edges'):
            for char_edge in media_data['characters']['edges']:
                name_obj = char_edge.get('node', {}).get('name', {})
                char_name = construct_character_name(name_obj)
                char_role = char_edge.get('role', '').upper()
                
                # Check against global character roles
                if char_name and char_role in ANILIST_CHARACTER_ROLES:
                    characters.append(char_name)
        metadata['Characters'] = ', '.join(characters)
        
        staff_roles = {
            'Writer': [], 'Penciller': [], 'Inker': [], 'Colorist': [],
            'Letterer': [], 'CoverArtist': [], 'Editor': [], 'Translator': []
        }
        
        if media_data.get('staff', {}).get('edges'):
            for staff_edge in media_data['staff']['edges']:
                role = staff_edge.get('role', '').lower()
                staff_name = staff_edge.get('node', {}).get('name', {}).get('full')
                
                if not staff_name:
                    continue
                
                # Check for global art roles
                is_art_role = any(art_role in role for art_role in ANILIST_ART_ROLES)
                
                is_touchup_lettering = 'touch-up art & lettering' in role.lower()
                is_touchup = 'touch-up' in role.lower()
                
                if is_art_role and not is_touchup_lettering and not is_touchup:
                    for art_field in ['CoverArtist']: # Changed from Artist (CoverArtist)
                        staff_roles[art_field].append(staff_name)
                
                # Apply global regex mappings first
                matched = False
                for pattern, target_field in ANILIST_STAFF_REGEX_MAPPINGS:
                    if re.match(pattern, role.lower(), re.IGNORECASE):
                        staff_roles[target_field].append(staff_name)
                        matched = True
                        break
                
                # Apply standard global role mappings
                if not matched:
                    role_lower = role.lower()
                    if role_lower in ANILIST_STAFF_ROLE_MAPPINGS:
                        staff_roles[ANILIST_STAFF_ROLE_MAPPINGS[role_lower]].append(staff_name)
        
        for role, names in staff_roles.items():
            if names:
                unique_names = []
                seen = set()
                for name in names:
                    if name not in seen:
                        unique_names.append(name)
                        seen.add(name)
                metadata[role] = ', '.join(unique_names)
            else:
                metadata[role] = ''
        
        return metadata
    
    except Exception as e:
        print(f"Error parsing AniList data: {e}")
        return {}
        
def count_pages_in_cbz(path):
    try:
        with zipfile.ZipFile(path, 'r') as cbz:
            count = 0
            for name in cbz.namelist():
                if name.startswith('__MACOSX/'):
                    continue
                _, ext = os.path.splitext(name)
                if ext.lower() in IMAGE_EXTENSIONS:
                    count += 1
            return count
    except Exception as e:
        logging.error(f"Error counting pages in {path}: {e}")
        return 0

def auto_extract_title(filename):
    name = os.path.splitext(os.path.basename(filename))[0]
    
    for pattern in TITLE_CLEANUP_PATTERNS:
        match = pattern.search(name)
        if match:
            title = match.group(1).strip()
            title = re.sub(r'[\s\-]+$', '', title)
            return title
    
    cleaned = BRACKET_REMOVAL_PATTERN.sub('', name)
    cleaned = SCANLATOR_REMOVAL_PATTERN .sub('', cleaned)
    return cleaned.strip() if cleaned.strip() else None

def natural_sort_key(path):
    # Sort by full path so files in the same folder stay grouped together
    # USE SINGLE BACKSLASHES HERE
    parts = re.split(r'(\d+(?:\.\d+)?)', path.replace('\\', '/').lower())

    key = []
    for part in parts:
        if not part:
            continue
        # USE SINGLE BACKSLASHES HERE TOO
        if re.fullmatch(r'\d+(?:\.\d+)?', part):
            key.append((0, float(part) if '.' in part else int(part)))
        else:
            key.append((1, part))
    return key
    
class SeriesManagerDialog(tk.Toplevel):
    """Dialog for managing saved series metadata"""
    
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Series Database Manager")
        self.transient(parent)
        self.grab_set()
        
        self.selected_series = None
        self.load_to_all = True
        self.match_mode = False
        self.create_widgets()
        self.refresh_series_list()
        
        self.geometry("900x600")
        self.update_idletasks()
        center_window(self, 900, 600)

    def create_widgets(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill='both', expand=True)
        
        search_frame = ttk.Frame(main_frame)
        search_frame.pack(fill='x', pady=(0, 10))
        
        search_label = ttk.Label(search_frame, text="Search Series:")
        search_label.pack(side='left')
        ToolTip(search_label, "Search through saved series by name or alias")
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side='left', fill='x', expand=True, padx=(5, 0))
        self.search_entry.bind('<KeyRelease>', self.on_search)
        ToolTip(self.search_entry, "Type to filter the series list by name or alias")
        
        list_frame = ttk.LabelFrame(main_frame, text="Saved Series", padding=5)
        list_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        columns = ('Series', 'Aliases', 'Last Updated')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        self.tree.heading('Series', text='Series Name')
        self.tree.heading('Aliases', text='Aliases')
        self.tree.heading('Last Updated', text='Last Updated')
        self.tree.column('Series', width=300)
        self.tree.column('Aliases', width=300)
        self.tree.column('Last Updated', width=150)
        ToolTip(self.tree, "Double-click on a series to load its metadata.\nShows series name, aliases, and last update date.")
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        self.tree.bind('<Double-1>', self.on_series_select)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x')
        
        load_all_btn = ttk.Button(button_frame, text="Load to All Files", command=self.load_to_all_files)
        load_all_btn.pack(side='left', padx=(0, 5))
        ToolTip(load_all_btn, "Load selected series metadata to all files in the current list")
        
        load_selected_btn = ttk.Button(button_frame, text="Load to Selected File", command=self.load_to_selected_file)
        load_selected_btn.pack(side='left', padx=(0, 5))
        ToolTip(load_selected_btn, "Load selected series metadata only to the currently selected file")
        
        match_file_btn = ttk.Button(button_frame, text="Match - File", command=self.match_current_file)
        match_file_btn.pack(side='left', padx=(0, 5))
        ToolTip(match_file_btn, "Try to automatically match the current file with a series from the database")
        
        match_all_btn = ttk.Button(button_frame, text="Match - All", command=self.match_all_files)
        match_all_btn.pack(side='left', padx=(0, 5))
        ToolTip(match_all_btn, "Try to automatically match all files with series from the database")
        
        edit_aliases_btn = ttk.Button(button_frame, text="Edit Aliases", command=self.edit_aliases)
        edit_aliases_btn.pack(side='left', padx=(0, 5))
        ToolTip(edit_aliases_btn, "Edit the aliases for the selected series")
        
        delete_btn = ttk.Button(button_frame, text="Delete Selected", command=self.delete_selected_series)
        delete_btn.pack(side='left', padx=(0, 5))
        ToolTip(delete_btn, "Delete the selected series from the database (cannot be undone)")
        
        refresh_btn = ttk.Button(button_frame, text="Refresh", command=self.refresh_series_list)
        refresh_btn.pack(side='left', padx=(0, 15))
        ToolTip(refresh_btn, "Refresh the series list from the database")
        
        close_btn = ttk.Button(button_frame, text="Close", command=self.destroy)
        close_btn.pack(side='right')
        ToolTip(close_btn, "Close the series manager dialog")
        
    def refresh_series_list(self):
        self.search_var.set("")
        results = series_db.get_all_series_with_aliases()
        self.populate_tree(results)
        
    def populate_tree(self, series_list):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for series_data in series_list:
            try:
                if len(series_data) == 3:
                    series_name, updated_at, aliases = series_data

                    try:
                        if updated_at:
                            dt = datetime.fromisoformat(updated_at)
                            formatted_date = dt.strftime('%Y-%m-%d %H:%M')
                        else:
                            formatted_date = ""
                    except Exception as date_error:
                        print(f"Date formatting error for {series_name}: {date_error}")
                        formatted_date = str(updated_at) if updated_at else ""

                    if aliases:
                        if isinstance(aliases, list):
                            valid_aliases = [a.strip() for a in aliases if a and a.strip()]
                            aliases_text = ", ".join(valid_aliases)
                        elif isinstance(aliases, str):
                            alias_list = [a.strip() for a in aliases.split('|') if a and a.strip()]
                            aliases_text = ", ".join(alias_list)
                        else:
                            aliases_text = str(aliases)
                    else:
                        aliases_text = ""

                    self.tree.insert('', 'end', values=(series_name, aliases_text, formatted_date))

                elif len(series_data) == 2:
                    series_name, updated_at = series_data
                    try:
                        dt = datetime.fromisoformat(updated_at)
                        formatted_date = dt.strftime('%Y-%m-%d %H:%M')
                    except (ValueError, AttributeError):
                        formatted_date = str(updated_at)
                    
                    self.tree.insert('', 'end', values=(series_name, "", formatted_date))
                else:
                    series_name = series_data[0] if len(series_data) > 0 else "Unknown"
                    self.tree.insert('', 'end', values=(series_name, "Error", "Error"))

            except Exception as e:
                print(f"Error processing series data {series_data}: {e}")
                safe_name = str(series_data[0]) if len(series_data) > 0 else "Error"
                self.tree.insert('', 'end', values=(safe_name, "Error", "Error"))



    def on_search(self, event=None):
        search_term = self.search_var.get().strip()
        if search_term:
            results = series_db.search_series_with_aliases(search_term)
            self.populate_tree(results)
        else:
            self.refresh_series_list()

    def edit_aliases(self):
        """Edit aliases for the selected series"""
        series_name = self.get_selected_series()
        if not series_name:
            messagebox.showwarning("No Selection", "Please select a series to edit aliases.")
            return
        
        current_aliases = series_db.load_series_aliases(series_name)
        
        dialog = AliasEditorDialog(self, series_name, current_aliases)
        self.wait_window(dialog)
        
        if dialog.result is not None:
            if series_db.save_series_aliases(series_name, dialog.result):
                messagebox.showinfo("Success", f"Aliases updated for '{series_name}'")
                self.refresh_series_list()
            else:
                messagebox.showerror("Error", f"Failed to update aliases for '{series_name}'")
        
    def get_selected_series(self):
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            return item['values'][0]  # Series name is in the first column
        return None
    
    def on_series_select(self, event):
        self.load_to_all_files()
    
    def load_to_all_files(self):
        series_name = self.get_selected_series()
        if not series_name:
            messagebox.showwarning("No Selection", "Please select a series to load.")
            return
        
        self.selected_series = series_name
        self.load_to_all = True
        self.match_mode = False
        self.destroy()
    
    def load_to_selected_file(self):
        series_name = self.get_selected_series()
        if not series_name:
            messagebox.showwarning("No Selection", "Please select a series to load.")
            return
        
        self.selected_series = series_name
        self.load_to_all = False
        self.match_mode = False
        self.destroy()
    
    def match_current_file(self):
        self.selected_series = None
        self.load_to_all = False
        self.match_mode = True
        self.destroy()
    
    def match_all_files(self):
        self.selected_series = None
        self.load_to_all = True
        self.match_mode = True
        self.destroy()
    
    def delete_selected_series(self):
        series_name = self.get_selected_series()
        if not series_name:
            messagebox.showwarning("No Selection", "Please select a series to delete.")
            return
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{series_name}' from the database?\n\nThis will also delete all associated aliases."):
            if series_db.delete_series(series_name):
                messagebox.showinfo("Deleted", f"Successfully deleted '{series_name}' and its aliases")
                self.refresh_series_list()
            else:
                messagebox.showerror("Error", f"Failed to delete '{series_name}'")

class MetadataGUI(tkdnd.Tk):
    def __init__(self):
        super().__init__()
        self.title("CBZ Metadata Manager")
        self.geometry("1600x1000")
        self.minsize(1200, 800)
        
        self._progress_lock = Lock()
        self._metadata_lock = Lock()
        self._cbz_paths_lock = Lock()
        
        self.metadata_mode = tk.StringVar(value="batch")
        self.individual_metadata_cache = {}
        self.batch_processing = False
        self.title_var = tk.StringVar()
        self.dropdown_selection_per_file = {}
        self.bulk_edit_enabled = tk.BooleanVar(value=False)
        self.use_folder_name_var = tk.BooleanVar(value=False)

        self.cbz_paths = []
        self.file_metadata = {}
        self.original_metadata = {}
        self.current_index = 0  
        self.metadata_options = []
             
        # Link class variables to global configurations
        self.fields = METADATA_FIELDS
        self.field_tooltips = FIELD_TOOLTIPS
        self.age_rating_options = AGE_RATING_OPTIONS
        self.format_options = FORMAT_OPTIONS
        
        self.before_entries = {}
        self.after_entries = {}
        self.dropdown_var = tk.StringVar()
        self.title_entry = tk.StringVar()
        
        self.create_widgets()
        
        self.update_idletasks()
        center_window(self, 1600, 1000)

    def setup_drag_drop(self):
        """Setup drag and drop functionality"""
        self.file_listbox.drop_target_register(tkdnd.DND_FILES)
        self.file_listbox.dnd_bind('<<Drop>>', self.on_drop)
        self.file_listbox.dnd_bind('<<DragEnter>>', self.on_drag_enter)
        self.file_listbox.dnd_bind('<<DragLeave>>', self.on_drag_leave)
        
        self.drop_target_register(tkdnd.DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop)
        self.dnd_bind('<<DragEnter>>', self.on_drag_enter)
        self.dnd_bind('<<DragLeave>>', self.on_drag_leave)

    def on_drag_enter(self, event):
        """Visual feedback when drag enters the drop zone"""
        if hasattr(self, 'file_listbox'):
            self.file_listbox.configure(bg='lightblue')
        return tkdnd.COPY

    def on_drag_leave(self, event):
        """Reset visual feedback when drag leaves"""
        if hasattr(self, 'file_listbox'):
            self.file_listbox.configure(bg='white')

    def on_drop(self, event):
        """Handle dropped files/folders - direct loading without popups"""
        try:
            if hasattr(self, 'file_listbox'):
                self.file_listbox.configure(bg='white')
            
            dropped_items = self.tk.splitlist(event.data)
            
            cbz_files = []
            folders_processed = 0
            invalid_files = []
            
            for item in dropped_items:
                if os.path.isfile(item):
                    if item.lower().endswith('.cbz'):
                        cbz_files.append(item)
                    else:
                        invalid_files.append(os.path.basename(item))
                
                elif os.path.isdir(item):
                    folder_cbz_count = 0
                    for root, dirs, files in os.walk(item):
                        for file in files:
                            if file.lower().endswith('.cbz'):
                                cbz_files.append(os.path.join(root, file))
                                folder_cbz_count += 1
                    
                    folders_processed += 1
                    
                    folder_name = os.path.basename(item)
                    if folder_cbz_count > 0:
                        print(f"Found {folder_cbz_count} CBZ files in folder: {folder_name}")
                    else:
                        print(f"No CBZ files found in folder: {folder_name}")
            
            # Process CBZ files if any were found
            if cbz_files:
                # Sort files for consistent ordering
                cbz_files.sort()
                
                # Load files directly
                self._process_cbz_files(cbz_files)
                
                # Log results to console
                total_files = len(cbz_files)
                print(f"Successfully loaded {total_files} CBZ files!")
                if folders_processed > 0:
                    print(f"Processed {folders_processed} folders")
                if invalid_files:
                    print(f"Skipped {len(invalid_files)} non-CBZ files: {', '.join(invalid_files[:5])}")
                    if len(invalid_files) > 5:
                        print(f"   ... and {len(invalid_files) - 5} more")
            else:
                # Log when no CBZ files found
                if dropped_items:
                    print("No CBZ files found in dropped items")
                    if invalid_files:
                        print(f"Skipped files: {', '.join(invalid_files)}")
            
        except Exception as e:
            logging.error(f"Error processing dropped items: {e}")
            print(f"Error processing dropped files: {str(e)}")
        
        return tkdnd.COPY
      
    def disable_middle_click_paste(self, widget):
        """Disable middle-click paste functionality for text widgets"""
        # Disable middle-click paste for Linux/Unix systems
        widget.bind("<Button-2>", lambda e: "break")
        widget.bind("<ButtonRelease-2>", lambda e: "break")
        
        # Also disable shift+middle-click which can also trigger paste
        widget.bind("<Shift-Button-2>", lambda e: "break")
        widget.bind("<Shift-ButtonRelease-2>", lambda e: "break")
        
        # For Combobox widgets, we need different handling
        if isinstance(widget, ttk.Combobox):
            # Disable middle-click on combobox
            widget.bind("<Button-2>", lambda e: "break")
            widget.bind("<ButtonRelease-2>", lambda e: "break")
            widget.bind("<Shift-Button-2>", lambda e: "break")
            widget.bind("<Shift-ButtonRelease-2>", lambda e: "break")
        else:
            # For Text widgets, prevent selection copying to primary selection
            widget.bind("<Button-1>", lambda e: widget.after_idle(lambda: widget.selection_clear() if hasattr(widget, 'selection_clear') else None))

            
    def create_widgets(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # === Top Metadata Section ===
        top_frame = ttk.LabelFrame(main_frame, text="File Selection & Metadata Source", padding=10)
        top_frame.pack(fill='x', pady=(0, 10))

        file_frame = ttk.Frame(top_frame)
        file_frame.pack(fill='x', pady=(0, 10))

        ttk.Label(file_frame, text="CBZ Files (drag & drop supported):").pack(anchor='w')
        file_list_frame = ttk.Frame(file_frame)
        file_list_frame.pack(fill='x')

        self.file_listbox = tk.Listbox(file_list_frame, height=4)
        self.file_listbox.pack(side='left', fill='both', expand=True)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        file_scroll = ttk.Scrollbar(file_list_frame, orient='vertical', command=self.file_listbox.yview)
        file_scroll.pack(side='right', fill='y')
        self.file_listbox.configure(yscrollcommand=file_scroll.set)

        # File selection buttons with tooltips
        select_folder_btn = ttk.Button(file_list_frame, text="Select Folder", command=self.browse_cbz_folder)
        select_folder_btn.pack(side='right', padx=(5, 0))
        ToolTip(select_folder_btn, "Browse and select a folder containing CBZ files")
        
        select_cbz_btn = ttk.Button(file_list_frame, text="Select CBZ", command=self.browse_cbz_files)
        select_cbz_btn.pack(side='right', padx=(5, 0))
        ToolTip(select_cbz_btn, "Browse and select individual CBZ files")

        title_frame = ttk.Frame(top_frame)
        title_frame.pack(fill='x', pady=(0, 10))

        mode_frame = ttk.Frame(title_frame)
        mode_frame.pack(fill='x', pady=(0, 5))

        ttk.Label(mode_frame, text="Metadata Mode:").pack(anchor='w')
        mode_radio_frame = ttk.Frame(mode_frame)
        mode_radio_frame.pack(fill='x')

        batch_radio = ttk.Radiobutton(mode_radio_frame, text="Same metadata for all files", variable=self.metadata_mode, value="batch")
        batch_radio.pack(anchor='w')
        ToolTip(batch_radio, "Apply the same metadata to all selected files (batch mode)")
        
        individual_radio = ttk.Radiobutton(mode_radio_frame, text="Different metadata per file", variable=self.metadata_mode, value="individual")
        individual_radio.pack(anchor='w')
        ToolTip(individual_radio, "Use different metadata for each file based on filename matching")

        ttk.Label(title_frame, text="Manga Title:").pack(anchor='w')
        title_entry_frame = ttk.Frame(title_frame)
        title_entry_frame.pack(fill='x')

        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(title_entry_frame, textvariable=self.title_var, font=('TkDefaultFont', 10))
        self.title_entry.pack(side='left', fill='x', expand=True)
        self.disable_middle_click_paste(self.title_entry)
        ToolTip(self.title_entry, "Enter the manga/comic series title to search for metadata")

        # Metadata fetch buttons with tooltips        
        fetch_anilist_btn = ttk.Button(title_entry_frame, text="Fetch AniList", command=self.fetch_anilist_metadata_gui)
        fetch_anilist_btn.pack(side='right', padx=(5, 0))
        ToolTip(fetch_anilist_btn, "Fetch metadata from AniList database")

        refetch_btn = ttk.Button(title_entry_frame, text="Re-Fetch This File/Series", command=self.fetch_metadata_for_current_file)
        refetch_btn.pack(side='right', padx=(5, 0))
        ToolTip(refetch_btn, "Re-fetch metadata for the currently selected file/all files in a series.")
                        
        fetch_metadata_btn = ttk.Button(title_entry_frame, text="Fetch Metadata", command=self.fetch_metadata_smart)
        fetch_metadata_btn.pack(side='right', padx=(5, 0))
        ToolTip(fetch_metadata_btn, "Search for and fetch metadata from online sources")

        self.progress_frame = ttk.Frame(title_frame)
        self.progress_var = tk.StringVar(value="")
        self.progress_label = ttk.Label(self.progress_frame, textvariable=self.progress_var)
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode='determinate')

        series_db_frame = ttk.Frame(top_frame)
        series_db_frame.pack(fill='x', pady=(10, 0))

        ttk.Label(series_db_frame, text="Series Database:", font=('TkDefaultFont', 9, 'bold')).pack(side='left')
        
        # Series database buttons with tooltips
        save_aliases_btn = ttk.Button(series_db_frame, text="Save Series + Aliases", command=lambda: self.save_current_series(prompt_aliases=True))
        save_aliases_btn.pack(side='left', padx=(10, 5))
        ToolTip(save_aliases_btn, "Save current series metadata to database with alias editing")
        
        save_quick_btn = ttk.Button(series_db_frame, text="Save (Quick)", command=self.save_current_series)
        save_quick_btn.pack(side='left', padx=(0, 5))
        ToolTip(save_quick_btn, "Quickly save current series metadata to database")
        
        load_series_btn = ttk.Button(series_db_frame, text="Load Series", command=self.load_series_from_db)
        load_series_btn.pack(side='left', padx=(0, 5))
        ToolTip(load_series_btn, "Load previously saved series metadata from database")
        
        match_file_btn = ttk.Button(series_db_frame, text="Match File", command=self._match_current_file_with_db)
        match_file_btn.pack(side='left', padx=(0, 5))
        ToolTip(match_file_btn, "Try to match current file with saved series using filename analysis")
        
        match_all_btn = ttk.Button(series_db_frame, text="Match All", command=self._match_all_files_with_db)
        match_all_btn.pack(side='left', padx=(0, 5))
        ToolTip(match_all_btn, "Try to match all files with saved series using filename analysis")

        folder_name_chk = ttk.Checkbutton(series_db_frame, text="Use Folder Name as Series", variable=self.use_folder_name_var, command=self._toggle_folder_name_mode)
        folder_name_chk.pack(side='right', padx=10)
        ToolTip(folder_name_chk, "Extract title from the parent folder name instead of the file name (e.g., for 'Bleach/Chapter 1.cbz')")

        self.dropdown = ttk.Combobox(top_frame, textvariable=self.dropdown_var, state='readonly', font=('TkDefaultFont', 10))
        self.dropdown.pack(fill='x', pady=(10, 0))
        self.dropdown.bind("<<ComboboxSelected>>", self.update_metadata_from_dropdown)
        ToolTip(self.dropdown, "Select from available metadata options found during search")      
        
        nav_frame = ttk.Frame(main_frame)
        nav_frame.pack(fill='x', pady=(0, 10))

        # Navigation and utility buttons with tooltips
        prev_btn = ttk.Button(nav_frame, text="Previous", command=lambda: self.navigate_file(-1))
        prev_btn.pack(side='left', padx=(0, 5))
        ToolTip(prev_btn, "Navigate to the previous file in the list")
        
        next_btn = ttk.Button(nav_frame, text="Next", command=lambda: self.navigate_file(1))
        next_btn.pack(side='left', padx=(0, 15))
        ToolTip(next_btn, "Navigate to the next file in the list")
        
        auto_fill_btn = ttk.Button(nav_frame, text="Auto-Fill Volume", command=lambda: self.fill_metadata_field("volume"))
        auto_fill_btn.pack(side='left', padx=(0, 5))
        ToolTip(auto_fill_btn, "Automatically extract volume/issue numbers from filename")
        
        auto_fill_chapter_btn = ttk.Button(nav_frame, text="Auto-Fill Chapter", command=lambda: self.fill_metadata_field("chapter"))
        auto_fill_chapter_btn.pack(side='left', padx=(0, 5))
        ToolTip(auto_fill_chapter_btn, "Automatically extract chapter/issue numbers from filename")
        
        count_pages_btn = ttk.Button(nav_frame, text="Count Pages", command=lambda: self.fill_metadata_field("pages"))
        count_pages_btn.pack(side='left', padx=(0, 5))
        ToolTip(count_pages_btn, "Count and fill in the number of pages in the CBZ file")
        
        extract_title_btn = ttk.Button(nav_frame, text="Extract Title", command=self.fill_title_from_filename)
        extract_title_btn.pack(side='left', padx=(0, 5))
        ToolTip(extract_title_btn, "Extract Chapter/Volume Name from filename (text after Cxxx/Vxxx)")
        
        do_all_alt_btn = ttk.Button(nav_frame, text="Do All - Fetch Anilist", command=self.do_all_operations_alt)
        do_all_alt_btn.pack(side='right', padx=(5, 0))
        ToolTip(do_all_alt_btn, "Execute all operations: Auto-fill Volume/Chapter, Count Pages, Extract Title and Save")
        
        do_all_btn = ttk.Button(nav_frame, text="Do All", command=self.do_all_operations)
        do_all_btn.pack(side='right', padx=(5, 0))
        ToolTip(do_all_btn, "Execute all operations: Fetch AniList, Auto-fill Volume/Chapter, Count Pages, Extract Title and Save")
                
        bulk_edit_check = ttk.Checkbutton(nav_frame, text="Bulk Edit All Files", variable=self.bulk_edit_enabled)
        bulk_edit_check.pack(side='right')
        ToolTip(bulk_edit_check, "When enabled, changes apply to all files instead of just the current file")

        self.button_frame = ttk.Frame(main_frame)  # Store reference for drag/drop
        self.button_frame.pack(fill='x')

        # Main action buttons with tooltips
        
        insert_btn = ttk.Button(self.button_frame, text="Insert Metadata into All CBZs", command=self.insert_metadata, style='Accent.TButton')
        insert_btn.pack(side='right', padx=(0, 15))
        ToolTip(insert_btn, "Apply the current metadata to all selected CBZ files")

        refresh_meta_btn = ttk.Button(self.button_frame, text="Refresh Metadata (Web ID)", command=self.refresh_metadata_from_web_url)
        refresh_meta_btn.pack(side='right', padx=(0, 10))
        ToolTip(refresh_meta_btn, "Fetches Metadata directly from Local Dump using the Mangabaka URL in the Web field from existing ComicInfo for all files.")
        
        copy_all_btn = ttk.Button(self.button_frame, text="Copy All Fields", command=self.copy_all_fields)
        copy_all_btn.pack(side='left', padx=(0, 5))
        ToolTip(copy_all_btn, "Copy all original metadata values to the updated fields")
        
        clear_all_btn = ttk.Button(self.button_frame, text="Clear All Fields", command=self.clear_all_fields)
        clear_all_btn.pack(side='left', padx=(0, 5))
        ToolTip(clear_all_btn, "Clear all metadata fields (both original and updated)")

        metadata_frame = ttk.LabelFrame(main_frame, text="Metadata Editor", padding=5)
        metadata_frame.pack(fill='both', expand=True, pady=(0, 10))

        canvas = tk.Canvas(metadata_frame)
        scrollbar = ttk.Scrollbar(metadata_frame, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)

        self.canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(self.canvas_window, width=e.width))
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        scroll_frame.grid_columnconfigure(1, weight=1)
        scroll_frame.grid_columnconfigure(3, weight=1)

        # Column headers
        ttk.Label(scroll_frame, text="Field", font=('TkDefaultFont', 9, 'bold')).grid(row=1, column=0, sticky='w', padx=(5, 0))
        ttk.Label(scroll_frame, text="Original Metadata", font=('TkDefaultFont', 9, 'bold')).grid(row=1, column=1, sticky='ew', padx=5)
        ttk.Label(scroll_frame, text="™", font=('TkDefaultFont', 9, 'bold')).grid(row=1, column=2, sticky='w', padx=(0, 5))
        ttk.Label(scroll_frame, text="Updated Metadata", font=('TkDefaultFont', 9, 'bold')).grid(row=1, column=3, sticky='ew', padx=5)

        self.copy_buttons = {}
        self.form_rows = {}

        # Create form fields with tooltips
        for i, field in enumerate(self.fields):
            row = i + 2

            label = ttk.Label(scroll_frame, text=field, font=('TkDefaultFont', 8))
            label.grid(row=row, column=0, sticky='nw', padx=(5, 10), pady=2)
            ToolTip(label, self.field_tooltips.get(field, f"Metadata field: {field}"))

            before = tk.Text(scroll_frame, height=1, width=50, wrap='word', font=('TkDefaultFont', 8), state='disabled', bg='#f0f0f0')
            before.grid(row=row, column=1, sticky='nsew', padx=(5, 2), pady=2)
            self.disable_middle_click_paste(before)
            ToolTip(before, f"Original {field} metadata from the CBZ file (read-only)")

            copy_btn = ttk.Button(scroll_frame, text="™", width=3, command=lambda f=field: self.copy_field(f))
            copy_btn.grid(row=row, column=2, padx=(2, 2), pady=2)
            ToolTip(copy_btn, f"Copy original {field} value to the updated field")

            if field == "AgeRating":
                after = ttk.Combobox(scroll_frame, values=self.age_rating_options, font=('TkDefaultFont', 8), width=50)
                after.bind('<<ComboboxSelected>>', lambda e, f=field: self.on_dropdown_change(f))
                after.bind('<KeyRelease>', lambda e, f=field: self.on_text_change(f))
                self.disable_middle_click_paste(after)  # Add this line
                ToolTip(after, "Select age rating from predefined options or enter custom value")
            elif field == "Format":
                after = ttk.Combobox(scroll_frame, values=self.format_options, font=('TkDefaultFont', 8), width=50)
                after.bind('<<ComboboxSelected>>', lambda e, f=field: self.on_dropdown_change(f))
                after.bind('<KeyRelease>', lambda e, f=field: self.on_text_change(f))
                self.disable_middle_click_paste(after)  # Add this line
                ToolTip(after, "Select publication format from predefined options or enter custom value")
            else:
                after = tk.Text(scroll_frame, height=1, width=50, wrap='word', font=('TkDefaultFont', 8))
                after.bind('<KeyRelease>', lambda e, f=field: self.on_text_change(f))
                self.disable_middle_click_paste(after)  # Add this line
                ToolTip(after, self.field_tooltips.get(field, f"Enter {field} metadata"))
            
            after.grid(row=row, column=3, sticky='nsew', padx=(2, 2), pady=2)

            clear_btn = ttk.Button(scroll_frame, text="¢", width=3, command=lambda f=field: self.clear_field(f))
            clear_btn.grid(row=row, column=4, padx=(2, 5), pady=2)
            ToolTip(clear_btn, f"Clear the {field} field")

            self.before_entries[field] = before
            self.after_entries[field] = after
            self.copy_buttons[field] = copy_btn
            self.form_rows[field] = (label, before, copy_btn, after, clear_btn)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        def _bind_to_mousewheel(event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        def _unbind_from_mousewheel(event):
            canvas.unbind_all("<MouseWheel>")
        
        # Only enable mousewheel scrolling when mouse enters the metadata canvas area
        canvas.bind('<Enter>', _bind_to_mousewheel)
        canvas.bind('<Leave>', _unbind_from_mousewheel)
        scrollbar.bind('<Enter>', _bind_to_mousewheel) 
        scrollbar.bind('<Leave>', _unbind_from_mousewheel)

        # Set up drag and drop AFTER all widgets are created
        self.setup_drag_drop()
        
        # Add visual hint to the file listbox when no files are loaded
        if self.file_listbox.size() == 0:
            self.file_listbox.insert(0, "Drag and drop CBZ files or folders here...")
            self.file_listbox.configure(fg='gray')

    def on_dropdown_change(self, field):
        """Handle dropdown field changes"""
        self.on_text_change(field)

    def on_text_change(self, field):
        """Update metadata for one or all files based on bulk edit mode"""
        if not self.cbz_paths:
            return

        if field in ["AgeRating", "Format"]:
            value = self.after_entries[field].get()
        else:
            value = self.after_entries[field].get("1.0", tk.END).strip()

        if self.bulk_edit_enabled.get():
            for file in self.cbz_paths:
                if file in self.file_metadata:
                    self.file_metadata[file][field] = value
        else:
            if self.current_index < len(self.cbz_paths):
                current_file = self.cbz_paths[self.current_index]
                if current_file in self.file_metadata:
                    self.file_metadata[current_file][field] = value
                
    def populate_dropdown_for_current_file(self):
        """Populate metadata dropdown based on current file (individual mode)"""
        if not self.cbz_paths or self.current_index >= len(self.cbz_paths):
            return

        current_file = self.cbz_paths[self.current_index]

        if self.metadata_mode.get() == "individual" and current_file in self.individual_metadata_cache:
            cache_data = self.individual_metadata_cache[current_file]
            self.metadata_options = cache_data.get('options', [])

            dropdown_values = []
            for meta in self.metadata_options:
                title_text = meta.get('Series') or meta.get('Title') or 'Unknown'
                type_text = meta.get("type", "")
                year_text = meta.get("Year", "")
                content_rating_text = meta.get("content_rating", "")
            
                parts = [title_text]
                if type_text:
                    parts.append(f"({type_text.title()})")
                if year_text:
                    parts.append(f"({year_text})")
                if content_rating_text:
                    parts.append(f"({content_rating_text.title()})")
            
                dropdown_values.append(" ".join(parts))

            self.dropdown['values'] = dropdown_values

            # Restore user's last selection if available
            selected_idx = self.dropdown_selection_per_file.get(current_file, 0)
            if selected_idx < len(dropdown_values):
                self.dropdown.set(dropdown_values[selected_idx])
                # REMOVED: self.update_metadata_from_dropdown() <-- This was erasing your edits!
            elif dropdown_values:
                self.dropdown.set(dropdown_values[0])
                # REMOVED: self.update_metadata_from_dropdown() <-- This was erasing your edits!
            else:
                self.dropdown.set("No matches found")
                
    def browse_cbz_files(self):
        file_paths = filedialog.askopenfilenames(
            title="Select CBZ Files",
            filetypes=[("CBZ files", "*.cbz")]
        )
        self._process_cbz_files(file_paths)

    def browse_cbz_folder(self):
        folder = filedialog.askdirectory(title="Select Folder Containing CBZs")
        if not folder:
            return

        cbz_files = []
        for root, _, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(".cbz"):
                    cbz_files.append(os.path.join(root, f))

        self._process_cbz_files(cbz_files)

        
    def _process_cbz_files(self, paths):
        if not paths:
            return

        # Clear placeholder text if it exists
        if (self.file_listbox.size() == 1 and 
            "Drag and drop CBZ files" in self.file_listbox.get(0)):
            self.file_listbox.delete(0)
            self.file_listbox.configure(fg='black')

        # Use natural sort so v2 comes before v10
        self.cbz_paths = sorted(paths, key=natural_sort_key)
        
        # 1. OPTIMIZATION: Clear and update the Listbox instantly using a Tuple
        self.file_listbox.delete(0, tk.END)
        display_names = []
        for path in self.cbz_paths:
            folder_name = os.path.basename(os.path.dirname(path))
            file_name = os.path.basename(path)
            if folder_name:
                display_names.append(f"{folder_name}/{file_name}")
            else:
                display_names.append(file_name)
        display_names = tuple(display_names)
        
        # In Tkinter, updating the 'listvariable' or doing a bulk insert is near-instant
        self.file_listbox.insert(tk.END, *display_names)
        
        self.file_metadata.clear()
        self.original_metadata.clear()

        # Update title var instantly using the full path now
        first_title = self._extract_title_from_filename(self.cbz_paths[0])
        if first_title:
            first_title = first_title.translate(APOSTROPHE_MAP)
            self.title_var.set(first_title)

        # 2. OPTIMIZATION: Dictionary comprehension is faster than a standard loop
        empty_meta = {field: "" for field in self.fields}
        self.file_metadata = {path: empty_meta.copy() for path in self.cbz_paths}
        self.original_metadata = {path: empty_meta.copy() for path in self.cbz_paths}

        if self.cbz_paths:
            self.file_listbox.select_set(0)
            self.current_index = 0
            # Show empty metadata instantly
            self.load_metadata(0)
            
            Thread(target=self._background_xml_loader, daemon=True).start()

    def _background_xml_loader(self):
        """Reads ComicInfo.xml from all loaded zips in the background without freezing GUI"""
        for path in self.cbz_paths:
            try:
                with zipfile.ZipFile(path, 'r') as cbz:
                    # Fast check using set intersection
                    if "ComicInfo.xml" in set(cbz.namelist()):
                        with cbz.open("ComicInfo.xml") as xml_file:
                            tree = ET.parse(xml_file)
                            root = tree.getroot()
                            
                            found_data = False
                            meta_update = {}
                            for field in self.fields:
                                element = root.find(field)
                                if element is not None and element.text:
                                    meta_update[field] = element.text.strip()
                                    found_data = True
                            
                            if found_data:
                                # ONLY update original_metadata. Leave file_metadata blank for the UI.
                                self.original_metadata[path].update(meta_update)
                                
                                # If this is the currently selected file, tell Tkinter to refresh
                                if path == self.cbz_paths[self.current_index]:
                                    self.after(0, lambda: self.load_metadata(self.current_index))
            except Exception as e:
                logging.warning(f"Failed to read ComicInfo.xml from {path}: {e}")

    def save_current_series(self, prompt_aliases=False):
        """Save current series metadata to database, optionally prompting for aliases"""
        if not self.cbz_paths:
            messagebox.showerror("Error", "No CBZ files loaded")
            return
            
        series_to_save = {}
        
        if self.metadata_mode.get() == "batch":
            # BATCH MODE: Just grab the currently selected series
            current_file = self.cbz_paths[self.current_index] if self.current_index < len(self.cbz_paths) else self.cbz_paths[0]
            current_metadata = self.file_metadata.get(current_file, {})
            series_name = current_metadata.get('Series', '').strip()
            
            if not series_name:
                series_name = tk.simpledialog.askstring(
                    "Series Name", "Enter series name:", initialvalue=self.title_entry.get().strip()
                )
                if not series_name or not series_name.strip():
                    messagebox.showwarning("Warning", "Series name is required")
                    return
                series_name = series_name.strip()
                
            series_to_save[series_name] = current_metadata
            
        else:
            # INDIVIDUAL MODE: Extract ALL unique series loaded in the app
            for path in self.cbz_paths:
                meta = self.file_metadata.get(path, {})
                series_name = meta.get('Series', '').strip()
                
                # If the user hasn't fetched metadata for a file yet, 'Series' might be empty.
                # Fallback to the extracted title from the file/folder name safely.
                if not series_name:
                    series_name = self._extract_title_from_filename(path)
                    
                if series_name:
                    # We only keep one metadata snapshot per unique series name
                    if series_name not in series_to_save:
                        series_to_save[series_name] = meta

        if not series_to_save:
            messagebox.showwarning("Warning", "No valid series names found to save.")
            return

        saved_count = 0
        failed_count = 0
        
        # Save every unique series found
        for series_name, current_metadata in series_to_save.items():
            # Create series metadata template and strip file-specific data
            series_metadata = current_metadata.copy()
            for field in ['Number', 'Volume', 'PageCount', 'Title']:
                if field in series_metadata:
                    series_metadata[field] = ""
            
            try:
                if series_db.save_series_metadata(series_name, series_metadata):
                    saved_count += 1
                    # If triggered by the "Save with Aliases" button, show the dialog
                    if prompt_aliases:
                        current_aliases = series_db.load_series_aliases(series_name)
                        dialog = AliasEditorDialog(self, series_name, current_aliases)
                        self.wait_window(dialog)
                        # If user hits Cancel, dialog.result is None, so it safely skips
                        if dialog.result is not None:
                            series_db.save_series_aliases(series_name, dialog.result)
                else:
                    failed_count += 1
            except Exception as e:
                logging.error(f"Error saving series '{series_name}': {e}")
                failed_count += 1
                
        # Final User Feedback
        if saved_count > 0:
            if len(series_to_save) == 1:
                print(f"Success: Series '{list(series_to_save.keys())[0]}' saved to database")
            else:
                messagebox.showinfo("Bulk Save Complete", f"Successfully saved {saved_count} unique series to the database.")
        
        if failed_count > 0:
            messagebox.showwarning("Warning", f"Failed to save {failed_count} series. Check logs.")
            
    def load_series_from_db(self):
        """Load series metadata from database"""
        dialog = SeriesManagerDialog(self)
        self.wait_window(dialog)
        
        if dialog.match_mode:
            # Handle match operations
            if dialog.load_to_all:
                self._match_all_files_with_db()
            else:
                self._match_current_file_with_db()
        elif dialog.selected_series:
            # Handle regular load operations
            series_metadata = series_db.load_series_metadata(dialog.selected_series)
            if series_metadata:
                if self.cbz_paths:
                    if dialog.load_to_all:
                        # Apply series metadata to ALL loaded files
                        files_to_update = self.cbz_paths
                        message_suffix = f"to all {len(self.cbz_paths)} files"
                    else:
                        # Apply series metadata to SELECTED file only
                        if self.current_index < len(self.cbz_paths):
                            files_to_update = [self.cbz_paths[self.current_index]]
                            current_filename = os.path.basename(self.cbz_paths[self.current_index])
                            message_suffix = f"to '{current_filename}'"
                        else:
                            messagebox.showwarning("Warning", "No file selected. Please select a file first.")
                            return
                    
                    # Apply metadata to selected files
                    for cbz_path in files_to_update:
                        # Keep existing file-specific data
                        existing_metadata = self.file_metadata.get(cbz_path, {})
                        file_specific_data = {
                            'Volume': existing_metadata.get('Volume', ''),
                            'Number': existing_metadata.get('Number', ''),
                            'PageCount': existing_metadata.get('PageCount', '')
                        }
                        
                        # Update with series metadata
                        self.file_metadata[cbz_path] = series_metadata.copy()
                        
                        # Restore file-specific data
                        self.file_metadata[cbz_path].update(file_specific_data)
                        
                        # Auto-extract volume if not already set
                        if not file_specific_data['Volume']:
                            volume = extract_volume_from_filename(os.path.basename(cbz_path))
                            if volume:
                                self.file_metadata[cbz_path]['Volume'] = volume
                    
                    # Refresh display
                    self.load_metadata(self.current_index)
                    messagebox.showinfo("Success", f"Loaded series metadata for '{dialog.selected_series}' {message_suffix}")
                else:
                    messagebox.showwarning("Warning", "No CBZ files loaded. Load files first, then apply series metadata.")
            else:
                messagebox.showerror("Error", f"Failed to load series metadata for '{dialog.selected_series}'")
                
    def _build_series_variants_cache(self, all_series):
        """Build a cached, pre-normalized dictionary of all series variants to eliminate DB hits during loops"""
        series_with_variants = []
        for series_item in all_series:
            if len(series_item) == 3:
                series_name, updated_at, aliases = series_item
            else:
                series_name = series_item[0] if isinstance(series_item, tuple) else series_item
                aliases = []
            
            # Load metadata ONCE per series
            series_metadata = series_db.load_series_metadata(series_name)
            if not isinstance(series_metadata, dict):
                series_metadata = {'Series': series_name}
            
            # Collect all title variants
            all_titles = [series_name]
            
            # Add aliases safely
            if aliases:
                if isinstance(aliases, list):
                    all_titles.extend(aliases)
                elif isinstance(aliases, str):
                    all_titles.extend([a.strip() for a in aliases.split(',') if a.strip()])
            
            # Add LocalizedSeries and alternative titles
            if series_metadata:
                if series_metadata.get('LocalizedSeries'):
                    all_titles.extend([t.strip() for t in series_metadata['LocalizedSeries'].split(',') if t.strip()])
                for field in ['Native', 'Romaji', 'Secondary']:
                    alt_title = series_metadata.get(field, '').strip()
                    if alt_title:
                        all_titles.append(alt_title)
            
            # Pre-clean and pre-normalize to save massive CPU time during the loop
            processed_variants = []
            unique_titles = list(dict.fromkeys(all_titles)) # Fast deduplication preserving order
            
            for t in unique_titles:
                if not t: continue
                cleaned = self._clean_title_for_matching(t)
                norm = self._normalize_for_comparison(cleaned)
                processed_variants.append({'raw': t, 'normalized': norm})
                
            series_with_variants.append((series_name, processed_variants))
            
        return series_with_variants

    def _find_best_match(self, extracted_title, series_with_variants):
        """Find the best matching series title using pre-cached variants (Blazing Fast)"""
        if not extracted_title or not series_with_variants:
            return None
        
        cleaned_extracted = self._clean_title_for_matching(extracted_title)
        normalized_extracted = self._normalize_for_comparison(cleaned_extracted)
        
        # 1. Try Exact match against pre-normalized variants
        for series_name, variants in series_with_variants:
            for variant in variants:
                if variant['normalized'] == normalized_extracted:
                    return series_name
        
        # 2. Try Substring matching (both ways)
        best_matches = []
        for series_name, variants in series_with_variants:
            for variant in variants:
                norm_variant = variant['normalized']
                if normalized_extracted in norm_variant:
                    score = len(norm_variant) - len(normalized_extracted)
                    best_matches.append((series_name, score, 'contains'))
                elif norm_variant in normalized_extracted:
                    score = len(normalized_extracted) - len(norm_variant)
                    best_matches.append((series_name, score, 'contained'))
        
        if best_matches:
            best_matches.sort(key=lambda x: (x[1], x[2]))
            return best_matches[0][0]
        
        # 3. Try Fuzzy matching
        return self._fuzzy_match_with_variants(normalized_extracted, series_with_variants) 
    
    def _extract_volume_from_filename(self, filename):
        """Extract volume number from filename (Wrapper for global function)"""
        # Call the global function, but ensure it returns "" instead of None
        return extract_volume_from_filename(filename) or ""
           
    def _clean_title_for_matching(self, title):
        """Clean title preserving ordinal numbers like '7th Time Loop'"""
        cleaned = BRACKET_CONTENT_PATTERN.sub('', title)
        cleaned = PAREN_CONTENT_PATTERN.sub('', cleaned)
        
        cleaned = VOLUME_PATTERN.sub('', cleaned)
        cleaned = CHAPTER_PATTERN.sub('', cleaned)      
      
        return WHITESPACE_PATTERN.sub(' ', cleaned).strip()
    
    def _normalize_for_comparison(self, title):
        """Normalize title for comparison by removing special characters and converting to lowercase"""
        normalized = SPECIAL_CHARS_REMOVAL.sub('', title.lower())
        return ' '.join(normalized.split())
    
    def _fuzzy_match_with_variants(self, normalized_extracted, series_with_variants):
        """Perform fuzzy matching against pre-normalized variants"""
        try:
            from difflib import SequenceMatcher
            best_match = None
            best_ratio = 0.0
            threshold = 0.8  # Minimum similarity threshold
            
            for series_name, variants in series_with_variants:
                for variant in variants:
                    ratio = SequenceMatcher(None, normalized_extracted, variant['normalized']).ratio()
                    if ratio > best_ratio and ratio >= threshold:
                        best_ratio = ratio
                        best_match = series_name
            return best_match
        except Exception as e:
            logging.error(f"Error in fuzzy matching: {e}")
            return None
        
    def _match_current_file_with_db(self):
        """Match current file with series DB based on filename"""
        if not self.cbz_paths or self.current_index >= len(self.cbz_paths):
            messagebox.showwarning("Warning", "No file selected.")
            return
        
        current_file = self.cbz_paths[self.current_index]
        filename = os.path.basename(current_file)
        
        # FIX: Pass the full path, not just the filename
        extracted_title = self._extract_title_from_filename(current_file)
        
        if not extracted_title:
            messagebox.showwarning("Warning", f"Could not extract title from filename: {filename}")
            return
        
        # Build the cache once, then match
        all_series = series_db.get_all_series_with_aliases()
        series_with_variants = self._build_series_variants_cache(all_series)
        best_match = self._find_best_match(extracted_title, series_with_variants)
        
        if best_match:
            series_metadata = series_db.load_series_metadata(best_match)
            if series_metadata:
                existing_metadata = self.file_metadata.get(current_file, {})
                file_specific_data = {
                    'Volume': existing_metadata.get('Volume', ''),
                    'Number': existing_metadata.get('Number', ''),
                    'PageCount': existing_metadata.get('PageCount', '')
                }
                
                self.file_metadata[current_file] = series_metadata.copy()
                self.file_metadata[current_file].update(file_specific_data)
                
                if not file_specific_data['Volume']:
                    volume = self._extract_volume_from_filename(filename)
                    if volume:
                        self.file_metadata[current_file]['Volume'] = volume
                
                self.load_metadata(self.current_index)
                messagebox.showinfo("Match Found", f"Matched '{filename}' with series '{best_match}'")
            else:
                messagebox.showerror("Error", f"Failed to load metadata for matched series '{best_match}'")
        else:
            messagebox.showinfo("No Match", f"No matching series found for '{filename}'\nExtracted title: '{extracted_title}'")

    def _match_all_files_with_db(self):
        """Match all files with series DB based on filenames (Now highly optimized)"""
        if not self.cbz_paths:
            messagebox.showwarning("Warning", "No CBZ files loaded.")
            return
        
        all_series = series_db.get_all_series_with_aliases()
        if not all_series:
            messagebox.showwarning("Warning", "No series found in database.")
            return
        
        matched_files = 0
        match_results = []
        
        # 1. BUILD CACHE ONCE for all files (Massive performance boost)
        series_with_variants = self._build_series_variants_cache(all_series)
        loaded_series_metadata_cache = {}  
        
        for cbz_path in self.cbz_paths:
            filename = os.path.basename(cbz_path)
            
            # FIX: Pass the full path, not just the filename
            extracted_title = self._extract_title_from_filename(cbz_path)
            
            if not extracted_title:
                match_results.append(f"{filename} - Could not extract title")
                continue
            
            # 2. MATCH using pre-computed memory cache
            best_match = self._find_best_match(extracted_title, series_with_variants)
            
            if best_match:
                if best_match not in loaded_series_metadata_cache:
                    loaded_series_metadata_cache[best_match] = series_db.load_series_metadata(best_match)
                
                series_metadata = loaded_series_metadata_cache[best_match]
                
                if series_metadata:
                    existing_metadata = self.file_metadata.get(cbz_path, {})
                    file_specific_data = {
                        'Volume': existing_metadata.get('Volume', ''),
                        'Number': existing_metadata.get('Number', ''),
                        'PageCount': existing_metadata.get('PageCount', '')
                    }
                    
                    self.file_metadata[cbz_path] = series_metadata.copy()
                    self.file_metadata[cbz_path].update(file_specific_data)
                    
                    if not file_specific_data['Volume']:
                        volume = self._extract_volume_from_filename(filename)
                        if volume:
                            self.file_metadata[cbz_path]['Volume'] = volume
                    
                    matched_files += 1
                    match_results.append(f"{filename} ➔ {best_match}")
                else:
                    match_results.append(f"{filename} - Failed to load '{best_match}' metadata")
            else:
                match_results.append(f"{filename} - No match found")
        
        self.load_metadata(self.current_index)
        
        result_text = f"Matching Results: {matched_files}/{len(self.cbz_paths)} files matched\n\n"
        result_text += "\n".join(match_results)
        self._show_match_results(result_text)
    
    def _show_match_results(self, results_text):
        """Show match results in a scrollable dialog"""
        dialog = tk.Toplevel(self)
        dialog.title("Match Results")
        dialog.transient(self)
        dialog.grab_set()
        
        # Main frame
        main_frame = ttk.Frame(dialog, padding=10)
        main_frame.pack(fill='both', expand=True)
        
        # Text widget with scrollbar
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        text_widget = tk.Text(text_frame, wrap='word', font=('Consolas', 10))
        scrollbar = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Insert results
        text_widget.insert('1.0', results_text)
        text_widget.configure(state='disabled')  # Make read-only
        
        # Close button
        ttk.Button(main_frame, text="Close", command=dialog.destroy).pack(pady=(0, 0))
        
        # Set size and center AFTER all content is created
        dialog.geometry("800x600")
        dialog.update_idletasks()
        center_window(dialog, 800, 600)
        
    def open_series_manager(self):
        """Open the series database manager"""
        dialog = SeriesManagerDialog(self)
        self.wait_window(dialog)
        
        if hasattr(dialog, 'selected_series') and dialog.selected_series:
            # Load selected series to files
            series_metadata = series_db.load_series_metadata(dialog.selected_series)
            if series_metadata:
                if dialog.load_to_all:
                    # Apply to all files
                    for cbz_path in self.cbz_paths:
                        existing_metadata = self.file_metadata.get(cbz_path, {})
                        file_specific_data = {
                            'Volume': existing_metadata.get('Volume', ''),
                            'Number': existing_metadata.get('Number', ''),
                            'PageCount': existing_metadata.get('PageCount', '')
                        }
                        
                        self.file_metadata[cbz_path] = series_metadata.copy()
                        self.file_metadata[cbz_path].update(file_specific_data)
                    
                    messagebox.showinfo("Success", f"Loaded '{dialog.selected_series}' metadata to all files")
                else:
                    # Apply to current file only
                    if self.cbz_paths and self.current_index < len(self.cbz_paths):
                        current_file = self.cbz_paths[self.current_index]
                        existing_metadata = self.file_metadata.get(current_file, {})
                        file_specific_data = {
                            'Volume': existing_metadata.get('Volume', ''),
                            'Number': existing_metadata.get('Number', ''),
                            'PageCount': existing_metadata.get('PageCount', '')
                        }
                        
                        self.file_metadata[current_file] = series_metadata.copy()
                        self.file_metadata[current_file].update(file_specific_data)
                        
                        messagebox.showinfo("Success", f"Loaded '{dialog.selected_series}' metadata to current file")
                    else:
                        messagebox.showwarning("Warning", "No file selected")
                
                # Refresh display
                self.load_metadata(self.current_index)
            else:
                messagebox.showerror("Error", f"Failed to load metadata for '{dialog.selected_series}'")
        
        elif hasattr(dialog, 'match_mode') and dialog.match_mode:
            # Handle matching modes
            if dialog.load_to_all:
                self._match_all_files_with_db()
            else:
                self._match_current_file_with_db()
        
    def load_metadata(self, idx):
        """Load metadata for the specified file index"""
        if not self.cbz_paths or idx >= len(self.cbz_paths):
            return
    
        self.current_index = idx
        current_file = self.cbz_paths[idx]
    
        before_meta = self.original_metadata.get(current_file, {field: "" for field in self.fields})
        after_meta = self.file_metadata.get(current_file, {field: "" for field in self.fields})
    
        for field in self.fields:
            before_val = before_meta.get(field, "")
            after_val = after_meta.get(field, "")
    
            # Special formatting for Web field
            if field == "Web":
                before_val = before_val.replace(",", "\n")
                after_val = after_val.replace(",", "\n")
    
            # Update before field (read-only)
            self.before_entries[field].config(state='normal')
            self.before_entries[field].delete("1.0", tk.END)
            self.before_entries[field].insert("1.0", before_val)
            self.before_entries[field].config(state='disabled')
    
            # Update after field (editable) - handle different widget types
            if field in ["AgeRating", "Format"]:
                self.after_entries[field].set(after_val)
            else:
                self.after_entries[field].delete("1.0", tk.END)
                self.after_entries[field].insert("1.0", after_val)
    
                max_lines = max(self._estimate_line_count(before_val), self._estimate_line_count(after_val))
    
                # Force minimum height for Web and Summary fields
                if field == "Web":
                    max_lines = max(max_lines, 12)
                elif field == "Summary":
                    max_lines = max(max_lines, 10)
    
                self.before_entries[field].configure(height=max_lines)
                self.after_entries[field].configure(height=max_lines)
    
    def _estimate_line_count(self, text):
        """Estimate required height in lines for a given text block"""
        import textwrap
        avg_chars_per_line = 100
        lines = textwrap.wrap(text, avg_chars_per_line)
        return min(len(lines) + 1, 12)

    def copy_field(self, field):
        if not self.cbz_paths or self.current_index >= len(self.cbz_paths):
            return
            
        files_to_update = self.cbz_paths if self.bulk_edit_enabled.get() else [self.cbz_paths[self.current_index]]
        for file in files_to_update:
            if file in self.file_metadata:
                self.file_metadata[file][field] = self.original_metadata.get(file, {}).get(field, "")
                
        current_file = self.cbz_paths[self.current_index]
        value = self.original_metadata.get(current_file, {}).get(field, "")
        
        target_widget = self.after_entries.get(field)
        if isinstance(target_widget, tk.Text):
            target_widget.delete("1.0", tk.END)
            target_widget.insert("1.0", value)
            target_widget.configure(height=min(value.count('\n') + 1, 8))
        elif isinstance(target_widget, ttk.Combobox):
            target_widget.set(value)
    
    def clear_field(self, field):
        if not self.cbz_paths or self.current_index >= len(self.cbz_paths):
            return
            
        files_to_update = self.cbz_paths if self.bulk_edit_enabled.get() else [self.cbz_paths[self.current_index]]
        for file in files_to_update:
            if file in self.file_metadata:
                self.file_metadata[file][field] = ""
                
        widget = self.after_entries.get(field)
        if isinstance(widget, tk.Text):
            widget.delete("1.0", tk.END)
            widget.configure(height=1)
        elif isinstance(widget, ttk.Combobox):
            widget.set("")

    def copy_all_fields(self):
        for field in self.fields:
            self.copy_field(field)

    def clear_all_fields(self):
        for field in self.fields:
            self.clear_field(field)

    def _sort_metadata_options(self, options):
        """Sort metadata options to prioritize Manga over Novels while preserving match accuracy"""
        MANGA_FORMATS = {"MANGA", "ONE_SHOT", "OEL", "MANHWA", "MANHUA", "DOUJINSHI"}
        NOVEL_FORMATS = {"NOVEL", "LIGHT_NOVEL"}
        
        def _format_priority(meta):
            fmt = str(meta.get("type", "")).upper()
            if fmt in MANGA_FORMATS: return 0
            elif fmt in NOVEL_FORMATS: return 2
            return 1
            
        # Python's sort is stable, so it preserves the original "best title match" scoring 
        # while grouping them by these format priorities.
        options.sort(key=_format_priority)
        return options
        
    @staticmethod
    def extract_metadata(entry, filename=None):
        """Extract metadata from API response entry - WITH UPDATED PUBLISHER LOGIC and filename parsing"""

        def safe_list(val):
            if isinstance(val, list):
                return val
            elif isinstance(val, str):
                return [val]
            return []

        def safe_get(obj, key, default=""):
            return str(obj.get(key, default)) if obj.get(key) is not None else default

        # Handle links from new paginated Weblinks API or local dumps
        extracted_links = []
        
        # 1. Construct and append the Mangabaka direct link
        # Extract the main entry ID to build the MB link
        entry_id = entry.get("id")
        if entry_id:
            mb_url = f"https://mangabaka.org/{str(entry_id).strip()}"
            extracted_links.append(mb_url)
            
        # Extract from either the local dump key
        links_v2 = entry.get("links_v2")
        
        items_to_process = []
        
        # 1. Handle local dump format (list of objects directly under 'links_v2')
        if isinstance(links_v2, list):
            items_to_process = links_v2
            
        # Parse the collected items
        for item in items_to_process:
            if not isinstance(item, dict):
                continue
            
            l_type = item.get("type", "")
            l_lang = item.get("language", "unknown")
            l_url = item.get("url", "")
            
            if l_type in ALLOWED_WEBLINK_TYPES and l_lang in ALLOWED_WEBLINK_LANGUAGES:
                if l_url:
                    extracted_links.append(l_url)

        # 2. Extract legacy source-derived links (AniList, MangaUpdates, etc.)
        source = entry.get("source", {})
        if isinstance(source, dict):
            # Use constants for URL patterns
            source_url_patterns = {
                "manga_updates": (SOURCE_URL_PATTERNS["manga_updates"], "id"),
                "my_anime_list": (SOURCE_URL_PATTERNS["my_anime_list"], "id"),
                "anilist": (SOURCE_URL_PATTERNS["anilist"], "id"),
                "anime_planet": (SOURCE_URL_PATTERNS["anime_planet"], "id"),
                "kitsu": (SOURCE_URL_PATTERNS["kitsu"], "id"),
                "shikimori": (SOURCE_URL_PATTERNS["shikimori"], "id"),
                "anime_news_network": (SOURCE_URL_PATTERNS["anime_news_network"], "id")
            }
            
            for source_name, (base_url, id_key) in source_url_patterns.items():
                source_data = source.get(source_name, {})
                if isinstance(source_data, dict):
                    source_id = source_data.get(id_key)
                    # Enhanced validation using helper function
                    if is_valid_source_id(source_id, source_name):
                        source_id_str = str(source_id).strip().strip('"')
                        constructed_url = f"{base_url}{source_id_str}"
                        extracted_links.append(constructed_url)
        
        # Clean URLs and join them into a semi-colon separated string
        web_links = MetadataGUI.clean_links('; '.join(extracted_links))

        # NEW PUBLISHER LOGIC - Use global PREFERRED_PUBLISHER_TYPES
        publishers = entry.get("publishers", [])
        pub_text = ""
        imprint_text = ""

        if isinstance(publishers, list) and publishers:
            publisher_infos = []

            for p in publishers:
                if isinstance(p, dict) and p.get('name') and p.get('type'):
                    name = p.get('name', '').strip()
                    ptype = p.get('type', '').strip()
                    if name:
                        publisher_infos.append((name, ptype))

            if publisher_infos:
                if len(publisher_infos) == 1:
                    pub_text = publisher_infos[0][0]
                    imprint_text = ""
                else:
                    # Prefer types defined in config
                    preferred = [p for p in publisher_infos if p[1].lower() in PREFERRED_PUBLISHER_TYPES]
                    others = [p for p in publisher_infos if p not in preferred]

                    selected = preferred[0] if preferred else publisher_infos[0]
                    pub_text = selected[0]

                    imprint_list = [f"{name} ({ptype})" for name, ptype in publisher_infos]
                    imprint_text = ", ".join(imprint_list)
        
        # ── NEW titles logic (Mangabaka API v2) ─────────────────────
        titles_arr = entry.get("titles", [])
        if not isinstance(titles_arr, list):
            titles_arr = []

        def _pick_series_title(titles):
            """Pick best Series title per priority rules in config."""
            for rule in SERIES_TITLE_PRIORITY:
                for t in titles:
                    if t.get("language") == rule["lang"] and t.get("is_primary") == rule["is_primary"]:
                        if rule["trait"] is None or rule["trait"] in t.get("traits", []):
                            return t.get("title", "")
            return ""

        def _get_localized_titles(titles):
            """Collect all titles from allowed languages for LocalizedSeries."""
            seen = set()
            result = []
            for t in titles:
                lang = t.get("language", "")
                title_val = t.get("title", "").strip()
                if lang in ALLOWED_LOCALIZED_LANGUAGES and title_val and title_val not in seen:
                    seen.add(title_val)
                    result.append(title_val)
            return ", ".join(result)

        series_title = _pick_series_title(titles_arr)
        localized = _get_localized_titles(titles_arr)

        # Fallback to legacy title field if new titles array is absent/empty
        if not series_title:
            series_title = safe_get(entry, "title")

        primary_title = series_title

        # ── Parse Year / Month / Day from published.start_date ───────
        start_year = ""
        start_month = ""
        start_day = ""
        published_field = entry.get("published", {})
        if isinstance(published_field, dict):
            start_date_str = published_field.get("start_date")
            if start_date_str and isinstance(start_date_str, str):
                date_parts = start_date_str.split("-")
                if len(date_parts) >= 1 and date_parts[0]:
                    start_year = date_parts[0]
                if len(date_parts) >= 2 and date_parts[1]:
                    try:
                        start_month = str(int(date_parts[1]))
                    except ValueError:
                        pass
                if len(date_parts) >= 3 and date_parts[2]:
                    try:
                        start_day = str(int(date_parts[2]))
                    except ValueError:
                        pass

        
        # Map content_rating to AgeRating using global map
        content_rating = safe_get(entry, "content_rating")
        age_rating = ""
        if content_rating:
            age_rating = AGE_RATING_MAPPING.get(content_rating.lower(), content_rating)
        
        # Extract chapter number and title from filename if provided
        chapter_number = ""
        filename_title = ""
        if filename:
            import os
            basename = os.path.basename(filename)
            basename_no_ext = os.path.splitext(basename)[0]

            chapter_match = CHAPTER_PATTERN.search(basename_no_ext)
            episode_match = EPISODE_PATTERN.search(basename_no_ext)
            if chapter_match:
                chapter_number = chapter_match.group(1)
            elif episode_match:
                chapter_number = episode_match.group(1)

            filename_title = EXTENSION_PATTERN.sub('', basename)
            filename_title = CHAPTER_PATTERN.sub('', filename_title)
            filename_title = VOLUME_PATTERN.sub('', filename_title)
            filename_title = BRACKET_CONTENT_PATTERN.sub('', filename_title)
            filename_title = PAREN_CONTENT_PATTERN.sub('', filename_title)
            filename_title = WHITESPACE_PATTERN.sub(' ', filename_title).strip()

        final_title = primary_title if primary_title else filename_title

        return {
            "Title": "",
            "Series": final_title,
            "Number": chapter_number,
            "Volume": "",
            "Summary": MetadataGUI.clean_html_description(safe_get(entry, "description")),
            "Writer": ", ".join(safe_list(entry.get("authors", []))),
            "CoverArtist": ", ".join(safe_list(entry.get("artists", []))),
            "Publisher": pub_text,
            "Imprint": imprint_text,
            "GTIN": "",
            "Genre": ", ".join(safe_list(entry.get("genres", []))),
            "Tags": ", ".join(safe_list(entry.get("tags", []))),
            "Year": start_year,
            "Month": start_month,
            "Day": start_day,
            "LanguageISO": safe_get(entry, "lang", "en"),
            "Web": web_links,
            "Count": (safe_get(entry, "final_volume") or safe_get(entry, "total_chapters")) if safe_get(entry, "status").lower() in ["completed", "canceled", "cancelled"] else "",
            "_total_chapters": safe_get(entry, "total_chapters") if safe_get(entry, "status").lower() in ["completed", "canceled", "cancelled"] else "",
            "_final_volume": safe_get(entry, "final_volume") if safe_get(entry, "status").lower() in ["completed", "canceled", "cancelled"] else "",
            "PageCount": "",
            "Teams": "",
            "Locations": "",
            "LocalizedSeries": localized,
            "Format": "",
            "AgeRating": age_rating,
            "type": safe_get(entry, "type"),
            "content_rating": safe_get(entry, "content_rating"),
            "entry_id": safe_get(entry, "id"),
            "all_titles": {
                "primary": series_title,
                "romanized": series_title,
                "native": "",
                "secondary": localized
            }
        }


    @staticmethod
    def clean_links(raw):
        """Clean and filter web links using the global blacklist"""
        if not raw:
            return ""
            
        links = [link.strip() for link in re.split(r'[;,]', raw) if link.strip()]
        cleaned = []
        seen = set()
        
        for link in links:
            # Normalize URL
            link_lower = link.lower().rstrip('/')
            if not link_lower.startswith(('http://', 'https://')):
                link = 'https://' + link
                link_lower = 'https://' + link_lower
            
            # Skip blacklisted domains from global config
            if any(bad in link_lower for bad in WEB_LINK_BLACKLIST):
                continue
                
            # Remove duplicates
            if link_lower not in seen:
                seen.add(link_lower)
                cleaned.append(link)
        
        return ', '.join(cleaned)

    @staticmethod
    def clean_html_description(text):
        """Clean HTML tags from description text for XML compatibility"""
        if not text:
            return ""
        
        # Only replace tags that affect formatting/newlines
        html_replacements = {
            '<br>': '\n', '<br/>': '\n', '<br />': '\n', '</br>': '\n',
            '<p>': '\n', '</p>': '\n'
        }
        
        cleaned = text
        for tag, replacement in html_replacements.items():
            cleaned = cleaned.replace(tag, replacement)
        
        # Obliterate all remaining HTML tags (<i>, <b>, <span>, etc.)
        cleaned = HTML_TAG_PATTERN.sub('', cleaned)
        
        # Clean up excess newlines using pre-compiled global
        cleaned = NEWLINE_CLEANUP_PATTERN.sub('\n\n', cleaned)
        
        return cleaned.strip()

    def save_current_metadata(self):
        """Save current form data to metadata storage"""
        if not self.cbz_paths or self.current_index >= len(self.cbz_paths):
            return
        current_file = self.cbz_paths[self.current_index]
        metadata = {}
        for field in self.fields:
            if field in ["AgeRating", "Format"]:
                metadata[field] = self.after_entries[field].get()
            else:
                metadata[field] = self.after_entries[field].get("1.0", tk.END).strip()
        
        with self._metadata_lock:  # Add thread safety
            self.file_metadata[current_file] = metadata


    def on_file_select(self, event):
        """Enhanced file selection handler without redundant logic"""
        selection = self.file_listbox.curselection()
        if not selection:
            return
    
        self.save_current_metadata()
        self.load_metadata(selection[0])
        self.populate_dropdown_for_current_file()

        # --- ADD THIS NEW BLOCK TO FIX THE TITLE SEARCH BAR ---
        current_file = self.cbz_paths[selection[0]]
        
        # When in individual mode, clicking a new file automatically updates the Manga Title bar
        if self.metadata_mode.get() == "individual":
            new_title = self._extract_title_from_filename(current_file)
            if new_title:
                # Update the search bar with the new series name
                self.title_var.set(new_title.translate(APOSTROPHE_MAP))


    def fetch_metadata_smart(self):
        """Smart fetch that chooses between batch and individual based on mode"""
        mode = self.metadata_mode.get()
        if mode == "batch":
            self.fetch_metadata_batch_fixed()
        else:
            self.fetch_metadata_individual()
            

    def fetch_metadata_batch_fixed(self):
        """FIXED version of fetch_metadata_batch - no popups"""
        title = self.title_var.get().strip()

        title = html.unescape(title)
        title = title.replace('‘', "'").replace('’', "'")
        title = title.replace('“', '"').replace('”', '"')

        if not title:
            print("❗ Error: Please enter a manga title")
            return

        try:
            self.metadata_options = get_metadata_from_dump(title)

            if not self.metadata_options:
                messagebox.showinfo("No Matches", f"No metadata found for: {title}")
                return
                
            self.metadata_options = self._sort_metadata_options(self.metadata_options)
            
            if self.metadata_options:
                dropdown_values = []
                for meta in self.metadata_options:
                    title_text = meta.get('Series') or meta.get('Title') or 'Unknown'
                    type_text = meta.get('type', '')
                    year_text = meta.get('Year', '')
                    content_rating_text = meta.get('content_rating', '')

                    parts = [title_text]
                    if type_text:
                        parts.append(f"({type_text.title()})")
                    if year_text:
                        parts.append(f"[{year_text}]")
                    if content_rating_text:
                        parts.append(f"[{content_rating_text.title()}]")

                    dropdown_values.append(" ".join(parts))

                self.dropdown['values'] = dropdown_values
                self.dropdown.current(0)
                self.update_metadata_from_dropdown()

                if len(self.metadata_options) == 1:
                    print(f"✅ Found 1 match for '{title}' - automatically selected")
                else:
                    print(f"✅ Found {len(self.metadata_options)} matches for '{title}'. First option selected - use dropdown to change.")

        except Exception as e:
            logging.error(f"Error fetching metadata: {e}")
            print(f"❌ Failed to fetch metadata: {str(e)}")


    def fetch_metadata_individual(self):
        with self._cbz_paths_lock:
            if not self.cbz_paths:
                messagebox.showerror("Error", "No CBZ files loaded")
                return
            # Get thread-safe copies
            cbz_paths_for_preview = self.cbz_paths[:3].copy() if len(self.cbz_paths) >= 3 else self.cbz_paths.copy()
            total_files_count = len(self.cbz_paths)
        
        # Test title extraction first
        test_titles = []
        for cbz_path in self.cbz_paths[:3]:  # Test first 3 files
            filename = os.path.basename(cbz_path)
            
            # FIX: Pass the full path, not just the filename
            title = self._extract_title_from_filename(cbz_path)
            test_titles.append(f"{filename} --->'{title}'")
        
        # Show user what titles will be extracted
        preview_msg = "Will extract these titles from filenames:\n\n" + "\n".join(test_titles)
        if total_files_count > 3:
            preview_msg += f"\n... and {total_files_count - 3} more files"
        
        result = messagebox.askyesno("Confirm Title Extraction", 
                                   preview_msg + "\n\nProceed with metadata fetch for ALL files?")
        if not result:
            return
        
        # Show progress UI
        self.progress_frame.pack(fill='x', pady=(5, 0))
        self.progress_bar.pack(fill='x')
        self.progress_label.pack(anchor='w')
        
        # Start fetching in background thread
        thread = Thread(target=self.fetch_individual_threaded, daemon=True)
        thread.start()
    
    
    def fetch_metadata_for_current_file(self):
        if not self.cbz_paths or self.current_index >= len(self.cbz_paths):
            return

        cbz_path = self.cbz_paths[self.current_index]
        filename = os.path.basename(cbz_path)

        title = self.title_var.get().strip()
        
        # ALREADY CORRECT: this one already used cbz_path!
        base_extracted_title = self._extract_title_from_filename(cbz_path)
        
        if not title:
            title = base_extracted_title

        result = messagebox.askyesno(
            "Re-Fetch Metadata",
            f"Refetch metadata for\n{filename}\n\nTitle: '{title}'?\n\nThis will update ALL files sharing this extracted title."
        )
        if not result:
            return

        try:
            metadata_options = get_metadata_from_dump(title)
            print(f"\rMatches for '{title}': {len(metadata_options)}")

            if metadata_options:
                self._sort_metadata_options(metadata_options)

                # Sync all files sharing this title
                files_to_update = [cbz_path]
                for path in self.cbz_paths:
                    if path != cbz_path:
                        # ALREADY CORRECT: this one already used path!
                        path_extracted = self._extract_title_from_filename(path)
                        path_cached_title = self.individual_metadata_cache.get(path, {}).get('title_used')
                        
                        if path_extracted == base_extracted_title or (title and path_cached_title == title):
                            if path not in files_to_update:
                                files_to_update.append(path)

                best_match = metadata_options[0]

                for path in files_to_update:
                    self.individual_metadata_cache[path] = {
                        'options': metadata_options,
                        'title_used': title
                    }
                    self.dropdown_selection_per_file[path] = 0
                    
                    current_metadata = self.file_metadata.get(path, {field: "" for field in self.fields})
                    file_specific_fields = ["Title", "Number", "Volume", "PageCount"]
                    preserved_data = {f: current_metadata.get(f) for f in file_specific_fields if current_metadata.get(f)}
                    
                    current_metadata.update(best_match)
                    current_metadata.update(preserved_data)
                    self.file_metadata[path] = current_metadata

                self.populate_dropdown_for_current_file()
                self._update_file_listbox_indicators()
                self.load_metadata(self.current_index)
                
                print(f"✅ Success: Updated metadata for {len(files_to_update)} files matching '{title}'")
            else:
                messagebox.showinfo("No Matches", f"No metadata found for: {title}")

        except Exception as e:
            logging.error(f"Error refetching metadata: {e}")
            messagebox.showerror("Error", f"Failed to refetch metadata: {e}")

    def fetch_individual_threaded(self):
        """Background thread for individual metadata fetching with intelligent caching"""
        try:
            total_files = len(self.cbz_paths)
            self.individual_metadata_cache = {}
            successful_fetches = 0
            failed_extractions = []
            failed_fetches = []
            
            # CACHE: Store results for titles we've already searched this session
            title_search_cache = {}

            for i, cbz_path in enumerate(self.cbz_paths):
                filename = os.path.basename(cbz_path)
                self.after(0, self._update_progress, i, total_files, filename)

                # FIX: Pass the full path, not just the filename
                title = self._extract_title_from_filename(cbz_path)

                if not title or len(title.strip()) < 2:
                    failed_extractions.append(filename)
                    continue

                try:
                    if title in title_search_cache:
                        metadata_options = title_search_cache[title]
                    else:
                        metadata_options = get_metadata_from_dump(title)
                        
                        if metadata_options:
                            self._sort_metadata_options(metadata_options)
                            
                        title_search_cache[title] = metadata_options

                    if metadata_options:
                        self.individual_metadata_cache[cbz_path] = {
                            'options': metadata_options,
                            'title_used': title
                        }
                        
                        best_match = metadata_options[0]
                        current_metadata = self.file_metadata.get(cbz_path, {field: "" for field in self.fields})
                        current_metadata.update(best_match)
                        self.file_metadata[cbz_path] = current_metadata
                        
                        successful_fetches += 1
                    else:
                        failed_fetches.append(filename)

                except Exception as e:
                    failed_fetches.append(f"{filename} (error: {str(e)})")
                    logging.error(f"Error fetching metadata for {filename}: {e}")

            self.after(0, self._finish_individual_fetch, successful_fetches, total_files, failed_extractions, failed_fetches)

        except Exception as e:
            error_msg = f"Unexpected error in metadata fetch: {str(e)}"
            logging.critical(error_msg, exc_info=True)
            self.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.after(0, self._hide_progress)
    
    def fetch_individual_threaded(self):
        """Background thread for individual metadata fetching with intelligent caching"""
        try:
            total_files = len(self.cbz_paths)
            self.individual_metadata_cache = {}
            successful_fetches = 0
            failed_extractions = []
            failed_fetches = []
            
            # CACHE: Store results for titles we've already searched this session
            title_search_cache = {}

            for i, cbz_path in enumerate(self.cbz_paths):
                filename = os.path.basename(cbz_path)
                self.after(0, self._update_progress, i, total_files, filename)

                # --- FIX IS HERE: Pass the full path (cbz_path), NOT just the filename ---
                title = self._extract_title_from_filename(cbz_path)

                if not title or len(title.strip()) < 2:
                    failed_extractions.append(filename)
                    continue

                try:
                    # Check cache first!
                    if title in title_search_cache:
                        metadata_options = title_search_cache[title]
                    else:
                        # LOCAL DUMP ONLY Search
                        metadata_options = get_metadata_from_dump(title)
                        
                        if metadata_options:
                            self._sort_metadata_options(metadata_options)
                            
                        title_search_cache[title] = metadata_options # Save to cache

                    if metadata_options:
                        self.individual_metadata_cache[cbz_path] = {
                            'options': metadata_options,
                            'title_used': title
                        }
                        
                        # --- THE FIX: AUTO-APPLY THE #1 BEST MATCH ---
                        best_match = metadata_options[0]
                        current_metadata = self.file_metadata.get(cbz_path, {field: "" for field in self.fields})
                        current_metadata.update(best_match)
                        self.file_metadata[cbz_path] = current_metadata
                        # ---------------------------------------------
                        
                        successful_fetches += 1
                    else:
                        failed_fetches.append(filename)

                except Exception as e:
                    failed_fetches.append(f"{filename} (error: {str(e)})")
                    logging.error(f"Error fetching metadata for {filename}: {e}")

            # Complete the process
            self.after(0, self._finish_individual_fetch, successful_fetches, total_files, failed_extractions, failed_fetches)

        except Exception as e:
            error_msg = f"Unexpected error in metadata fetch: {str(e)}"
            logging.critical(error_msg, exc_info=True)
            self.after(0, lambda: messagebox.showerror("Error", error_msg))
            self.after(0, self._hide_progress)

    def _update_progress(self, current, total, filename):
        """Update progress bar and label"""
        progress = (current / total) * 100
        self.progress_bar['value'] = progress
        self.progress_var.set(f"Processing: {filename} ({current + 1}/{total})")
        self.update_idletasks()

    def _finish_individual_fetch(self, successful, total, failed_extractions, failed_fetches):
        """Finish individual fetch process"""
        self._hide_progress()
        
        # Create detailed results message
        results = []
        if successful > 0:
            results.append(f"✓ Successfully fetched metadata for {successful}/{total} files")
        
        if failed_extractions:
            results.append(f"⚠ Could not extract titles from {len(failed_extractions)} files:")
            for filename in failed_extractions[:5]:  # Show first 5
                results.append(f"  - {filename}")
            if len(failed_extractions) > 5:
                results.append(f"  ... and {len(failed_extractions) - 5} more")
        
        if failed_fetches:
            results.append(f"⚠ No metadata found for {len(failed_fetches)} files:")
            for filename in failed_fetches[:5]:  # Show first 5
                results.append(f"  - {filename}")
            if len(failed_fetches) > 5:
                results.append(f"  ... and {len(failed_fetches) - 5} more")
        
        if successful == 0:
            results.append("\nTips for better results:")
            results.append("- Make sure filenames contain the manga title")
            results.append("- Try removing extra text like '[Group]' or quality tags")
            results.append("- Use 'Batch Mode' if they're all the same series")
            
            messagebox.showinfo("No Results", "\n".join(results))
            return

        # Update file listbox to show which files have metadata instantly
        self._update_file_listbox_indicators()

        # Refresh current display
        if self.cbz_paths and self.current_index < len(self.cbz_paths):
            self.load_metadata(self.current_index)
            self.populate_dropdown_for_current_file()            
        
        # Show results
        print("\n".join(results))
        messagebox.showinfo("Fetch Complete", "\n".join(results))

    def _hide_progress(self):
        """Hide progress UI"""
        self.progress_frame.pack_forget()

    def _extract_title_from_filename(self, file_path):
        """Extract title from either the filename or the parent folder based on user preference"""
        if getattr(self, 'use_folder_name_var', None) and self.use_folder_name_var.get():
            # FOR FOLDERS: Extract the parent folder name
            target_name = os.path.basename(os.path.dirname(file_path))
            if not target_name: 
                target_name = os.path.basename(file_path)
                
            cleaned = BRACKET_REMOVAL_PATTERN.sub('', target_name)
            cleaned = SCANLATOR_REMOVAL_PATTERN.sub('', cleaned)
            return cleaned.strip() if cleaned.strip() else target_name
            
        else:
            # FOR FILES: Default behavior (extract from filename)
            target_name = os.path.basename(file_path)
            return auto_extract_title(target_name)


    def _update_file_listbox_indicators(self):
        """Update file listbox to show which files have metadata while preserving folder names"""
        if not hasattr(self, 'file_listbox'):
            return
        
        self.file_listbox.delete(0, tk.END)
        
        display_names = []
        for cbz_path in self.cbz_paths:
            folder_name = os.path.basename(os.path.dirname(cbz_path))
            file_name = os.path.basename(cbz_path)
            
            if folder_name:
                display_name = f"{folder_name}/{file_name}"
            else:
                display_name = file_name
                
            if cbz_path in self.individual_metadata_cache:
                indicator = "✓ "
            else:
                indicator = ""
            
            display_names.append(f"{indicator}{display_name}")
            
        self.file_listbox.insert(tk.END, *display_names)

    def refresh_metadata_from_web_url(self):
        """Fetch updated metadata from local dump based on Mangabaka ID in Web field for ALL loaded files"""
        if not self.cbz_paths:
            return
            
        # Group all loaded files by their embedded Mangabaka ID
        files_by_id = {}
        
        for path in self.cbz_paths:
            # Prioritize updated metadata web link, fallback to original
            web_links = self.file_metadata.get(path, {}).get("Web", "")
            if not web_links:
                web_links = self.original_metadata.get(path, {}).get("Web", "")
                
            if web_links:
                # Support both .org and .dev
                match = re.search(r'mangabaka\.(?:org|dev)/(?:manga/)?(\d+)', web_links, re.IGNORECASE)
                if match:
                    entry_id = match.group(1)
                    if entry_id not in files_by_id:
                        files_by_id[entry_id] = []
                    files_by_id[entry_id].append(path)
        
        if not files_by_id:
            messagebox.showinfo("Error", "Could not find any valid Mangabaka URLs (.org or .dev) in the loaded files.")
            return
            
        # Fetch and apply metadata for each unique ID found
        total_updated = 0
        failed_ids = []
        
        for entry_id, paths in files_by_id.items():
            updated_meta = get_metadata_from_dump_by_id(entry_id)
            
            if not updated_meta:
                failed_ids.append(entry_id)
                continue
                
            # Apply the specific updated_meta to only the files that share this entry_id
            for path in paths:
                current_metadata = self.file_metadata.get(path, {field: "" for field in self.fields})
                file_specific_fields = ["Title", "Number", "Volume", "PageCount"]
                preserved_data = {f: current_metadata.get(f) for f in file_specific_fields if current_metadata.get(f)}
                
                current_metadata.update(updated_meta)
                current_metadata.update(preserved_data)

                # --- NEW: Dynamic Count Logic ---
                series_type = current_metadata.get("type", "").upper()
                
                if series_type in ["MANHWA", "MANHUA", "OEL"]:
                    path_lower = path.lower()
                    is_webcomic_path = any(kw.lower() in path_lower for kw in WEBCOMIC_COUNT_KEYWORDS)
                    
                    if is_webcomic_path:
                        # Prefer total_chapters, fallback to final_volume
                        current_metadata["Count"] = current_metadata.get("_total_chapters") or current_metadata.get("_final_volume") or ""
                    else:
                        # Prefer final_volume, fallback to total_chapters
                        current_metadata["Count"] = current_metadata.get("_final_volume") or current_metadata.get("_total_chapters") or ""
                else:
                    # Default Manga logic (Always prefer physical volume count first)
                    current_metadata["Count"] = current_metadata.get("_final_volume") or current_metadata.get("_total_chapters") or ""

                # Remove temporary helper keys so they don't cause clutter
                current_metadata.pop("_total_chapters", None)
                current_metadata.pop("_final_volume", None)
                # --------------------------------

                self.file_metadata[path] = current_metadata
                
                # Keep dropdown options in sync
                if path in self.individual_metadata_cache and self.individual_metadata_cache[path].get('options'):
                    # We pass the raw updated_meta (which still holds the hidden keys) 
                    # so the dropdown logic can re-evaluate if needed
                    self.individual_metadata_cache[path]['options'][0] = updated_meta
                    
            total_updated += len(paths)
            print(f"✅ Success: Refreshed metadata for {len(paths)} files using Web ID {entry_id}")
            
        # Refresh the UI for the currently selected file
        self.load_metadata(self.current_index)
        self.populate_dropdown_for_current_file()
        
        # Display a summary of the bulk operation
        if failed_ids:
            messagebox.showwarning(
                "Refresh Partially Complete", 
                f"Updated {total_updated} files across {len(files_by_id) - len(failed_ids)} series.\n\n"
                f"Failed to find dump data for IDs: {', '.join(failed_ids)}"
            )
        else:
            messagebox.showinfo(
                "Refresh Complete", 
                f"Successfully updated {total_updated} files across {len(files_by_id)} series based on their Web IDs."
            )

    def fetch_anilist_metadata_gui(self, on_complete=None):
        """Fetch AniList metadata for ALL files based on current mode with smart API caching"""
        if not self.cbz_paths:
            messagebox.showerror("Error", "No CBZ files loaded")
            return
            
        mode = self.metadata_mode.get()
        is_batch = mode == "batch"
        
        # Display a summary of the bulk operation
        if not is_batch:
            if not messagebox.askyesno("Fetch AniList Metadata", 
                                      f"This will fetch AniList metadata for all {len(self.cbz_paths)} files.\n"
                                      f"Identical series will be cached to avoid duplicate API calls.\n\nContinue?"):
                return
                
        print(f"\n{'='*60}\nMETADATA FETCH STARTING ({mode.upper()} MODE)\n{'='*60}")
        
        # Show progress UI
        self.progress_frame.pack(fill='x', pady=(5, 0))
        self.progress_bar.pack(fill='x')
        self.progress_label.pack(anchor='w')
        self.progress_bar['value'] = 0
        self.progress_var.set("Starting AniList Fetch...")
        
        # Start fetching in background thread to prevent UI freezing, passing on_complete
        from threading import Thread
        thread = Thread(target=self._fetch_anilist_threaded, args=(is_batch, on_complete), daemon=True)
        thread.start()


    def _fetch_anilist_threaded(self, is_batch, on_complete=None):
        """Background thread for AniList metadata fetching"""
        files_updated, files_with_no_links, files_with_errors = 0, [], []
        total_files = len(self.cbz_paths)
        
        # CACHE: Store AniList API results by AniList ID to prevent duplicate network calls
        anilist_api_cache = {}
        cached_batch_metadata = None # Used to store metadata if in batch mode
        
        for i, cbz_path in enumerate(self.cbz_paths):
            filename = os.path.basename(cbz_path)
            print(f"Processing [{i+1}/{total_files}]: {filename}")
            
            # Safely update the progress bar from the background thread
            self.after(0, self._update_progress, i, total_files, filename)
            
            # If in batch mode and we already fetched the metadata, just apply it
            if is_batch and cached_batch_metadata:
                self.file_metadata[cbz_path].update(cached_batch_metadata)
                files_updated += 1
                continue
                
            current_metadata = self.file_metadata.get(cbz_path, {})
            web_links = current_metadata.get('Web', '')
            
            if not web_links:
                files_with_no_links.append(filename)
                print("No web links found in metadata")
                if is_batch: break # If batch mode fails on first file, abort
                continue
                
            try:
                # Let extract_anilist_id_from_url handle the comma-splitting and finding
                anilist_id = extract_anilist_id_from_url(web_links)
                
                # Check cache first!
                if anilist_id in anilist_api_cache:
                    print(f"Loading AniList metadata for ID {anilist_id} from cache (Instant!)")
                    anilist_metadata = anilist_api_cache[anilist_id]
                else:
                    print(f"Fetching AniList metadata for ID {anilist_id} from API...")
                    anilist_metadata = fetch_anilist_metadata(anilist_id)
                    if anilist_metadata:
                        anilist_api_cache[anilist_id] = anilist_metadata # Save to cache
                
                if anilist_metadata:
                    current_metadata.update(anilist_metadata)
                    self.file_metadata[cbz_path] = current_metadata
                    files_updated += 1
                    
                    if is_batch:
                        cached_batch_metadata = anilist_metadata # Save for rest of loop
                else:
                    files_with_errors.append(filename)
                    print(f"AniList API returned no data for ID: {anilist_id}")
                    if is_batch: break
                    
            except Exception as e:
                files_with_errors.append(filename)
                print(f"Error processing AniList data: {str(e)}")
                if is_batch: break
                
        # Execute final UI updates on main thread and pass the callback forward
        self.after(0, self._finish_anilist_fetch, is_batch, files_updated, total_files,
                   len(anilist_api_cache), files_with_no_links, files_with_errors, on_complete)


    def _finish_anilist_fetch(self, is_batch, files_updated, total_files,
                              cache_size, files_with_no_links, files_with_errors, on_complete=None):
        """Finish AniList fetch process and update UI"""
        self._hide_progress()
        
        # Refresh UI
        self.load_metadata(self.current_index)
        
        # Print Summary
        print(f"\n{'='*60}\nANILIST FETCH RESULTS SUMMARY\n{'='*60}")
        print(f"Successfully updated: {files_updated}/{total_files} files")
        if not is_batch:
            print(f"Unique API calls made: {cache_size}") # Shows you how many calls were saved!
            
        for lst, label in [(files_with_no_links, "No AniList links"), (files_with_errors, "Errors")]:
            if lst:
                print(f"{label}: {len(lst)} files")
                for f in lst: print(f)
                
        if files_with_no_links or files_with_errors:
            print("\nTROUBLESHOOTING TIPS:")
            if files_with_no_links: print("- Fetch Mangabaka metadata first to get AniList links")
            if files_with_errors: print("- Verify the AniList manga IDs/URLs are valid")
        print(f"{'='*60}\n")
        
        # Show success message
        if files_updated > 0:
            print("AniList Fetch Complete", f"Successfully updated {files_updated}/{total_files} files!\nCheck console for details.")
        else:
            messagebox.showwarning("AniList Fetch Complete", "No files were updated.\nCheck console for detailed error information.")
            
        # Trigger the callback function if it was provided
        if on_complete:
            self.after(0, on_complete)

    def update_metadata_from_dropdown(self, *args):
        """Updated method to safely apply dropdown metadata across matching files"""
        selection_idx = self.dropdown.current()
        if selection_idx < 0 or selection_idx >= len(self.metadata_options):
            return

        selected_metadata = self.metadata_options[selection_idx].copy()
        
        if "Web" in selected_metadata:
            selected_metadata["Web"] = self.clean_links(selected_metadata["Web"])

        mode = self.metadata_mode.get()
        
        file_specific_fields = ["Title", "Number", "Volume", "PageCount"]

        def apply_metadata_safely(path):
            current_meta = self.file_metadata.get(path, {})
            
            preserved_data = {f: current_meta.get(f) for f in file_specific_fields if current_meta.get(f)}

            new_meta = {field: "" for field in self.fields}
            new_meta.update(current_meta)
            new_meta.update(selected_metadata)
            
            new_meta.update(preserved_data)

            # --- NEW: Dynamic Count Logic ---
            series_type = new_meta.get("type", "").upper()
            
            if series_type in ["MANHWA", "MANHUA", "OEL"]:
                path_lower = path.lower()
                is_webcomic_path = any(kw.lower() in path_lower for kw in WEBCOMIC_COUNT_KEYWORDS)
                
                if is_webcomic_path:
                    # Prefer total_chapters, fallback to final_volume
                    new_meta["Count"] = new_meta.get("_total_chapters") or new_meta.get("_final_volume") or ""
                else:
                    # Prefer final_volume, fallback to total_chapters
                    new_meta["Count"] = new_meta.get("_final_volume") or new_meta.get("_total_chapters") or ""
            else:
                # Default Manga logic (Always prefer physical volume count first)
                new_meta["Count"] = new_meta.get("_final_volume") or new_meta.get("_total_chapters") or ""

            # Remove temporary helper keys so they don't cause clutter
            new_meta.pop("_total_chapters", None)
            new_meta.pop("_final_volume", None)
            # --------------------------------

            if not new_meta.get("Volume"):
                vol = extract_volume_from_filename(os.path.basename(path))
                if vol:
                    new_meta["Volume"] = vol
                    
            self.file_metadata[path] = new_meta

        if mode == "batch":
            # BATCH MODE: Apply this exact metadata to EVERY loaded file
            with self._cbz_paths_lock:
                for cbz_path in self.cbz_paths:
                    self.dropdown_selection_per_file[cbz_path] = selection_idx
                    apply_metadata_safely(cbz_path)
        else:
            # INDIVIDUAL MODE: Only apply to files that used this exact search term
            if self.cbz_paths and self.current_index < len(self.cbz_paths):
                current_file = self.cbz_paths[self.current_index]

                # Get the title we used to search for this specific file
                cache_data = self.individual_metadata_cache.get(current_file, {})
                title_used = cache_data.get('title_used')

                # Find ALL files that used the exact same search title
                files_to_update = [current_file]
                if title_used:
                    for path, data in self.individual_metadata_cache.items():
                        if data.get('title_used') == title_used and path != current_file:
                            files_to_update.append(path)

                for path in files_to_update:
                    self.dropdown_selection_per_file[path] = selection_idx
                    apply_metadata_safely(path)

        # Refresh the UI with the newly applied metadata
        self.load_metadata(self.current_index)
        
    def insert_metadata(self):
        """Insert metadata into all CBZ files - parallel processing version"""
        with self._cbz_paths_lock:
            if not self.cbz_paths:
                messagebox.showerror("Error", "No CBZ files loaded")
                return
            total_files = len(self.cbz_paths)
        
        # Only show confirmation dialog if not previously confirmed
        if not getattr(self, '_skip_confirmation', False):
            if not messagebox.askyesno("Confirm Metadata Insertion", 
                f"Insert metadata into {total_files} CBZ files?\n\nThis will modify the files and cannot be undone.\n\nClick Yes to proceed and skip this confirmation in the future."):
                return
            self._skip_confirmation = True
        
        self.save_current_metadata()
        self._progress_lock = Lock()
        self._processed_count = 0
        
        self._max_workers = MAX_WORKER_THREADS if MAX_WORKER_THREADS else min(8, (os.cpu_count() or 4) + 4)
        
        self._toggle_insertion_ui(active=True)
        Thread(target=self._insert_metadata_threaded, daemon=True).start()

    def _toggle_insertion_ui(self, active):
        """Toggle UI state and progress frame visibility during insertion"""
        state = 'disabled' if active else 'normal'
        
        # Toggle buttons and inputs
        if not hasattr(self, '_insertion_buttons') and hasattr(self, 'button_frame'):
            self._insertion_buttons = [w for w in self.button_frame.winfo_children() if isinstance(w, ttk.Button)]
        for btn in getattr(self, '_insertion_buttons', []):
            btn.configure(state=state)
            
        for widget in ('title_entry', 'file_listbox'):
            if hasattr(self, widget):
                getattr(self, widget).configure(state=state)
                
        if not active:
            if hasattr(self, 'insertion_progress_frame'):
                self.insertion_progress_frame.pack_forget()
            for attr in ('_progress_lock', '_processed_count', '_max_workers'):
                if hasattr(self, attr): delattr(self, attr)
            return

        # Create/Show progress UI
        if not hasattr(self, 'insertion_progress_frame'):
            parent = self.button_frame.master if hasattr(self, 'button_frame') else self
            self.insertion_progress_frame = ttk.Frame(parent)
            
            self.insertion_progress_bar = ttk.Progressbar(self.insertion_progress_frame, mode='determinate')
            self.insertion_progress_bar.pack(fill='x', pady=(0, 5))
            
            self.insertion_status_var = tk.StringVar()
            ttk.Label(self.insertion_progress_frame, textvariable=self.insertion_status_var).pack(anchor='w')
            
            self.insertion_cancel_var = tk.BooleanVar(value=False)
            ttk.Button(self.insertion_progress_frame, text="Cancel Operation", 
                      command=lambda: self.insertion_cancel_var.set(True)).pack(anchor='center', pady=(5, 0))
            
        self.insertion_progress_bar['value'] = 0
        self.insertion_status_var.set("Initializing parallel processing...")
        self.insertion_cancel_var.set(False)
        self.insertion_progress_frame.pack(fill='x', pady=(5, 10), before=getattr(self, 'button_frame', None))

    def _insert_metadata_threaded(self):
        """Background thread for parallel metadata insertion"""
        try:
            total = len(self.cbz_paths)
            success_count, error_files = 0, []
            
            # Prepare metadata mapping
            processed_metadata = {}
            for path in self.cbz_paths:
                raw = self.file_metadata.get(path, {})
                meta = {}
                for field in self.fields:
                    val = raw.get(field)
                    if not val: continue
                    if field == "Web" and isinstance(val, str) and '\n' in val:
                        meta[field] = ', '.join(u.strip() for u in val.split() if u.strip())
                    else:
                        meta[field] = val
                processed_metadata[path] = meta
                
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                future_to_path = {executor.submit(self._process_single_cbz_file, p, processed_metadata[p]): p for p in self.cbz_paths}
                
                for future in as_completed(future_to_path):
                    if getattr(self, 'insertion_cancel_var', None) and self.insertion_cancel_var.get():
                        [f.cancel() for f in future_to_path]
                        self.after(0, self._finish_insertion, "cancelled", success_count, total, error_files)
                        return
                        
                    filename = os.path.basename(future_to_path[future])
                    with self._progress_lock:
                        self._processed_count += 1
                        current = self._processed_count
                        
                    self.after(0, self._update_insertion_progress, current - 1, total, filename)
                    
                    try:
                        res = future.result()
                        if res is True: success_count += 1
                        else: error_files.append(f"{filename}: {res}")
                    except Exception as e:
                        error_files.append(f"{filename}: {e}")
                        
            self.after(0, self._finish_insertion, "success", success_count, total, error_files)
            
        except Exception as e:
            self.after(0, self._finish_insertion, "error", 0, 0, [], str(e))

    def _process_single_cbz_file(self, cbz_path, metadata):
        """Process a single CBZ file (called by thread pool)"""
        try:
            if not metadata.get('PageCount'):
                try: metadata['PageCount'] = str(count_pages_in_cbz(cbz_path))
                except Exception as e: logging.warning(f"Could not count pages in {os.path.basename(cbz_path)}: {e}")
            
            insert_comicinfo_into_cbz(cbz_path, create_comicinfo_xml(metadata))
            return True
        except Exception as e:
            return str(e)

    def _update_insertion_progress(self, current, total, filename):
        """Update progress bar and status"""
        if hasattr(self, 'insertion_progress_bar'):
            self.insertion_progress_bar['value'] = (current / total) * 100
        if hasattr(self, 'insertion_status_var'):
            name = filename[:47] + "..." if len(filename) > 50 else filename
            self.insertion_status_var.set(f"Processing: {name} ({current + 1}/{total}) [{total - current} remaining, using {getattr(self, '_max_workers', 1)} threads]")
        self.update_idletasks()

    def _finish_insertion(self, status, success, total, errors=None, error_msg=None):
        """Handle all completion states (success, cancelled, error)"""
        self._toggle_insertion_ui(active=False)
        errors = errors or []
        
        if status == "cancelled":
            messagebox.showinfo("Operation Cancelled", f"Operation cancelled by user.\n\nSuccessfully processed {success} files before cancellation.")
        elif status == "error":
            messagebox.showerror("Critical Error", f"Critical error occurred:\n{error_msg}\n\nSuccessfully processed {success} files before error.")
        elif errors:
            if len(errors) > 5:
                self._show_detailed_results(success, total, errors)
            else:
                msg = f"Processed {success}/{total} files successfully.\n\nErrors in {len(errors)} files:\n" + "\n".join(errors)
                messagebox.showwarning("Partial Success", msg)
        else:
            print("Success", f"Successfully inserted metadata into all {success} CBZ files using {getattr(self, '_max_workers', 1)} parallel threads!")
            
    def _show_detailed_results(self, success, total, errors):
        """Show detailed results in a scrollable window"""
        win = tk.Toplevel(self)
        win.title("Metadata Insertion Results")
        win.transient(self)
        win.grab_set()
        
        ttk.Label(win, text=f"Processed {success}/{total} files successfully | {len(errors)} errors", font=('TkDefaultFont', 10, 'bold')).pack(pady=10)
        
        frame = ttk.Frame(win)
        frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        txt = tk.Text(frame, wrap='word', height=15)
        sb = ttk.Scrollbar(frame, orient='vertical', command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        
        txt.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        
        for err in errors: txt.insert('end', f" {err}\n")
        txt.configure(state='disabled')
        
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=10)
        win.geometry("600x400")
        win.update_idletasks()
        center_window(win, 600, 400)
                
    def navigate_file(self, direction):
        """Navigate files by offset (+1 for next, -1 for previous)"""
        if not self.cbz_paths:
            return
            
        self.save_current_metadata()
        self.current_index = (self.current_index + direction) % len(self.cbz_paths)
        self.load_metadata(self.current_index)
        self.populate_dropdown_for_current_file()
        
        self.file_listbox.select_clear(0, tk.END)
        self.file_listbox.select_set(self.current_index)
        self.file_listbox.see(self.current_index)

    def fill_metadata_field(self, field_type, on_complete=None):
        """Generic function to auto-fill volume, chapter, or page count for all files"""
        if not self.cbz_paths:
            return
            
        # STEP 1: If it's page counting, spin up the background thread
        if field_type == "pages":
            self.progress_frame.pack(fill='x', pady=(5, 0))
            self.progress_bar['value'] = 0
            self.progress_var.set("Counting pages...")
            
            from threading import Thread
            Thread(target=self._threaded_page_counter, args=(on_complete,), daemon=True).start()
            return

        # STEP 2: For volume and chapter, regex is practically instant so we run it on the main thread
        updated_count = 0
        failed_files = []
        
        for cbz_path in self.cbz_paths:
            filename = os.path.basename(cbz_path)
            value = None
            
            try:
                if field_type == "volume":
                    value = extract_volume_from_filename(filename)
                    field_name = "Volume"
                elif field_type == "chapter":
                    value = extract_chapter_from_filename(filename)
                    field_name = "Number"
                
                if value is not None:
                    if cbz_path not in self.file_metadata:
                        self.file_metadata[cbz_path] = {f: "" for f in self.fields}
                    
                    self.file_metadata[cbz_path][field_name] = value
                    updated_count += 1
            
            except Exception as e:
                failed_files.append(filename)
                logging.error(f"Failed to process {field_type} for {cbz_path}: {e}")
        
        # Refresh UI
        self.load_metadata(self.current_index)
        if hasattr(self, '_update_file_listbox_indicators'):
            self._update_file_listbox_indicators()
            
        # Logging
        labels = {
            "volume": ("Volume Info", "volume information"),
            "chapter": ("Chapter Info", "chapter/issue numbers")
        }
        title, noun = labels[field_type]
        
        if updated_count > 0:
            print(f"[{title}] Successfully updated {noun} for {updated_count} files!")
        else:
            print(f"[{title}] No {noun} could be extracted/counted for any files")
            
        # Trigger the callback immediately since regex was instant
        if on_complete:
            self.after(0, on_complete)


    def _threaded_page_counter(self, on_complete=None):
        """Background thread to count pages in CBZ files without freezing UI"""
        updated_count = 0
        failed_files = []
        total_files = len(self.cbz_paths)
        
        for i, cbz_path in enumerate(self.cbz_paths):
            filename = os.path.basename(cbz_path)
            
            # Safely update progress bar from thread (uses your existing update_progress method)
            self.after(0, self._update_progress, i, total_files, filename)
            
            try:
                value = count_pages_in_cbz(cbz_path)
                if value is not None and value > 0:
                    value = str(value)
                else:
                    value = None
                    
                if value is not None:
                    if cbz_path not in self.file_metadata:
                        self.file_metadata[cbz_path] = {f: "" for f in self.fields}
                    
                    self.file_metadata[cbz_path]["PageCount"] = value
                    updated_count += 1
            except Exception as e:
                failed_files.append(filename)
                logging.error(f"Failed to process pages for {cbz_path}: {e}")
                
        # Send everything back to the main thread to update UI safely
        self.after(0, self._finish_page_counter, updated_count, failed_files, on_complete)
        
    def _finish_page_counter(self, updated_count, failed_files, on_complete=None):
        """Finish page count process and update UI on main thread"""
        self._hide_progress()
        self.load_metadata(self.current_index)
        
        if hasattr(self, '_update_file_listbox_indicators'):
            self._update_file_listbox_indicators()
            
        if updated_count > 0:
            if failed_files:
                msg = (f"Updated page count for {updated_count}/{len(self.cbz_paths)} files.\n\n"
                       f"Failed to process {len(failed_files)} files:\n" + 
                       "\n".join(failed_files[:5]))
                if len(failed_files) > 5:
                    msg += f"\n... and {len(failed_files) - 5} more"
                messagebox.showinfo("Page Count", msg)
            else:
                print(f"[Page Count] Successfully counted pages for {updated_count} files!")
        else:
            print(f"[Page Count] No pages could be counted for any files")
            
        # FINALLY: Trigger the callback function so save_current_series executes!
        if on_complete:
            self.after(0, on_complete)        

    def fill_title_from_filename(self):
        if not self.cbz_paths:
            return

        count = 0
        files_to_process = self.cbz_paths

        for cbz_path in files_to_process:
            filename = os.path.basename(cbz_path)
            name_no_ext = os.path.splitext(filename)[0]

            # Use the global pattern INSIDE the loop
            vol_match = TITLE_FALLBACK_PATTERN.search(name_no_ext)

            if vol_match:
                extracted_title = name_no_ext[:vol_match.end()].strip()
            else:
                extracted_title = name_no_ext.strip()

            if extracted_title:
                if cbz_path not in self.file_metadata:
                    self.file_metadata[cbz_path] = {}
                self.file_metadata[cbz_path]["Title"] = extracted_title
                count += 1

        if self.cbz_paths:
            self.load_metadata(self.current_index)

        print(f"Updated titles for {count} files based on filename patterns.")

    def _toggle_folder_name_mode(self):
        """React instantly when the user toggles the 'Use Folder Name' checkbox."""
        if not hasattr(self, 'cbz_paths') or not self.cbz_paths:
            return
            
        # Clear the cache so it stops holding onto old filename extractions
        if hasattr(self, 'individual_metadata_cache'):
            self.individual_metadata_cache.clear()
            
        # Instantly update the Title text box for the currently selected file
        if self.current_index < len(self.cbz_paths):
            current_path = self.cbz_paths[self.current_index]
            new_title = self._extract_title_from_filename(current_path)
            if new_title:
                self.title_var.set(new_title)
                
            # Reload metadata to refresh the UI and clear stale dropdowns
            self.load_metadata(self.current_index)
            
    def do_all_operations(self):
        """Execute all metadata operations in sequence via callbacks"""
        try:
            # Step 1: Start AniList fetch. When done, it will call _continue_do_all
            self.fetch_anilist_metadata_gui(on_complete=self._continue_do_all)
        except Exception as e:
            print(f"Error during Do All operation: {e}")

    def _continue_do_all(self):
        try:
            # Step 2: Run the fast synchronous tasks
            self.fill_metadata_field("volume")
            self.fill_metadata_field("chapter")
            self.fill_title_from_filename()
            
            # Step 3: Start Page counting. When done, trigger the save!
            self.fill_metadata_field("pages", on_complete=self.save_current_series)
            
        except Exception as e:
            print(f"Error during Do All continuation: {e}")
            
    def do_all_operations_alt(self):
        """Execute all metadata operations in sequence (No AniList)"""
        try:
            # Skip Anilist and jump straight to the synchronous fields & page count
            self._continue_do_all()
        except Exception as e:
            print(f"Error during Do All Alt operation: {e}")

if __name__ == '__main__':
    try:
        app = MetadataGUI()
        app.mainloop()
    except Exception as e:
        logging.error(f"Application error: {e}")
        print(f"Error starting application: {e}")
        input("Press Enter to exit...")
