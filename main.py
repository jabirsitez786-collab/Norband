import asyncio
import os
import sys
import logging
import subprocess
import psutil
import sqlite3
import hashlib
import json
import zipfile
import venv
import shutil
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

# Enhanced environment loading with better error handling
def load_environment_variables():
    """Load environment variables with enhanced error handling"""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logging.info(f"Loaded .env from: {env_file}")
    
    TOKEN = os.getenv('BOT_TOKEN')
    OWNER_ID_STR = os.getenv('OWNER_ID')
    ADMIN_ID_STR = os.getenv('ADMIN_ID')
    YOUR_USERNAME = os.getenv('YOUR_USERNAME')
    UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL')
    
    missing_vars = []
    if not TOKEN:
        missing_vars.append('BOT_TOKEN')
    if not OWNER_ID_STR:
        missing_vars.append('OWNER_ID')
    if not ADMIN_ID_STR:
        missing_vars.append('ADMIN_ID')
    
    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logging.error(error_msg)
        print(f"\n❌ {error_msg}")
        print("Please set these variables in your .env file or environment variables.")
        print("Example .env file:")
        print("BOT_TOKEN=your_bot_token_here")
        print("OWNER_ID=your_owner_id_here")
        print("ADMIN_ID=your_admin_id_here")
        print("YOUR_USERNAME=@your_username")
        print("UPDATE_CHANNEL=https://t.me/YourChannel")
        sys.exit(1)
    
    try:
        OWNER_ID = int(OWNER_ID_STR)
        ADMIN_ID = int(ADMIN_ID_STR)
    except ValueError as e:
        error_msg = f"OWNER_ID and ADMIN_ID must be valid integers: {e}"
        logging.error(error_msg)
        print(f"\n❌ {error_msg}")
        sys.exit(1)
    
    YOUR_USERNAME = YOUR_USERNAME or '@NASA_LEADER1'
    if not YOUR_USERNAME.startswith('@'):
        YOUR_USERNAME = '@' + YOUR_USERNAME
    
    UPDATE_CHANNEL = UPDATE_CHANNEL or 'https://t.me/YourChannel'
    
    return {
        'TOKEN': TOKEN,
        'OWNER_ID': OWNER_ID,
        'ADMIN_ID': ADMIN_ID,
        'YOUR_USERNAME': YOUR_USERNAME,
        'UPDATE_CHANNEL': UPDATE_CHANNEL
    }

# Initialize environment variables
env_vars = load_environment_variables()
TOKEN = env_vars['TOKEN']
OWNER_ID = env_vars['OWNER_ID']
ADMIN_ID = env_vars['ADMIN_ID']
YOUR_USERNAME = env_vars['YOUR_USERNAME']
UPDATE_CHANNEL = env_vars['UPDATE_CHANNEL']

# AI Engine Credentials (OpenRouter config)
AI_API_KEY = os.getenv('OPENROUTER_API_KEY', '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')
AI_MODEL = os.getenv('OPENROUTER_MODEL', 'openai/gpt-oss-120b:free')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.absolute()
UPLOAD_BOTS_DIR = BASE_DIR / 'upload_bots'
IROTECH_DIR = BASE_DIR / 'inf'
DATABASE_PATH = IROTECH_DIR / 'bot_data.db'

FREE_USER_LIMIT = 1
SUBSCRIBED_USER_LIMIT = 80
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

# Create all necessary directories
UPLOAD_BOTS_DIR.mkdir(exist_ok=True)
IROTECH_DIR.mkdir(exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Global tracking variables
bot_scripts = {}
user_subscriptions = {}
user_files = {}
user_projects = {}  # Solved missing global declaration bug
user_favorites = {}
banned_users = set()
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
bot_stats = {'total_uploads': 0, 'total_downloads': 0, 'total_runs': 0}

running_processes = {}
user_processes = {}  # Track processes per user

# ============= AI DEVOPS UTILITIES =============

async def ask_ai(prompt: str) -> str:
    """Call OpenRouter API with headers and failover mechanism to guarantee 100% uptime."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/nasa-leader1/jabir-hosting",
        "X-Title": "Jabir AI Hosting DevOps"
    }
    
    # Payload for primary model
    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system", 
                "content": "You are the advanced AI DevOps Engine for Jabir Hosting Bot. You analyze uploaded Python projects, figure out nested architectures, resolve paths, find entrypoints, analyze error logs/tracebacks, and write direct step-by-step instructions and code fixes in Persian."
            },
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            logger.info(f"Attempting AI request with model: {AI_MODEL}")
            async with session.post(url, headers=headers, json=payload, timeout=40) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                else:
                    logger.warning(f"Primary model {AI_MODEL} failed (status {response.status}). Trying fallback...")
    except Exception as e:
        logger.warning(f"Primary model connection failed: {e}. Trying fallback...")
        
    # Fallback to the general free router path which is highly reliable
    fallback_model = "openrouter/free"
    payload["model"] = fallback_model
    try:
        async with aiohttp.ClientSession() as session:
            logger.info(f"Attempting AI request with fallback model: {fallback_model}")
            async with session.post(url, headers=headers, json=payload, timeout=40) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                else:
                    err_text = await response.text()
                    logger.error(f"Fallback model failed: {response.status} - {err_text}")
                    return f"❌ خطایی در موتور پردازش هوش مصنوعی (کد {response.status}) رخ داده است. لطفاً چند لحظه دیگر امتحان کنید."
    except Exception as e:
        logger.error(f"AI Fallback connection failed: {e}")
        return f"❌ خطا در برقراری ارتباط با شبکه هوش مصنوعی: {str(e)}"

def get_project_structure_text(project_path: Path, max_depth=3) -> str:
    """Recursively list directory structures for the AI context."""
    structure = []
    project_path = Path(project_path)
    for root, dirs, files in os.walk(project_path):
        depth = len(Path(root).relative_to(project_path).parts)
        if depth > max_depth:
            continue
        indent = "  " * depth
        folder_name = os.path.basename(root) or project_path.name
        structure.append(f"{indent}📁 {folder_name}/")
        for f in files:
            if not f.endswith(('.pyc', '.git', '.log', '.zip')):
                structure.append(f"{indent}  📄 {f}")
    return "\n".join(structure)[:1200]  # Hard limit size

def get_key_file_contents(project_path: Path) -> str:
    """Fetch sample code block contents for AI diagnostic precision."""
    project_path = Path(project_path)
    contents = []
    
    # Check requirements
    req_file = project_path / "requirements.txt"
    if req_file.exists():
        try:
            with open(req_file, 'r', encoding='utf-8') as f:
                contents.append(f"--- requirements.txt ---\n{f.read()[:500]}")
        except:
            pass
            
    # Find potential main files and preview them
    main_files = ['main.py', 'app.py', 'bot.py', 'run.py', 'index.py']
    for mf in main_files:
        file_path = project_path / mf
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    contents.append(f"--- {mf} (First 100 lines) ---\n" + "".join(f.readlines()[:100]))
                    break
            except:
                pass
    return "\n\n".join(contents)[:1500]  # Hard limit size

# ============= USER & DB UTILITIES =============

def register_active_user(user_id):
    """Ensure user exists and active status is logged into SQL database for the admin panel."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute('INSERT OR IGNORE INTO active_users (user_id, join_date, last_active) VALUES (?, ?, ?)', (user_id, now, now))
        c.execute('UPDATE active_users SET last_active = ? WHERE user_id = ?', (now, user_id))
        conn.commit()
        conn.close()
        active_users.add(user_id)
    except Exception as e:
        logger.error(f"Error registering user {user_id}: {e}")

# ============= DATABASE OPERATIONS =============

def migrate_db():
    logger.info("Running database migrations...")
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        # Migrations for user_files
        c.execute("PRAGMA table_info(user_files)")
        columns = [row[1] for row in c.fetchall()]
        if 'upload_date' not in columns:
            logger.info("Adding upload_date column to user_files table...")
            c.execute('ALTER TABLE user_files ADD COLUMN upload_date TEXT')
            logger.info("upload_date column added successfully.")
        
        # Migrations for user_projects (Fixes the admin User Projects loading issue)
        c.execute("PRAGMA table_info(user_projects)")
        columns_proj = [row[1] for row in c.fetchall()]
        if 'upload_date' not in columns_proj:
            logger.info("Adding upload_date column to user_projects table...")
            c.execute('ALTER TABLE user_projects ADD COLUMN upload_date TEXT')
            logger.info("upload_date column added to user_projects successfully.")
        
        # Migrations for active_users
        c.execute("PRAGMA table_info(active_users)")
        columns_active = [row[1] for row in c.fetchall()]
        if 'join_date' not in columns_active:
            logger.info("Adding join_date column to active_users table...")
            c.execute('ALTER TABLE active_users ADD COLUMN join_date TEXT')
            logger.info("join_date column added successfully.")
        if 'last_active' not in columns_active:
            logger.info("Adding last_active column to active_users table...")
            c.execute('ALTER TABLE active_users ADD COLUMN last_active TEXT')
            logger.info("last_active column added successfully.")
        
        conn.commit()
        conn.close()
        logger.info("Database migrations completed successfully.")
        return True
    except Exception as e:
        logger.error(f"Database migration error: {e}")
        return False

def init_db():
    logger.info("Initializing database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_path TEXT, file_size INTEGER, upload_date TEXT, PRIMARY KEY (user_id, file_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_projects
                     (user_id INTEGER, project_name TEXT, project_path TEXT, venv_path TEXT, main_file TEXT, requirements_installed BOOLEAN, upload_date TEXT, PRIMARY KEY (user_id, project_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY, join_date TEXT, last_active TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users
                     (user_id INTEGER PRIMARY KEY, banned_date TEXT, reason TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS favorites
                     (user_id INTEGER, project_name TEXT, PRIMARY KEY (user_id, project_name))''')
        c.execute('''CREATE TABLE IF NOT EXISTS bot_stats
                     (stat_name TEXT PRIMARY KEY, stat_value INTEGER)''')
        
        c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (ADMIN_ID,))
        
        for stat in ['total_uploads', 'total_downloads', 'total_runs']:
            c.execute('INSERT OR IGNORE INTO bot_stats (stat_name, stat_value) VALUES (?, 0)', (stat,))
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
        return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False

def load_data():
    logger.info("Loading data from database...")
    try:
        global user_projects, user_files, user_subscriptions, active_users, admin_ids, banned_users, bot_stats
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        c.execute('SELECT user_id, expiry FROM subscriptions')
        for user_id, expiry in c.fetchall():
            try:
                user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
            except ValueError:
                logger.warning(f"Invalid expiry date for user {user_id}")
        
        c.execute('SELECT user_id, file_name, file_path, file_size FROM user_files')
        for user_id, file_name, file_path, file_size in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = {}
            user_files[user_id][file_name] = {'path': file_path, 'size': file_size}
        
        c.execute('SELECT user_id, project_name, project_path, venv_path, main_file, requirements_installed FROM user_projects')
        for user_id, project_name, project_path, venv_path, main_file, requirements_installed in c.fetchall():
            if user_id not in user_projects:
                user_projects[user_id] = {}
            user_projects[user_id][project_name] = {
                'project_path': project_path,
                'venv_path': venv_path,
                'main_file': main_file,
                'requirements_installed': bool(requirements_installed)
            }
        
        c.execute('SELECT user_id FROM active_users')
        active_users.update(user_id for (user_id,) in c.fetchall())
        
        c.execute('SELECT user_id FROM admins')
        admin_ids.update(user_id for (user_id,) in c.fetchall())
        
        c.execute('SELECT user_id FROM banned_users')
        banned_users.update(user_id for (user_id,) in c.fetchall())
        
        c.execute('SELECT user_id, project_name FROM favorites')
        for user_id, project_name in c.fetchall():
            if user_id not in user_favorites:
                user_favorites[user_id] = []
            user_favorites[user_id].append(project_name)
        
        c.execute('SELECT stat_name, stat_value FROM bot_stats')
        for stat_name, stat_value in c.fetchall():
            bot_stats[stat_name] = stat_value
        
        conn.close()
        logger.info(f"Data loaded: {len(active_users)} users, {len(banned_users)} banned, {len(admin_ids)} admins.")
        return True
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return False

def save_project_to_db(user_id, project_name, project_info):
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute('INSERT OR REPLACE INTO user_projects (user_id, project_name, project_path, venv_path, main_file, requirements_installed, upload_date) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (user_id, project_name, project_info['project_path'], project_info.get('venv_path'), 
                   project_info.get('main_file'), project_info.get('requirements_installed', False), now))
        c.execute('UPDATE bot_stats SET stat_value = stat_value + 1 WHERE stat_name = ?', ('total_uploads',))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error saving project to database: {e}")
        return False

def get_user_project_limit(user_id):
    if user_id == OWNER_ID: return OWNER_LIMIT
    if user_id in admin_ids: return ADMIN_LIMIT
    if user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now():
        return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT

def get_main_keyboard(user_id):
    if user_id in admin_ids:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Updates", url=UPDATE_CHANNEL)],
            [InlineKeyboardButton(text="📤 Upload Project", callback_data="upload_project"),
             InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects")],
            [InlineKeyboardButton(text="⭐ Favorites", callback_data="my_favorites"),
             InlineKeyboardButton(text="🔍 Search Projects", callback_data="search_projects")],
            [InlineKeyboardButton(text="⚡ Bot Speed", callback_data="bot_speed"),
             InlineKeyboardButton(text="📊 My Stats", callback_data="statistics")],
            [InlineKeyboardButton(text="ℹ️ Help & Info", callback_data="help_info"),
             InlineKeyboardButton(text="🎯 Features", callback_data="all_features")],
            [InlineKeyboardButton(text="👨‍💼 Admin Panel", callback_data="admin_panel"),
             InlineKeyboardButton(text="💬 Contact", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}")]
        ])
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Updates Channel", url=UPDATE_CHANNEL)],
            [InlineKeyboardButton(text="📤 Upload Project", callback_data="upload_project"),
             InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects")],
            [InlineKeyboardButton(text="⭐ Favorites", callback_data="my_favorites"),
             InlineKeyboardButton(text="🔍 Search Projects", callback_data="search_projects")],
            [InlineKeyboardButton(text="⚡ Bot Speed", callback_data="bot_speed"),
             InlineKeyboardButton(text="📊 My Stats", callback_data="statistics")],
            [InlineKeyboardButton(text="💎 Get Premium", callback_data="get_premium"),
             InlineKeyboardButton(text="ℹ️ Help", callback_data="help_info")],
            [InlineKeyboardButton(text="🎯 Features", callback_data="all_features"),
             InlineKeyboardButton(text="💬 Contact Owner", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}")]
        ])
    return keyboard

def create_user_venv(user_id, project_name):
    """Create virtual environment for user project with enhanced error handling"""
    try:
        venv_path = UPLOAD_BOTS_DIR / f"user_{user_id}_{project_name}_venv"
        if venv_path.exists():
            logger.info(f"Venv already exists for user {user_id}, project {project_name}")
            return str(venv_path)
        
        logger.info(f"Creating venv for user {user_id}, project {project_name}")
        venv.create(venv_path, with_pip=True, system_site_packages=True)
        
        if os.name == 'nt':  # Windows
            pip_path = venv_path / "Scripts" / "pip.exe"
        else:  # Unix/Linux
            pip_path = venv_path / "bin" / "pip"
        
        logger.info(f"Upgrading pip for user {user_id}")
        upgrade_result = subprocess.run(
            [str(pip_path), "install", "--upgrade", "pip"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        logger.info(f"Pip upgrade output: {upgrade_result.stdout}")
        
        essential_packages = ["wheel", "setuptools"]
        for package in essential_packages:
            subprocess.run(
                [str(pip_path), "install", package],
                check=True,
                capture_output=True,
                text=True,
                timeout=60
            )
            logger.info(f"Installed {package} in venv")
        
        bot_stats['total_runs'] = bot_stats.get('total_runs', 0) + 1
        logger.info(f"Venv created successfully for user {user_id}")
        return str(venv_path)
        
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout creating venv for user {user_id}")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed creating venv for user {user_id}: {e}")
        logger.error(f"STDERR: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Error creating venv for user {user_id}: {e}")
        return None

def get_venv_python_path(venv_path):
    if os.name == 'nt':  # Windows
        return str(Path(venv_path) / "Scripts" / "python.exe")
    else:  # Unix/Linux
        return str(Path(venv_path) / "bin" / "python")

def get_venv_pip_path(venv_path):
    if os.name == 'nt':  # Windows
        return str(Path(venv_path) / "Scripts" / "pip.exe")
    else:  # Unix/Linux
        return str(Path(venv_path) / "bin" / "pip")

def install_requirements(venv_path, requirements_path):
    try:
        pip_path = get_venv_pip_path(venv_path)
        requirements_file = Path(requirements_path)
        if not requirements_file.exists():
            return False, "requirements.txt not found"
        
        logger.info(f"Installing requirements from {requirements_path}")
        with open(requirements_file, 'r') as f:
            requirements_content = f.read().strip()
            if not requirements_content:
                return False, "requirements.txt is empty"
        
        result = subprocess.run(
            [str(pip_path), "install", "-r", str(requirements_file)],
            capture_output=True,
            text=True,
            timeout=600
        )
        
        if result.returncode == 0:
            logger.info(f"Requirements installed successfully: {result.stdout}")
            return True, "Requirements installed successfully"
        else:
            error_msg = f"Installation failed: {result.stderr}"
            logger.error(error_msg)
            
            logger.info("Trying to install with --no-deps flag")
            no_deps_result = subprocess.run(
                [str(pip_path), "install", "--no-deps", "-r", str(requirements_file)],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if no_deps_result.returncode == 0:
                logger.info(f"Requirements installed with --no-deps: {no_deps_result.stdout}")
                return True, "Requirements installed (some dependencies may be missing)"
            else:
                logger.error(f"No-deps install failed: {no_deps_result.stderr}")
                return False, f"Installation failed even with --no-deps: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "Installation timed out (10 minutes)"
    except Exception as e:
        return False, f"Error installing requirements: {str(e)}"

# ============= RESOLVED NESTED FILE DETECTOR =============

def find_main_file(project_dir):
    """Intelligently detects nested entrypoints while bypassing non-runnable files and virtual environments."""
    project_path = Path(project_dir)
    main_filenames = ['main.py', 'bot.py', 'app.py', 'run.py', 'start.py', 'index.py']
    
    # 1. First, search at the root level directory (highest priority)
    for name in main_filenames:
        p = project_path / name
        if p.exists() and p.is_file():
            return str(p)
            
    # 2. Search recursively, excluding environments and temporary caches
    all_py_files = list(project_path.rglob("*.py"))
    clean_py_files = []
    
    for p in all_py_files:
        parts = p.parts
        # Filter out venv, virtual env folders, node_modules, and caching paths
        if any(x in [".venv", "venv", "env", "site-packages", "__pycache__", "node_modules"] for x in parts):
            continue
        clean_py_files.append(p)
        
    # Search for prioritized names in clean recursive path list
    for name in main_filenames:
        for p in clean_py_files:
            if p.name == name:
                return str(p)
                
    # 3. Fallback: select first python file that is not config/setting related
    for p in clean_py_files:
        if p.name not in ['config.py', 'settings.py', 'setup.py', '__init__.py']:
            return str(p)
            
    # Final fallback
    if clean_py_files:
        return str(clean_py_files[0])
        
    return None

def setup_environment_variables(project_dir):
    env_file = Path(project_dir) / ".env"
    if env_file.exists():
        try:
            load_dotenv(env_file)
            with open(env_file, 'r') as f:
                env_lines = f.readlines()
                loaded_vars = [line.split('=')[0].strip() for line in env_lines if '=' in line and not line.strip().startswith('#')]
            logger.info(f"Loaded environment variables from {env_file}: {loaded_vars}")
            return True
        except Exception as e:
            logger.error(f"Error loading .env file from {env_file}: {e}")
            return False
    return False

# ============= COMPLETE RESOURCE CLEANUP SYSTEM =============

async def delete_project_completely(user_id, project_name):
    """Completely terminates running instances and wipes directory/venv/db records to release CPU and RAM."""
    script_key = f"{user_id}_{project_name}"
    
    # 1. Terminate running instance if any
    if script_key in bot_scripts:
        try:
            script_info = bot_scripts[script_key]
            process = script_info['process']
            process.terminate()
            await asyncio.sleep(1)
            if process.poll() is None:
                process.kill()
            if 'log_file' in script_info:
                script_info['log_file'].close()
            del bot_scripts[script_key]
            logger.info(f"Successfully terminated running process for {script_key}")
        except Exception as e:
            logger.error(f"Error terminating process on deletion: {e}")

    # 2. Safely wipe associated Virtual Environment to free Disk Space
    venv_path = UPLOAD_BOTS_DIR / f"user_{user_id}_{project_name}_venv"
    if venv_path.exists():
        try:
            shutil.rmtree(venv_path)
            logger.info(f"Wiped Venv directory: {venv_path}")
        except Exception as e:
            logger.error(f"Error deleting venv tree: {e}")

    # 3. Delete Project folder directory
    project_info = user_files.get(user_id, {}).get(project_name)
    if project_info:
        project_path = Path(project_info['path'])
        if project_path.exists():
            try:
                shutil.rmtree(project_path)
                logger.info(f"Wiped project folder: {project_path}")
            except Exception as e:
                logger.error(f"Error deleting project tree: {e}")

    # 4. Remove entries from database tables
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM user_files WHERE user_id = ? AND file_name = ?", (user_id, project_name))
        c.execute("DELETE FROM user_projects WHERE user_id = ? AND project_name = ?", (user_id, project_name))
        c.execute("DELETE FROM favorites WHERE user_id = ? AND project_name = ?", (user_id, project_name))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error executing DB cleanup: {e}")

    # 5. Clear in-memory dictionaries
    if user_id in user_files and project_name in user_files[user_id]:
        del user_files[user_id][project_name]
    if user_id in user_projects and project_name in user_projects[user_id]:
        del user_projects[user_id][project_name]
    if user_id in user_favorites and project_name in user_favorites[user_id]:
        user_favorites[user_id].remove(project_name)

# ============= ADMIN PANEL HANDLERS =============

def get_admin_keyboard():
    """Get completely aligned, bug-free admin panel keyboard"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Users List", callback_data="admin_users"),
         InlineKeyboardButton(text="📁 User Projects", callback_data="admin_projects")],
        [InlineKeyboardButton(text="⬇️ Download Projects", callback_data="admin_download"),
         InlineKeyboardButton(text="⭐ Premium Management", callback_data="admin_premium")],
        [InlineKeyboardButton(text="🚫 Ban Management", callback_data="admin_ban"),
         InlineKeyboardButton(text="📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🏃 Running Processes", callback_data="admin_running")],
        [InlineKeyboardButton(text="💎 Premium Users", callback_data="admin_premium_list"),
         InlineKeyboardButton(text="🆓 Free Users", callback_data="admin_free_list")],
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")]
    ])
    return keyboard

async def get_users_list():
    """Get formatted list of all users from sqlite table"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT a.user_id, a.join_date, a.last_active,
                   CASE WHEN s.user_id IS NOT NULL THEN 'Premium' ELSE 'Free' END as user_type,
                   CASE WHEN s.user_id IS NOT NULL THEN s.expiry ELSE NULL END as expiry
            FROM active_users a
            LEFT JOIN subscriptions s ON a.user_id = s.user_id
            ORDER BY a.join_date DESC
        ''')
        users = c.fetchall()
        conn.close()
        
        if not users:
            return "No users found in the database."
        
        text = "📋 **All Users List:**\n\n"
        for user_id, join_date, last_active, user_type, expiry in users:
            status_emoji = "⭐" if user_type == "Premium" else "🆓"
            text += f"{status_emoji} **ID:** `{user_id}`\n"
            text += f"   📅 **Joined:** {join_date[:10] if join_date else 'Unknown'}\n"
            text += f"   🕐 **Last Active:** {last_active[:10] if last_active else 'Unknown'}\n"
            if expiry:
                text += f"   ⏰ **Expires:** {expiry[:10]}\n"
            text += "\n"
        
        return text
    except Exception as e:
        logger.error(f"Error getting users list: {e}")
        return f"❌ Error getting users list: {str(e)}"

async def get_user_projects_list():
    """Get all user hosted projects from the synced database"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT up.user_id, up.project_name, up.upload_date, up.project_path,
                   CASE WHEN s.user_id IS NOT NULL THEN 'Premium' ELSE 'Free' END as user_type
            FROM user_projects up
            LEFT JOIN active_users a ON up.user_id = a.user_id
            LEFT JOIN subscriptions s ON up.user_id = s.user_id
            ORDER BY up.upload_date DESC
            LIMIT 50
        ''')
        projects = c.fetchall()
        conn.close()
        
        if not projects:
            return "No projects found in the database."
        
        text = "📁 **All User Projects:**\n\n"
        for user_id, project_name, upload_date, project_path, user_type in projects:
            status_emoji = "⭐" if user_type == "Premium" else "🆓"
            text += f"{status_emoji} **User:** `{user_id}`\n"
            text += f"   📦 **Project:** {project_name}\n"
            text += f"   📅 **Uploaded:** {upload_date[:10] if upload_date else 'Unknown'}\n"
            text += f"   📂 **Path:** `{project_path}`\n\n"
        
        return text
    except Exception as e:
        logger.error(f"Error getting user projects: {e}")
        return f"❌ Error getting user projects: {str(e)}"

async def get_running_processes():
    if not running_processes:
        return "🏃 **No processes currently running**\n\n"
    
    text = "🏃 **Currently Running Processes:**\n\n"
    for process_id, process_info in running_processes.items():
        text += f"🔹 **Process ID:** `{process_id}`\n"
        text += f"   👤 **User:** `{process_info.get('user_id', 'Unknown')}`\n"
        text += f"   📦 **Project:** {process_info.get('project_name', 'Unknown')}\n"
        text += f"   ⏱️ **Started:** {process_info.get('start_time', 'Unknown')}\n"
        text += f"   📊 **Status:** {process_info.get('status', 'Unknown')}\n\n"
    
    return text

async def get_premium_users():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT s.user_id, s.expiry, a.join_date, a.last_active
            FROM subscriptions s
            JOIN active_users a ON s.user_id = a.user_id
            WHERE s.expiry > datetime('now')
            ORDER BY s.expiry DESC
        ''')
        premium_users = c.fetchall()
        conn.close()
        
        if not premium_users:
            return "⭐ **No active premium users found**\n\n"
        
        text = "⭐ **Premium Users List:**\n\n"
        for user_id, expiry, join_date, last_active in premium_users:
            text += f"⭐ **User ID:** `{user_id}`\n"
            text += f"   ⏰ **Expires:** {expiry[:19]}\n"
            text += f"   📅 **Joined:** {join_date[:10] if join_date else 'Unknown'}\n"
            text += f"   🕐 **Last Active:** {last_active[:10] if last_active else 'Unknown'}\n\n"
        
        return text
    except Exception as e:
        logger.error(f"Error getting premium users: {e}")
        return f"❌ Error getting premium users: {str(e)}"

async def get_free_users():
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''
            SELECT a.user_id, a.join_date, a.last_active
            FROM active_users a
            LEFT JOIN subscriptions s ON a.user_id = s.user_id
            WHERE s.user_id IS NULL OR s.expiry <= datetime('now')
            ORDER BY a.join_date DESC
            LIMIT 50
        ''')
        free_users = c.fetchall()
        conn.close()
        
        if not free_users:
            return "🆓 **No free users found**\n\n"
        
        text = "🆓 **Free Users List:**\n\n"
        for user_id, join_date, last_active in free_users:
            text += f"🆓 **User ID:** `{user_id}`\n"
            text += f"   📅 **Joined:** {join_date[:10] if join_date else 'Unknown'}\n"
            text += f"   🕐 **Last Active:** {last_active[:10] if last_active else 'Unknown'}\n\n"
        
        return text
    except Exception as e:
        logger.error(f"Error getting free users: {e}")
        return f"❌ Error getting free users: {str(e)}"

# Consolidated working single admin_panel query callback
@dp.callback_query(F.data == "admin_panel")
async def callback_admin_panel(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM active_users")
        total_users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM user_projects")
        total_projects = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM subscriptions WHERE expiry > datetime('now')")
        total_premium = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM banned_users")
        total_banned = c.fetchone()[0]
        conn.close()
    except Exception as e:
        logger.error(f"Admin stats fetching failed: {e}")
        total_users = len(active_users)
        total_projects = sum(len(projects) for projects in user_files.values())
        total_premium = len([uid for uid in user_subscriptions if user_subscriptions[uid]['expiry'] > datetime.now()])
        total_banned = len(banned_users)

    text = f"""🛡️ **ADMIN CONTROL PANEL** 🛡️
    
Welcome to the Admin Control Panel!
Manage bot resources and users below.

📊 **Bot Statistics:**
• Total Registered Users: {total_users}
• Total Hosted Projects: {total_projects}
• Premium Subscribers: {total_premium}
• Banned Users: {total_banned}
• Active In-Memory Sessions: {len(active_users)}

Choose an option below 👇"""
    
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_users")
async def callback_admin_users(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    users_text = await get_users_list()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_users")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(users_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_projects")
async def callback_admin_projects(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    projects_text = await get_user_projects_list()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_projects")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(projects_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_running")
async def callback_admin_running(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    running_text = await get_running_processes()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_running")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(running_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_premium_list")
async def callback_admin_premium_list(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    premium_text = await get_premium_users()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_premium_list")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(premium_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_free_list")
async def callback_admin_free_list(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    free_text = await get_free_users()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_free_list")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(free_text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_premium")
async def callback_admin_premium(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    text = """⭐ **Premium Management** ⭐

Choose an action:

➕ **Add Premium:** Give premium access to a user
➖ **Remove Premium:** Remove premium access from a user

Please use the command format:
• `/addpremium <user_id> <days>` - Add premium for X days
• `/removepremium <user_id>` - Remove premium from user

Example: `/addpremium 123456789 30`"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_premium")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_ban")
async def callback_admin_ban(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    text = """🚫 **Ban Management** 🚫

Choose an action:

🚫 **Ban User:** Ban a user from using the bot
✅ **Unban User:** Remove ban from a user

Please use the command format:
• `/ban <user_id> <reason>` - Ban user with reason
• `/unban <user_id>` - Unban user

Example: `/ban 123456789 Spamming`"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_ban")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def callback_admin_broadcast(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    text = """📢 **Broadcast Message** 📢

Send a message to all users:

Please use the command format:
`/broadcast <message>`

Example: `/broadcast Bot maintenance scheduled for tonight!`

⚠️ **Note:** This will send the message to all active users."""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "admin_download")
async def callback_admin_download(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await callback.answer("❌ Access denied!", show_alert=True)
        return
    
    text = """⬇️ **Download User Projects** ⬇️

Download projects from any user:

Please use the command format:
• `/download <user_id> <project_name>` - Download specific project
• `/downloadall <user_id>` - Download all projects from user

Example: `/download 123456789 mybot`"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_download")],
        [InlineKeyboardButton(text="🔙 Admin Panel", callback_data="admin_panel")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    await callback.answer()

# Admin Command Handlers
@dp.message(Command("addpremium"))
async def cmd_addpremium(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await message.answer("❌ Access denied!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("Usage: `/addpremium <user_id> <days>`")
            return
        
        target_user_id = int(parts[1])
        days = int(parts[2])
        
        expiry_date = datetime.now() + timedelta(days=days)
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)',
                     (target_user_id, expiry_date.isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            await message.answer(f"❌ Database error: {e}")
            return
        
        user_subscriptions[target_user_id] = {'expiry': expiry_date}
        await message.answer(f"✅ Premium access granted to user `{target_user_id}` for {days} days!", parse_mode="Markdown")
        
        try:
            await bot.send_message(target_user_id, f"⭐ **Congratulations!**\n\nYou've been granted premium access for {days} days!\n\nEnjoy unlimited projects and premium features!")
        except:
            pass
            
    except ValueError:
        await message.answer("❌ Invalid user_id or days. Please provide valid numbers.")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("removepremium"))
async def cmd_removepremium(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await message.answer("❌ Access denied!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: `/removepremium <user_id>`")
            return
        
        target_user_id = int(parts[1])
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('DELETE FROM subscriptions WHERE user_id = ?', (target_user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            await message.answer(f"❌ Database error: {e}")
            return
        
        if target_user_id in user_subscriptions:
            del user_subscriptions[target_user_id]
        
        await message.answer(f"✅ Premium access removed from user `{target_user_id}`", parse_mode="Markdown")
        
        try:
            await bot.send_message(target_user_id, "ℹ️ Your premium access has been removed. You can still use the bot with free limits.")
        except:
            pass
            
    except ValueError:
        await message.answer("❌ Invalid user_id. Please provide a valid number.")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await message.answer("❌ Access denied!")
        return
    
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2:
            await message.answer("Usage: `/ban <user_id> [reason]`")
            return
        
        target_user_id = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "No reason provided"
        
        banned_users.add(target_user_id)
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO banned_users (user_id, banned_date, reason) VALUES (?, ?, ?)',
                     (target_user_id, datetime.now().isoformat(), reason))
            conn.commit()
            conn.close()
        except Exception as e:
            await message.answer(f"❌ Database error: {e}")
            return
        
        await message.answer(f"✅ User `{target_user_id}` has been banned!\nReason: {reason}", parse_mode="Markdown")
        
        try:
            await bot.send_message(target_user_id, f"🚫 You have been banned from using this bot.\nReason: {reason}")
        except:
            pass
            
    except ValueError:
        await message.answer("❌ Invalid user_id. Please provide a valid number.")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("unban"))
async def cmd_unban(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await message.answer("❌ Access denied!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: `/unban <user_id>`")
            return
        
        target_user_id = int(parts[1])
        banned_users.discard(target_user_id)
        
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            c.execute('DELETE FROM banned_users WHERE user_id = ?', (target_user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            await message.answer(f"❌ Database error: {e}")
            return
        
        await message.answer(f"✅ User `{target_user_id}` has been unbanned!", parse_mode="Markdown")
        
        try:
            await bot.send_message(target_user_id, "✅ You have been unbanned and can now use the bot again!")
        except:
            pass
            
    except ValueError:
        await message.answer("❌ Invalid user_id. Please provide a valid number.")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await message.answer("❌ Access denied!")
        return
    
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) != 2:
            await message.answer("Usage: `/broadcast <message>`")
            return
        
        broadcast_message = parts[1]
        sent_count = 0
        failed_count = 0
        
        status_msg = await message.answer("📢 Broadcasting message...")
        
        for target_user_id in active_users:
            try:
                await bot.send_message(target_user_id, f"📢 **Broadcast Message:**\n\n{broadcast_message}", parse_mode="Markdown")
                sent_count += 1
                await asyncio.sleep(0.1)
            except:
                failed_count += 1
        
        await status_msg.edit_text(f"✅ Broadcast completed!\n\n📊 **Statistics:**\n✅ Sent: {sent_count}\n❌ Failed: {failed_count}")
        
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("download"))
async def cmd_download(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await message.answer("❌ Access denied!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("Usage: `/download <user_id> <project_name>`")
            return
        
        target_user_id = int(parts[1])
        project_name = parts[2]
        
        if target_user_id not in user_files or project_name not in user_files[target_user_id]:
            await message.answer("❌ Project not found!")
            return
        
        project_path = user_files[target_user_id][project_name]['path']
        
        zip_path = UPLOAD_BOTS_DIR / f"admin_download_{target_user_id}_{project_name}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(project_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, project_path)
                    zipf.write(file_path, arcname)
        
        await message.answer_document(
            FSInputFile(zip_path, filename=f"{project_name}.zip"),
            caption=f"📁 **Project Download:**\n\n👤 **User ID:** `{target_user_id}`\n📦 **Project:** {project_name}\n📅 **Downloaded:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        zip_path.unlink()
        
    except ValueError:
        await message.answer("❌ Invalid user_id. Please provide a valid number.")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("downloadall"))
async def cmd_downloadall(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id not in admin_ids:
        await message.answer("❌ Access denied!")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("Usage: `/downloadall <user_id>`")
            return
        
        target_user_id = int(parts[1])
        
        if target_user_id not in user_files or not user_files[target_user_id]:
            await message.answer("❌ No projects found for this user!")
            return
        
        projects = user_files[target_user_id]
        
        zip_path = UPLOAD_BOTS_DIR / f"admin_download_all_{target_user_id}.zip"
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for project_name, project_info in projects.items():
                project_path = project_info['path']
                for root, dirs, files in os.walk(project_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join(project_name, os.path.relpath(file_path, project_path))
                        zipf.write(file_path, arcname)
        
        await message.answer_document(
            FSInputFile(zip_path, filename=f"all_projects_user_{target_user_id}.zip"),
            caption=f"📁 **All Projects Download:**\n\n👤 **User ID:** `{target_user_id}`\n📦 **Projects:** {len(projects)} projects\n📅 **Downloaded:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        zip_path.unlink()
        
    except ValueError:
        await message.answer("❌ Invalid user_id. Please provide a valid number.")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

# ============= MESSAGE HANDLERS =============

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id in banned_users:
        await message.answer("🚫 <b>You are banned from using this bot!</b>\n\nContact admin for more info.", parse_mode="HTML")
        return
    
    welcome_text = f"""    
    ╔═══════════════════════════════════╗
          🌟 <b>WELCOME TO JABIR HOSTING BOT</b> 🌟
    ╚═══════════════════════════════════╝
    
    👋 <b>Hi,</b> {message.from_user.full_name}!
    
    🆔 <b>Your ID:</b> <code>{user_id}</code>
    📦 <b>Project Limit:</b> {get_user_project_limit(user_id)} projects
    💎 <b>Account:</b> {'Premium ✨' if user_id in user_subscriptions else 'Free 🏃'}
    
    ════════════════════════════════════
    <b>🎯 ENHANCED FEATURES (with AI Diagnostic):</b>
    
    📤 <b>Upload ZIP Projects</b> - Complete projects with nested structures
    🤖 <b>AI Smart Troubleshooter</b> - Detect nested Entrypoints & fix code errors
    🛠 *Isolated Venv System* - Pure execution with auto pip dependencies
    🧰 <b>.env Support</b> - Automatically maps environment variables
    
    ════════════════════════════════════
    <b>🚀 Start building with smart hosting now! 🚀</b>
    """
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")

@dp.message(F.document)
async def handle_document(message: types.Message):
    user_id = message.from_user.id
    register_active_user(user_id)
    
    if user_id in banned_users:
        await message.answer("🚫 You are banned from using this bot!")
        return
    
    if bot_locked and user_id not in admin_ids:
        await message.answer("🔒 Bot is currently locked!")
        return
    
    document = message.document
    file_name = document.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext != '.zip':
        await message.answer("❌ Only ZIP project files are supported!")
        return
    
    current_projects = len(user_files.get(user_id, {}))
    limit = get_user_project_limit(user_id)
    
    if current_projects >= limit:
        await message.answer(f"❌ Project limit reached! ({current_projects}/{limit})\n\n💎 Upgrade to premium for more space!")
        return
    
    user_folder = UPLOAD_BOTS_DIR / str(user_id)
    user_folder.mkdir(exist_ok=True)
    
    project_name = os.path.splitext(file_name)[0]
    if project_name in user_files.get(user_id, {}):
        counter = 1
        while f"{project_name}_{counter}" in user_files.get(user_id, {}):
            counter += 1
        project_name = f"{project_name}_{counter}"
    
    project_path = user_folder / project_name
    zip_path = user_folder / file_name
    
    try:
        file_size_kb = document.file_size / 1024
        
        status_msg = await message.answer(
            f"📤 <b>Preparing upload...</b>\n\n"
            f"📦 Project: <code>{file_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"██████████ 0%",
            parse_mode="HTML"
        )
        
        await asyncio.sleep(0.3)
        await status_msg.edit_text(
            f"📥 <b>Downloading...</b>\n\n"
            f"📦 Project: <code>{file_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"██████████ 30%",
            parse_mode="HTML"
        )
        
        await bot.download(document, destination=zip_path)
        
        await status_msg.edit_text(
            f"📂 <b>Extracting project...</b>\n\n"
            f"📦 Project: <code>{file_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"██████████ 60%",
            parse_mode="HTML"
        )
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(project_path)
        
        await status_msg.edit_text(
            f"🔍 <b>Analyzing project...</b>\n\n"
            f"📦 Project: <code>{file_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"██████████ 90%",
            parse_mode="HTML"
        )
        
        main_file = find_main_file(project_path)
        if not main_file:
            await status_msg.edit_text("❌ No Python files found in the project!")
            zip_path.unlink()
            return
        
        env_loaded = setup_environment_variables(project_path)
        
        # Save project info to local dictionaries
        if user_id not in user_files:
            user_files[user_id] = {}
        user_files[user_id][project_name] = {
            'path': str(project_path),
            'size': document.file_size
        }
        
        if user_id not in user_projects:
            user_projects[user_id] = {}
        user_projects[user_id][project_name] = {
            'project_path': str(project_path),
            'venv_path': str(UPLOAD_BOTS_DIR / f"user_{user_id}_{project_name}_venv"),
            'main_file': main_file,
            'requirements_installed': False
        }
        
        # Save to SQLite database (Synchronize both user_files and user_projects)
        try:
            conn = sqlite3.connect(DATABASE_PATH)
            c = conn.cursor()
            now = datetime.now().isoformat()
            
            c.execute('INSERT OR REPLACE INTO user_files (user_id, file_name, file_path, file_size, upload_date) VALUES (?, ?, ?, ?, ?)',
                      (user_id, project_name, str(project_path), document.file_size, now))
                      
            c.execute('INSERT OR REPLACE INTO user_projects (user_id, project_name, project_path, venv_path, main_file, requirements_installed, upload_date) VALUES (?, ?, ?, ?, ?, ?, ?)',
                      (user_id, project_name, str(project_path), str(UPLOAD_BOTS_DIR / f"user_{user_id}_{project_name}_venv"), main_file, False, now))
                      
            c.execute('UPDATE bot_stats SET stat_value = stat_value + 1 WHERE stat_name = ?', ('total_uploads',))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Database sync error on upload: {e}")
        
        bot_stats['total_uploads'] = bot_stats.get('total_uploads', 0) + 1
        zip_path.unlink()
        
        await status_msg.edit_text(
            f"✅ <b>Finalizing...</b>\n\n"
            f"📦 Project: <code>{project_name}</code>\n"
            f"💾 Size: {file_size_kb:.2f} KB\n\n"
            f"██████████ 100%",
            parse_mode="HTML"
        )
        
        await asyncio.sleep(0.5)
        
        req_file = project_path / "requirements.txt"
        has_requirements = req_file.exists()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛠️ Create Venv", callback_data=f"create_venv:{project_name}")],
            [InlineKeyboardButton(text="📦 Install Requirements", callback_data=f"install_req:{project_name}") 
             if has_requirements else InlineKeyboardButton(text="📄 No requirements.txt", callback_data="req_info")],
            [InlineKeyboardButton(text="🤖 AI DevOps Assistant", callback_data=f"ai_diagnostic:{project_name}")],
            [InlineKeyboardButton(text="🚀 Run Project", callback_data=f"run_project:{project_name}")],
            [InlineKeyboardButton(text="⭐ Add Favorite", callback_data=f"toggle_fav:{project_name}")],
            [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects"),
             InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ])
        
        env_status = "✅ .env loaded" if env_loaded else "ℹ️ No .env file"
        
        await status_msg.edit_text(
            f"""    
    ╔═══════════════════════════════════╗
          ✅ <b>UPLOAD SUCCESS!</b> ✅
    ╚═══════════════════════════════════╝
    
    📦 <b>Project:</b> <code>{project_name}</code>
    🐍 <b>Main File:</b> <code>{os.path.basename(main_file)}</code>
    💾 <b>Size:</b> {document.file_size / 1024:.2f} KB
    📊 <b>Usage:</b> {current_projects + 1}/{limit}
    🧰 <b>.env:</b> {env_status}
    📦 <b>Requirements:</b> {'Found ✅' if has_requirements else 'Not found ❌'}
    
    🎉 Project uploaded and analyzed successfully!
    
    <b>Next Steps:</b>
    1️⃣ Create Virtual Environment
    2️⃣ Install Requirements (if available)
    3️⃣ Try AI Scan or Run Your Project!
    """,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error uploading project: {e}")
        await message.answer(f"❌ Upload failed: {str(e)}")

# ============= CALLBACK HANDLERS =============

@dp.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    welcome_text = f"""    
    ╔═══════════════════════════════════╗
          🏠 <b>MAIN MENU</b> 🏠
    ╚═══════════════════════════════════╝
    
    👤 <b>User:</b> {callback.from_user.full_name}
    🆔 <b>ID:</b> <code>{user_id}</code>
    📦 <b>Projects:</b> {len(user_files.get(user_id, {}))}/{get_user_project_limit(user_id)}
    
    Use buttons below to navigate 👇
    """
    await callback.message.edit_text(welcome_text, reply_markup=get_main_keyboard(user_id), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "upload_project")
async def callback_upload_project(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    if bot_locked and user_id not in admin_ids:
        await callback.answer("🔒 Bot is locked for maintenance!", show_alert=True)
        return
    
    current_projects = len(user_files.get(user_id, {}))
    limit = get_user_project_limit(user_id)
    
    upload_text = f"""    
    ╔═══════════════════════════════════╗
          📤 <b>UPLOAD PROJECTS</b> 📤
    ╚═══════════════════════════════════╝
    
    📊 <b>Current Usage:</b> {current_projects}/{limit} projects
    
    📝 <b>Supported Formats:</b>
    📦 ZIP Archives (.zip) - Complete projects
    
    ════════════════════════════════════
    <b>💡 How to Upload:</b>
    
    1️⃣ Send your ZIP project file
    2️⃣ Wait for extraction and analysis
    3️⃣ Project will be setup automatically
    4️⃣ Install requirements and run!
    
    ⚡ <b>Project limit:</b> {limit} projects
    🔥 <b>Smart & Automatic!</b>
    
    <b>🎯 Project Structure:</b>
    • main.py (or app.py, bot.py)
    • requirements.txt (auto-detected)
    • .env file (auto-loaded)
    • Other project files/folders
    """
    
    back_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(upload_text, reply_markup=back_keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("create_venv:"))
async def callback_create_venv(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    project_info = user_files.get(user_id, {}).get(project_name)
    if not project_info:
        await callback.answer("❌ Project not found!", show_alert=True)
        return
    
    try:
        await callback.message.edit_text(
            f"🛠️ <b>Creating Virtual Environment...</b>\n\n"
            f"📦 Project: <code>{project_name}</code>\n"
            f"⏳ Please wait, this may take a moment...",
            parse_mode="HTML"
        )
        
        venv_path = create_user_venv(user_id, project_name)
        
        if venv_path:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 Install Requirements", callback_data=f"install_req:{project_name}")],
                [InlineKeyboardButton(text="🚀 Run Project", callback_data=f"run_project:{project_name}")],
                [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects"),
                 InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
            ])
            
            await callback.message.edit_text(
                f"""    
    ╔═══════════════════════════════════╗
          ✅ <b>VENV CREATED!</b> ✅
    ╚═══════════════════════════════════╝
    
    🛠️ <b>Virtual Environment:</b> Ready ✅
    📦 <b>Project:</b> <code>{project_name}</code>
    🐍 <b>Python:</b> Isolated environment
    📦 <b>Pip:</b> Ready to install packages
    
    <b>Next Steps:</b>
    📦 Install requirements
    🚀 Run your project
    """,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer("✅ Virtual environment created successfully!")
        else:
            await callback.answer("❌ Failed to create virtual environment!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error creating venv: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("install_req:"))
async def callback_install_requirements(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    project_info = user_files.get(user_id, {}).get(project_name)
    if not project_info:
        await callback.answer("❌ Project not found!", show_alert=True)
        return
    
    venv_path = UPLOAD_BOTS_DIR / f"user_{user_id}_{project_name}_venv"
    if not venv_path.exists():
        await callback.answer("❌ Please create virtual environment first!", show_alert=True)
        return
    
    project_path = Path(project_info['path'])
    requirements_file = project_path / "requirements.txt"
    
    if not requirements_file.exists():
        await callback.answer("❌ requirements.txt not found!", show_alert=True)
        return
    
    try:
        await callback.message.edit_text(
            f"📦 <b>Installing Requirements...</b>\n\n"
            f"📦 Project: <code>{project_name}</code>\n"
            f"📄 Requirements.txt: Found\n"
            f"⏳ Installing packages...",
            parse_mode="HTML"
        )
        
        success, message = install_requirements(str(venv_path), str(requirements_file))
        
        if success:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Run Project", callback_data=f"run_project:{project_name}")],
                [InlineKeyboardButton(text="📋 View Logs", callback_data=f"view_logs:{project_name}")],
                [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects"),
                 InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
            ])
            
            await callback.message.edit_text(
                f"""    
    ╔═══════════════════════════════════╗
          ✅ <b>REQUIREMENTS INSTALLED!</b> ✅
    ╚═══════════════════════════════════╝
    
    📦 <b>Requirements:</b> Installed successfully ✅
    📦 Project: <code>{project_name}</code>
    🐍 <b>Packages:</b> Ready to use
    🚀 <b>Status:</b> Ready to run!
    
    <b>Your project is now ready to run!</b> 🎉
    """,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer("✅ Requirements installed successfully!")
        else:
            await callback.answer(f"❌ Installation failed: {message}", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error installing requirements: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

# ============= AI DIAGNOSTICS HANDLER =============

@dp.callback_query(F.data.startswith("ai_diagnostic:"))
async def callback_ai_diagnostic(callback: types.CallbackQuery):
    """Scan and diagnose project details or debug structural anomalies using the OpenAI gpt-oss model."""
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    project_info = user_files.get(user_id, {}).get(project_name)
    if not project_info:
        await callback.answer("❌ Project not found!", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"🤖 <b>AI DevOps Cloud Engine is scanning your project...</b>\n\n"
        f"📦 Project: <code>{project_name}</code>\n"
        f"🔍 Reading structure tree, configuration dependencies, and paths...\n"
        f"⏳ Analyzing project code. Please wait, this takes up to 30 seconds.",
        parse_mode="HTML"
    )
    
    project_path = Path(project_info['path'])
    structure_text = get_project_structure_text(project_path)
    code_samples = get_key_file_contents(project_path)
    
    log_content = ""
    log_file_path = project_path / f"{project_name}_execution.log"
    if log_file_path.exists():
        try:
            with open(log_file_path, 'r', encoding='utf-8') as f:
                log_content = f.read()[-2000:]  # Grab latest traceback
        except:
            pass
            
    prompt = f"""
Analyze the uploaded Python project named '{project_name}' on our virtualized DevOps cloud container.
We need you to evaluate:
1. Directory Architecture: Identify the real entrypoint (especially if nested in folders like src, app, internal).
2. Code Analysis: Look at the file structures and contents below, identify bugs, syntax issues, or import anomalies.
3. Troubleshooting & Logs: If there are run tracebacks/logs below, locate the file causing the error, explain the issue (in Persian), and provide the modified Python code block to replace and fix it.
4. Deployment Guide: Give a clear Persian step-by-step summary of how the user should properly run or fix this nested layout.

--- DIRECTORY STRUCTURE TREE ---
{structure_text}

--- CODES SNIPPETS & REQS ---
{code_samples}

--- RECENT CRASH / RUN LOGS ---
{log_content or 'No traceback history recorded.'}
"""

    ai_response = await ask_ai(prompt)
    
    if len(ai_response) > 3800:
        ai_response = ai_response[:3700] + "\n\n... (توضیحات طولانی به علت محدودیت تلگرام کوتاه شد)"
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Run Project", callback_data=f"run_project:{project_name}")],
        [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects"),
         InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(
        f"🤖 <b>AI DEVOPS CLOUD SCAN REPORT</b>\n"
        f"📦 Project: <code>{project_name}</code>\n"
        f"====================================\n\n"
        f"{ai_response}",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("run_project:"))
async def callback_run_project(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    project_info = user_files.get(user_id, {}).get(project_name)
    if not project_info:
        await callback.answer("❌ Project not found!", show_alert=True)
        return
    
    project_path = Path(project_info['path'])
    main_file = find_main_file(project_path)
    
    if not main_file or not Path(main_file).exists():
        await callback.answer("❌ Main file not found!", show_alert=True)
        return
    
    script_key = f"{user_id}_{project_name}"
    if script_key in bot_scripts:
        await callback.answer("⚠️ Project is already running!", show_alert=True)
        return
    
    venv_path = UPLOAD_BOTS_DIR / f"user_{user_id}_{project_name}_venv"
    if not venv_path.exists():
        await callback.answer("❌ Please create virtual environment first!", show_alert=True)
        return
    
    log_file_path = project_path / f"{project_name}_execution.log"
    
    try:
        await callback.message.edit_text(
            f"🚀 <b>Starting Project...</b>\n\n"
            f"📦 Project: <code>{project_name}</code>\n"
            f"🐍 Main File: <code>{os.path.basename(main_file)}</code>\n"
            f"⏳ Initializing...",
            parse_mode="HTML"
        )
        
        log_file = open(log_file_path, 'w')
        python_path = get_venv_python_path(str(venv_path))
        
        project_env = os.environ.copy()
        env_file = project_path / ".env"
        if env_file.exists():
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            project_env[key.strip()] = value.strip()
                logger.info(f"Loaded environment variables from project .env file")
            except Exception as e:
                logger.error(f"Error loading project .env: {e}")
        
        process = subprocess.Popen(
            [python_path, main_file],
            cwd=str(project_path),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=project_env,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        bot_scripts[script_key] = {
            'process': process,
            'project_name': project_name,
            'script_owner_id': user_id,
            'start_time': datetime.now(),
            'project_path': str(project_path),
            'log_file': log_file,
            'log_file_path': str(log_file_path)
        }
        
        bot_stats['total_runs'] = bot_stats.get('total_runs', 0) + 1
        
        await asyncio.sleep(2.5)
        if process.poll() is None:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⏹️ Stop Project", callback_data=f"stop_project:{project_name}")],
                [InlineKeyboardButton(text="📋 View Logs", callback_data=f"view_logs:{project_name}")],
                [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects"),
                 InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
            ])
            
            await callback.message.edit_text(
                f"""    
    ╔═══════════════════════════════════╗
          🚀 <b>PROJECT RUNNING!</b> 🚀
    ╚═══════════════════════════════════╝
    
    ✅ <b>Status:</b> Running successfully
    📦 <b>Project:</b> <code>{project_name}</code>
    🐍 <b>Main File:</b> <code>{os.path.basename(main_file)}</code>
    ⏱️ <b>Started:</b> {datetime.now().strftime('%H:%M:%S')}
    📋 <b>Logs:</b> Available
    
    <b>Your project is now running! 🎉</b>
    
    <i>Note: Check logs for output and any errors</i>
    """,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer("✅ Project started successfully!")
        else:
            exit_code = process.returncode
            log_file.close()
            
            try:
                with open(log_file_path, 'r') as f:
                    log_content = f.read()
            except:
                log_content = "Could not read log file"
            
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            
            # Offer Direct AI Troubleshoot / Auto-Fix option on Crash!
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🤖 AI Troubleshooting & Auto-Fix", callback_data=f"ai_diagnostic:{project_name}")],
                [InlineKeyboardButton(text="📋 View Error Logs", callback_data=f"view_logs:{project_name}")],
                [InlineKeyboardButton(text="🔄 Try Again", callback_data=f"run_project:{project_name}")],
                [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects"),
                 InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
            ])
            
            error_msg = log_content[:450] + "..." if len(log_content) > 450 else log_content
            
            await callback.message.edit_text(
                f"""    
    ╔═══════════════════════════════════╗
          ❌ <b>PROJECT FAILED TO START</b> ❌
    ╚═══════════════════════════════════╝
    
    ❌ <b>Status:</b> Exited with code {exit_code}
    📦 <b>Project:</b> <code>{project_name}</code>
    🐍 <b>Main File:</b> <code>{os.path.basename(main_file)}</code>
    
    <b>Error Output:</b>
    <code>{error_msg}</code>
    
    💡 <b>AI Fix Available:</b> Click the <b>AI Troubleshooting</b> button below to have the hosting AI engine resolve this traceback automatically!
    """,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer(f"❌ Project exited with code {exit_code}", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error running project: {e}")
        if script_key in bot_scripts:
            del bot_scripts[script_key]
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("stop_project:"))
async def callback_stop_project(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    script_key = f"{user_id}_{project_name}"
    
    if script_key not in bot_scripts:
        await callback.answer("❌ Project is not running!", show_alert=True)
        return
    
    try:
        script_info = bot_scripts[script_key]
        process = script_info['process']
        
        process.terminate()
        await asyncio.sleep(2)
        
        if process.poll() is None:
            process.kill()
        
        if 'log_file' in script_info:
            script_info['log_file'].close()
        
        del bot_scripts[script_key]
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Run Again", callback_data=f"run_project:{project_name}")],
            [InlineKeyboardButton(text="📋 View Logs", callback_data=f"view_logs:{project_name}")],
            [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects"),
             InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(
            f"""    
    ╔═══════════════════════════════════╗
          ⏹️ <b>PROJECT STOPPED</b> ⏹️
    ╚═══════════════════════════════════╝
    
    ✅ <b>Status:</b> Project stopped successfully
    📦 <b>Project:</b> <code>{project_name}</code>
    ⏱️ <b>Stopped:</b> {datetime.now().strftime('%H:%M:%S')}
    
    <b>Project has been stopped.</b>
    
    You can run it again or check the logs.
    """,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        await callback.answer("✅ Project stopped successfully!")
        
    except Exception as e:
        logger.error(f"Error stopping project: {e}")
        await callback.answer(f"❌ Error: {str(e)}", show_alert=True)

@dp.callback_query(F.data.startswith("view_logs:"))
async def callback_view_logs(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    project_info = user_files.get(user_id, {}).get(project_name)
    if not project_info:
        await callback.answer("❌ Project not found!", show_alert=True)
        return
    
    project_path = Path(project_info['path'])
    log_file_path = project_path / f"{project_name}_execution.log"
    
    try:
        if log_file_path.exists():
            with open(log_file_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            if len(log_content) > 3300:
                log_content = log_content[-3300:] + "\n\n... (truncated)"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh", callback_data=f"view_logs:{project_name}")],
                [InlineKeyboardButton(text="🤖 AI Analyze Logs", callback_data=f"ai_diagnostic:{project_name}")],
                [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects"),
                 InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
            ])
            
            await callback.message.edit_text(
                f"""    
    ╔═══════════════════════════════════╗
          📋 <b>PROJECT LOGS</b> 📋
    ╚═══════════════════════════════════╝
    
    📦 <b>Project:</b> <code>{project_name}</code>
    📋 <b>Log File:</b> {project_name}_execution.log
    
    <b>Latest Output:</b>
    <code>{log_content}</code>
    """,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await callback.answer("✅ Logs refreshed!")
        else:
            await callback.answer("❌ No logs found!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error viewing logs: {e}")
        await callback.answer(f"❌ Error reading logs: {str(e)}", show_alert=True)

# ============= PROJECT DELETION HANDLERS =============

@dp.callback_query(F.data.startswith("delete_proj:"))
async def callback_delete_project(callback: types.CallbackQuery):
    """Initiates confirmation dialog before triggering structural resource deletions."""
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Delete Project", callback_data=f"confirm_delete:{project_name}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="check_projects")
        ]
    ])
    
    await callback.message.edit_text(
        f"⚠️ <b>Delete Confirmation Required</b>\n\n"
        f"Are you sure you want to delete project <code>{project_name}</code>?\n\n"
        f"• Stops execution and releases RAM/CPU context.\n"
        f"• Deletes the isolated Virtual Environment (Venv).\n"
        f"• Purges all code files, .env settings, and log outputs.\n"
        f"• Removes database indices permanently.\n\n"
        f"<i>This action cannot be undone!</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_delete:"))
async def callback_confirm_delete(callback: types.CallbackQuery):
    """Executes total resource cleanup on local structures and system disk files."""
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    await callback.message.edit_text(
        f"🗑️ <b>Purging project: {project_name}...</b>\n"
        f"Terminating run process and erasing cloud directory folders. Please wait...",
        parse_mode="HTML"
    )
    
    await delete_project_completely(user_id, project_name)
    
    await callback.message.edit_text(
        f"✅ <b>Successfully Deleted!</b>\n\n"
        f"All files, isolated execution environments, database indices, and running contexts for <code>{project_name}</code> have been safely wiped to free up server overhead.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📁 My Projects", callback_data="check_projects")],
            [InlineKeyboardButton(text="🏠 Home", callback_data="back_to_main")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer("🗑️ Project deleted successfully!")

# ============= USER PROJECTS LIST VIEW =============

@dp.callback_query(F.data == "check_projects")
async def callback_check_projects(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    limit = get_user_project_limit(user_id)
    
    projects = user_files.get(user_id, {})
    
    if not projects:
        text = f"""    
    ╔═══════════════════════════════════╗
          📁 <b>MY PROJECTS</b> 📁
    ╚═══════════════════════════════════╝
    
    📝 <b>No projects uploaded yet!</b>
    
    📊 <b>Usage:</b> 0/{limit} projects
    
    <b>Ready to upload your first project?</b>
    
    1️⃣ Click "Upload Project"
    2️⃣ Send your ZIP file
    3️⃣ We'll handle the rest! 🚀
    """
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Upload First Project", callback_data="upload_project")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ])
    else:
        text = f"""    
    ╔═══════════════════════════════════╗
          📁 <b>MY PROJECTS</b> 📁
    ╚═══════════════════════════════════╝
    
    📊 <b>Usage:</b> {len(projects)}/{limit} projects
    
    <b>Your Projects:</b>
    """
        
        buttons = []
        for i, project_name in enumerate(projects, 1):
            project_info = projects[project_name]
            venv_path = UPLOAD_BOTS_DIR / f"user_{user_id}_{project_name}_venv"
            script_key = f"{user_id}_{project_name}"
            
            venv_status = "✅" if venv_path.exists() else "❌"
            is_running = script_key in bot_scripts
            status = "🟢 Running" if is_running else "⏸️ Stopped"
            
            text += f"{i}. 📦 <code>{project_name}</code>\n"
            text += f"   🛠️ Venv: {venv_status} | {status}\n\n"
            
            action_text = "⏹️ Stop" if is_running else "🚀 Run"
            action_callback = "stop_project" if is_running else "run_project"
            
            # Row 1: Execute control
            buttons.append([
                InlineKeyboardButton(text=f"{action_text} {project_name[:12]}", callback_data=f"{action_callback}:{project_name}")
            ])
            # Row 2: Management & AI Diagnostics & Wipe button
            buttons.append([
                InlineKeyboardButton(text="🤖 AI Diagnostic", callback_data=f"ai_diagnostic:{project_name}"),
                InlineKeyboardButton(text="📋 Logs", callback_data=f"view_logs:{project_name}"),
                InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_proj:{project_name}")
            ])
        
        buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_fav:"))
async def callback_toggle_favorite(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    project_name = callback.data.split(":", 1)[1]
    
    if user_id not in user_favorites:
        user_favorites[user_id] = []
    
    try:
        if project_name in user_favorites[user_id]:
            user_favorites[user_id].remove(project_name)
            action_text = "removed from favorites"
            action_emoji = "💔"
        else:
            user_favorites[user_id].append(project_name)
            action_text = "added to favorites"
            action_emoji = "⭐"
        
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('DELETE FROM favorites WHERE user_id = ? AND project_name = ?', (user_id, project_name))
        for fav in user_favorites[user_id]:
            c.execute('INSERT OR IGNORE INTO favorites (user_id, project_name) VALUES (?, ?)', (user_id, fav))
        conn.commit()
        conn.close()
        
        await callback.answer(f"{action_emoji} Project {action_text}!", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error toggling favorite: {e}")
        await callback.answer("❌ Error updating favorites!", show_alert=True)

@dp.callback_query(F.data == "my_favorites")
async def callback_my_favorites(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    favorites = user_favorites.get(user_id, [])
    
    if not favorites:
        text = """    
    ╔═══════════════════════════════════╗
          ⭐ <b>MY FAVORITES</b> ⭐
    ╚═══════════════════════════════════╝
    
    💔 <b>No favorite projects yet!</b>
    
    <b>How to add favorites:</b>
    1️⃣ Upload a project
    2️⃣ Click "⭐ Add Favorite"
    3️⃣ Access them here anytime!
    """
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Upload Project", callback_data="upload_project")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ])
    else:
        text = f"""    
    ╔═══════════════════════════════════╗
          ⭐ <b>MY FAVORITES</b> ⭐
    ╚═══════════════════════════════════╝
    
    <b>Your Favorite Projects:</b>
    """
        buttons = []
        for i, project_name in enumerate(favorites, 1):
            text += f"{i}. ⭐ <code>{project_name}</code>\n"
            buttons.append([
                InlineKeyboardButton(text=f"🚀 {project_name[:20]}", callback_data=f"run_project:{project_name}"),
                InlineKeyboardButton(text="💔", callback_data=f"toggle_fav:{project_name}")
            ])
        
        buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "bot_speed")
async def callback_bot_speed(callback: types.CallbackQuery):
    register_active_user(callback.from_user.id)
    start_time = datetime.now()
    await callback.answer("⚡ Testing...", show_alert=False)
    end_time = datetime.now()
    speed = (end_time - start_time).total_seconds() * 1000
    
    if speed < 100:
        status = "🟢 Excellent"
        emoji = "🚀"
    elif speed < 300:
        status = "🟡 Good"
        emoji = "⚡"
    else:
        status = "🔴 Slow"
        emoji = "🐌"
    
    text = f"""    
    ╔═══════════════════════════════════╗
          ⚡ <b>BOT SPEED TEST</b> ⚡
    ╚═══════════════════════════════════╝
    
    {emoji} <b>Status:</b> {status}
    ⏱️ <b>Response Time:</b> {speed:.2f} ms
    
    <b>Performance Analysis:</b>
    """
    
    if speed < 100:
        text += """
    ✅ Excellent performance!
    🚀 Bot is running at optimal speed
    💨 Instant response times
    """
    elif speed < 300:
        text += """
    ✅ Good performance
    ⚡ Bot is responsive
    🔄 Normal operation speed
    """
    else:
        text += """
    ⚠️ Bot is running slow
    🔍 Check server resources
    🔄 Consider restarting
    """
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Test Again", callback_data="bot_speed")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "statistics")
async def callback_statistics(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    projects = user_files.get(user_id, {})
    
    text = f"""    
    ╔═══════════════════════════════════╗
          📊 <b>MY STATISTICS</b> 📊
    ╚═══════════════════════════════════╝
    
    👤 <b>User:</b> {callback.from_user.full_name}
    🆔 <b>ID:</b> <code>{user_id}</code>
    
    <b>Your Stats:</b>
    📦 <b>Projects:</b> {len(projects)}/{get_user_project_limit(user_id)}
    ⭐ <b>Favorites:</b> {len(user_favorites.get(user_id, []))}
    
    <b>Bot Stats:</b>
    📤 <b>Total Uploads:</b> {bot_stats.get('total_uploads', 0)}
    🚀 <b>Total Runs:</b> {bot_stats.get('total_runs', 0)}
    """
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="statistics")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "help_info")
async def callback_help_info(callback: types.CallbackQuery):
    register_active_user(callback.from_user.id)
    text = """    
    ╔═══════════════════════════════════╗
          ℹ️ <b>HELP & INFORMATION</b> ℹ️
    ╚═══════════════════════════════════╝
    
    <b>🤖 How to use the bot:</b>
    
    1️⃣ <b>Upload Projects</b>
    📤 Send ZIP files containing your Python projects
    📦 Supports complete project structures
    🔍 Automatic detection of main files
    
    2️⃣ <b>Virtual Environments</b>
    🛠️ Create isolated Python environments
    📦 Install project dependencies automatically
    🔧 Safe and isolated execution
    
    3️⃣ <b>Run Projects</b>
    🚀 Execute your projects with one click
    📋 View real-time logs and output
    ⏹️ Stop and restart projects anytime
    
    🤖 <b>AI DevOps Troubleshooter</b>
    🧠 Analyze complex nested configurations and trace error logs instantly!
    
    <b>📝 Project Requirements:</b>
    • ZIP archive format
    • Python files (.py)
    • requirements.txt (optional)
    • .env file for variables (optional)
    
    <b>🔧 Tips:</b>
    • Keep your projects organized
    • Use meaningful project names
    • Check logs for debugging
    • Add favorites for quick access
    
    <b>📞 Need Help?</b>
    Contact: @NASA_LEADER1
    """
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Upload Project", callback_data="upload_project")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "all_features")
async def callback_all_features(callback: types.CallbackQuery):
    register_active_user(callback.from_user.id)
    text = """    
    ╔═══════════════════════════════════╗
          🎯 <b>ALL FEATURES</b> 🎯
    ╚═══════════════════════════════════╝
    
    <b>🚀 Core Features:</b>
    
    📤 <b>Smart Upload System</b>
    • Automatic ZIP extraction
    • Project structure analysis
    • Main file detection
    • Duplicate naming handling
    
    🛠️ <b>Virtual Environment Management</b>
    • Isolated Python environments
    • Automatic pip setup
    • Package installation
    • Environment isolation
    
    🔧 <b>Project Execution</b>
    • One-click project running
    • Real-time log viewing
    • Process management
    • Error handling
    
    📋 <b>Advanced Features:</b>
    
    ⭐ <b>Favorites System</b>
    • Quick access to important projects
    • Persistent storage
    • Easy management
    
    📊 <b>Statistics & Analytics</b>
    • Usage tracking
    • Performance monitoring
    • User statistics
    
    🧠 <b>AI Smart DevOps Engine</b>
    • Smart nested layouts detection
    • Automatic error-log diagnostics and corrections
    
    👥 <b>User Management</b>
    • Project limits
    • User roles
    • Banning system
    • Admin controls
    
    🔒 <b>Security Features</b>
    • Isolated execution
    • Process monitoring
    • Resource management
    • Safe file handling
    
    <b>✨ Premium Features:</b>
    💎 Increased project limits
    🚀 Priority execution
    📈 Extended analytics
    🎯 Advanced tools
    """
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 Get Premium", callback_data="get_premium")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "get_premium")
async def callback_get_premium(callback: types.CallbackQuery):
    register_active_user(callback.from_user.id)
    text = """    
    ╔═══════════════════════════════════╗
          💎 <b>GET PREMIUM</b> 💎
    ╚═══════════════════════════════════╝
    
    <b>🌟 Premium Benefits:</b>
    
    📦 <b>Extended Limits:</b>
    • Free: 1 projects
    • Premium: 80 projects
    • Admin: 999 projects
    
    🚀 <b>Priority Features:</b>
    • Faster execution
    • Priority support
    • Advanced analytics
    • Extended storage
    
    🎯 <b>Advanced Tools:</b>
    • Project templates
    • Bulk operations
    • Advanced debugging
    • Custom environments
    
    💎 <b>Premium Plans:</b>
    
    📅 <b>Monthly: $9.99</b>
    • All premium features
    • Priority support
    • Monthly updates
    
    📅 <b>Yearly: $59.99</b>
    • Save 50%
    • All premium features
    • VIP support
    • Early access to new features
    
    📅 <b>Lifetime: $199.99</b>
    • One-time payment
    • Lifetime premium access
    • Exclusive features
    • Dedicated support
    
    <b>🎁 Limited Time Offer:</b>
    Get 20% off on yearly plans!
    Use code: LAUNCH20
    
    <b>📞 How to Purchase:</b>
    1️⃣ Contact @NASA_LEADER1
    2️⃣ Choose your plan
    3️⃣ Complete payment
    4️⃣ Enjoy premium features!
    
    <b>💳 Payment Methods:</b>
    • Cryptocurrency
    • Bank Transfer
    • Digital Wallets
    • Local payment options
    """
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Contact Admin", url=f"https://t.me/{YOUR_USERNAME.replace('@', '')}")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "search_projects")
async def callback_search_projects(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    register_active_user(user_id)
    
    projects = user_files.get(user_id, {})
    
    if not projects:
        text = """    
    ╔═══════════════════════════════════╗
          🔍 <b>SEARCH PROJECTS</b> 🔍
    ╚═══════════════════════════════════╝
    
    📝 <b>No projects to search!</b>
    
    <b>Search will be available after:</b>
    1️⃣ Uploading your first project
    2️⃣ Projects are indexed automatically
    3️⃣ Search by name instantly
    
    <b>Ready to upload?</b> Click below!
    """
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Upload Project", callback_data="upload_project")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ])
    else:
        text = f"""    
    ╔═══════════════════════════════════╗
          🔍 <b>SEARCH PROJECTS</b> 🔍
    ╚═══════════════════════════════════╝
    
    📊 <b>Available Projects:</b> {len(projects)}
    
    <b>📋 Your Projects:</b>
    """
        
        buttons = []
        for i, project_name in enumerate(projects, 1):
            project_info = projects[project_name]
            file_size_mb = project_info['size'] / (1024 * 1024)
            
            text += f"{i}. 📦 <code>{project_name}</code>\n"
            text += f"   💾 Size: {file_size_mb:.2f} MB\n\n"
            
            buttons.append([
                InlineKeyboardButton(text=f"🚀 {project_name[:15]}", callback_data=f"run_project:{project_name}"),
                InlineKeyboardButton(text="📋 Logs", callback_data=f"view_logs:{project_name}")
            ])
        
        buttons.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# ============= MAIN RUN ENTRYPOINT =============

async def main():
    """Main function to start the bot"""
    logger.info("🤖 Starting Advanced AI Project Bot...")
    
    if not init_db():
        logger.warning("⚠️ Database initialization failed, running in memory mode")
    
    if not migrate_db():
        logger.warning("⚠️ Database migration failed")
    
    if not load_data():
        logger.warning("⚠️ Database operations failed, running in memory mode")
    
    async def web_server():
        app = web.Application()
        
        async def health_check(request):
            return web.Response(text="AI Bot is running!", status=200)
        
        app.router.add_get('/health', health_check)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        logger.info("🌐 Web server started on port 8080")
    
    asyncio.create_task(web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Bot crashed: {e}", exc_info=True)
        sys.exit(1)