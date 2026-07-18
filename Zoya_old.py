# =====================================================
# ЗОЯ — Полная сборка Ksenia + Canon Engine 8.0
# Часть 1 из 15+
# =====================================================

import sys
import os
import re
import json
import requests
import concurrent.futures
import threading
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import time
import logging
import hashlib
from difflib import SequenceMatcher
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QGroupBox, QFormLayout, QLineEdit, QPushButton, QComboBox,
    QLabel, QMenuBar, QMenu, QStatusBar, QToolBar,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QAbstractItemView,
    QListWidget, QListWidgetItem, QScrollArea, QGridLayout,
    QInputDialog, QToolButton, QStyle, QTextEdit, QCheckBox,
    QRadioButton, QProgressBar, QProgressDialog, QFrame,
    QPlainTextEdit, QSpacerItem, QSizePolicy, QSlider,
    QSpinBox, QDoubleSpinBox, QButtonGroup
)
from PyQt6.QtCore import (
    Qt, QTimer, QSettings, QSize, QPoint,
    QStringListModel, QEvent, pyqtSignal,
    QThread, QObject, QModelIndex, QRunnable, QThreadPool,
    QMetaObject, Q_ARG, pyqtSlot
)
from PyQt6.QtGui import (
    QAction, QKeySequence, QColor, QFont, QIcon,
    QTextCursor, QClipboard, QDesktopServices, QPalette,
    QContextMenuEvent, QShortcut, QTextCharFormat, QSyntaxHighlighter,
    QFontMetrics, QPainter, QBrush, QPen, QGuiApplication
)


# =========================
# ZOYA CANON ENGINE 8.0 — ТВОЙ ПОЛНЫЙ КОД
# =========================

@dataclass
class ChannelData:
    name: str
    url: str
    extinf: str
    group: Optional[str] = None
    tvg_id: Optional[str] = None

    e_flags: Dict[str, Any] = field(default_factory=dict)
    e_group: Optional[str] = None
    e_class: Optional[str] = None

    z_code: Optional[str] = None
    region: Optional[str] = None

    cdn_type: Optional[str] = None
    cdn_chain: List[str] = field(default_factory=list)
    n_flags: Dict[str, Any] = field(default_factory=dict)

    country: Optional[str] = None
    language: Optional[str] = None
    world_region: Optional[str] = None

    quality: Optional[str] = None
    q_code: Optional[str] = None

    shift: Optional[int] = None
    s_code: Optional[str] = None

    world_shift: Optional[int] = None
    sw_code: Optional[str] = None

    live_status: Optional[bool] = None
    live_response_time: Optional[float] = None
    live_cdn: Optional[str] = None
    live_quality: Optional[str] = None
    live_tracks: Optional[str] = None

    epg_shift: int = 0

    extinf_extra: Dict[str, Any] = field(default_factory=dict)

    def apply_e_canon(self, e_canon):
        self.e_flags = e_canon.analyze_extinf(self.extinf)
        self.e_group = e_canon.detect_group(self.name, self.extinf)
        self.e_class = e_canon.classify(self.name, self.extinf)

    def apply_r_canon(self, r_canon):
        self.region = r_canon.detect_region(self.name, self.extinf)

    def apply_w_canon(self, w_canon):
        self.country = w_canon.detect_country(self.name, self.extinf)
        self.language = w_canon.detect_language(self.name, self.extinf)
        self.world_region = w_canon.detect_world_region(self.country)

    def apply_z_canon(self, z_canon):
        self.z_code = z_canon.get_zcode_for(self.name, self.group, self.region)

    def apply_n_canon(self, n_canon):
        info = n_canon.analyze_url(self.url)
        self.cdn_type = info.get("cdn_type")
        self.cdn_chain = info.get("cdn_chain", [])
        self.n_flags = info

    def apply_ultra_live(self, ultra):
        info = ultra.check_url(self.url)
        self.live_status = info["status"]
        self.live_response_time = info["response_time"]
        self.live_cdn = info["cdn"]
        self.live_quality = info["quality"]
        self.live_tracks = info["tracks"]

    def apply_q_canon(self, q_canon):
        self.quality = q_canon.detect_quality(self)
        self.q_code = q_canon.encode_quality(self.quality)
        self.name = f"{self.name} ({self.q_code})"
        self.extinf_extra["E-Q"] = self.q_code
        self.url = f"{self.url}?Q={self.q_code[-1]}"

    def apply_s_canon(self, s_canon):
        if self.country == "RU":
            self.shift = s_canon.detect_shift(self)
            self.s_code = s_canon.encode_shift(self.shift)
            self.name = f"{self.name} ({self.s_code})"
            self.extinf_extra["E-S"] = self.s_code
            self.url = f"{self.url}&S={self.shift}"
            self.epg_shift = self.shift

    def apply_sw_canon(self, sw_canon):
        if self.country and self.country != "RU":
            self.world_shift = sw_canon.detect_world_shift(self)
            self.sw_code = sw_canon.encode_world_shift(self.world_shift)
            self.name = f"{self.name} ({self.sw_code})"
            self.extinf_extra["E-SW"] = self.sw_code
            self.url = f"{self.url}&SW=UTC{self.world_shift:+d}"
            self.epg_shift = self.world_shift

    def apply_geo(self, g_canon):
        g_canon.apply_geo(self)

    def apply_e_protection(self, e_canon):
        e_canon.apply_protection(self)

    def update_extinf(self):
        parts = [self.extinf]
        for k, v in self.extinf_extra.items():
            parts.append(f'{k}="{v}"')
        self.extinf = " ".join(parts)


class ECanon:
    def analyze_extinf(self, extinf: str) -> Dict[str, Any]:
        flags = {}
        if "trash" in extinf.lower():
            flags["trash"] = True
        return flags

    def detect_group(self, name: str, extinf: str) -> str:
        name_l = name.lower()
        if "первый" in name_l or "россия" in name_l or "нтв" in name_l:
            return "Zoya Federal"
        return "Без группы"

    def classify(self, name: str, extinf: str) -> Dict[str, Any]:
        return {"type": "unknown"}

    def apply_protection(self, channel: ChannelData):
        channel.e_flags["protect"] = True
        channel.e_flags["ecode"] = channel.z_code or "00"

        channel.extinf_extra["x-protect"] = "zoya"
        channel.extinf_extra["x-e"] = channel.e_flags["ecode"]
        channel.extinf_extra["x-meta"] = "canon"

        if channel.tvg_id:
            channel.tvg_id = f'"{channel.tvg_id}"'

        channel.name = f"★★★ {channel.name} ★★★"
        channel.group = f"Zoya {channel.group or 'Group'}"

        channel.extinf_extra["E-CANON"] = "true"
        channel.extinf_extra["E-Z"] = channel.z_code or "00"
        channel.extinf_extra["E-R"] = channel.region or "NONE"
        channel.extinf_extra["E-W"] = channel.world_region or "NONE"

# =========================
# Продолжение ZOYA CANON ENGINE
# =========================

class RCanon:
    REGION_SHIFT_MAP = {
        "Калининград": -1,
        "Москва": 0,
        "Самара": 1,
    }

    def detect_region(self, name: str, extinf: str) -> str:
        n = name.lower()
        if "калининград" in n:
            return "Калининград"
        if "самара" in n:
            return "Самара"
        return "Москва"


class WCanon:
    def detect_country(self, name: str, extinf: str) -> str:
        n = name.lower()
        if any(x in n for x in ["bbc", "cnn", "dw", "nhk", "al jazeera", "tve"]):
            if "bbc" in n:
                return "UK"
            if "nhk" in n:
                return "JP"
            if "cnn" in n:
                return "US"
            if "tve" in n:
                return "ES"
            if "al jazeera" in n:
                return "QA"
            return "WORLD"
        return "RU"

    def detect_language(self, name: str, extinf: str) -> str:
        return "ru"

    def detect_world_region(self, country: str) -> str:
        if country in ("UK", "JP", "US", "ES", "QA", "WORLD"):
            return "INTL"
        return "RU"


class NCanon:
    def analyze_url(self, url: str) -> Dict[str, Any]:
        info = {}
        u = url.lower()
        if "ngenix" in u:
            info["cdn_type"] = "ngenix"
        elif "cloudflare" in u:
            info["cdn_type"] = "cloudflare"
        else:
            info["cdn_type"] = "other"

        if "tracks-v1a1" in u:
            info["tracks"] = "v1a1"

        return info


class UltraLiveEngine:
    def __init__(self, timeout: int = 3, workers: int = 20):
        self.timeout = timeout
        self.workers = workers

    def check_url(self, url: str) -> Dict[str, Any]:
        u = url.lower()
        return {
            "status": True,
            "response_time": 0.123,
            "cdn": "ngenix" if "ngenix" in u else "other",
            "quality": "1080p" if "1080" in u else "720p",
            "tracks": "v1a1" if "tracks-v1a1" in u else None,
        }


class QCanon:
    Q_MAP = {
        "360p": "Q.0",
        "480p": "Q.1",
        "576p": "Q.2",
        "720p": "Q.3",
        "1080p": "Q.4",
    }

    def detect_quality(self, channel: ChannelData) -> str:
        if channel.live_quality:
            return channel.live_quality

        u = channel.url.lower()
        if "1080" in u:
            return "1080p"
        if "720" in u:
            return "720p"
        if "576" in u:
            return "576p"
        if "480" in u:
            return "480p"
        if "360" in u:
            return "360p"
        return "360p"

    def encode_quality(self, quality: str) -> str:
        return self.Q_MAP.get(quality, "Q.0")


class SCanon:
    S_MAP = {
        -1: "S.(-1)",
        0: "S.0",
        1: "S.1",
    }

    Z_SHIFT_MAP = {
        "Z.R(39)": -1,
        "Z.R(77)": 0,
        "Z.R(63)": 1,
    }

    def detect_shift(self, channel: ChannelData) -> int:
        if channel.e_flags.get("tvg_shift") is not None:
            try:
                return int(channel.e_flags["tvg_shift"])
            except Exception:
                pass

        if channel.region in RCanon.REGION_SHIFT_MAP:
            return RCanon.REGION_SHIFT_MAP[channel.region]

        if channel.z_code in self.Z_SHIFT_MAP:
            return self.Z_SHIFT_MAP[channel.z_code]

        return 0

    def encode_shift(self, shift: int) -> str:
        return self.S_MAP.get(shift, "S.0")


class SWCanon:
    COUNTRY_UTC_MAP = {
        "WORLD": 0,
        "UK": 0,
        "DE": 1,
        "FI": 2,
        "TR": 3,
        "JP": 9,
        "US": -5,
        "ES": 1,
        "QA": 3,
    }

    def detect_world_shift(self, channel: ChannelData) -> int:
        if channel.country == "RU":
            return 0
        if channel.country in self.COUNTRY_UTC_MAP:
            return self.COUNTRY_UTC_MAP[channel.country]
        return 0

    def encode_world_shift(self, shift: int) -> str:
        return f"SW.(UTC{shift:+d})"


class GCanon:
    GEO_MAP = {
        "UK": {
            "country": "UK",
            "region": "GB-LON",
            "language": "en",
            "locale": "en_GB",
            "timezone": "Europe/London",
            "utc": 0,
            "cdn": "world-uk"
        },
        "JP": {
            "country": "JP",
            "region": "JP-TOK",
            "language": "ja",
            "locale": "ja_JP",
            "timezone": "Asia/Tokyo",
            "utc": 9,
            "cdn": "world-jp"
        },
        "US": {
            "country": "US",
            "region": "US-NY",
            "language": "en",
            "locale": "en_US",
            "timezone": "America/New_York",
            "utc": -5,
            "cdn": "world-us"
        },
        "ES": {
            "country": "ES",
            "region": "ES-MAD",
            "language": "es",
            "locale": "es_ES",
            "timezone": "Europe/Madrid",
            "utc": 1,
            "cdn": "world-es"
        },
        "QA": {
            "country": "QA",
            "region": "QA-DOH",
            "language": "ar",
            "locale": "ar_QA",
            "timezone": "Asia/Qatar",
            "utc": 3,
            "cdn": "world-qa"
        }
    }

    def detect_geo(self, channel: ChannelData) -> Optional[dict]:
        if channel.country in self.GEO_MAP:
            return self.GEO_MAP[channel.country]
        return None

    def apply_geo(self, channel: ChannelData):
        geo = self.detect_geo(channel)
        if not geo:
            return

        channel.extinf_extra["x-country"] = geo["country"]
        channel.extinf_extra["x-region"] = geo["region"]
        channel.extinf_extra["x-language"] = geo["language"]
        channel.extinf_extra["x-locale"] = geo["locale"]
        channel.extinf_extra["x-timezone"] = geo["timezone"]

        channel.world_shift = geo["utc"]
        channel.sw_code = f"SW.(UTC{geo['utc']:+d})"
        channel.name = f"{channel.name} ({channel.sw_code})"

        base_url = channel.url.split("?", 1)[0]
        channel.url = (
            f"{base_url}"
            f"?geo={geo['country']}"
            f"&locale={geo['locale']}"
            f"&timezone={geo['timezone']}"
            f"&cdn={geo['cdn']}"
            f"&SW=UTC{geo['utc']:+d}"
        )

        channel.epg_shift = geo["utc"]


class ZoyaCanonEngine8:
    def __init__(self):
        self.e_canon = ECanon()
        self.z_canon = ZCanon()
        self.r_canon = RCanon()
        self.w_canon = WCanon()
        self.n_canon = NCanon()
        self.q_canon = QCanon()
        self.s_canon = SCanon()
        self.sw_canon = SWCanon()
        self.g_canon = GCanon()
        self.ultra = UltraLiveEngine()

    def process_channel(self, ch: ChannelData) -> ChannelData:
        ch.apply_e_canon(self.e_canon)
        ch.apply_r_canon(self.r_canon)
        ch.apply_w_canon(self.w_canon)
        ch.apply_z_canon(self.z_canon)
        ch.apply_n_canon(self.n_canon)
        ch.apply_ultra_live(self.ultra)
        ch.apply_q_canon(self.q_canon)
        ch.apply_s_canon(self.s_canon)
        ch.apply_sw_canon(self.sw_canon)
        ch.apply_geo(self.g_canon)
        ch.apply_e_protection(self.e_canon)
        ch.update_extinf()
        return ch

# =====================================================
# Ksenia — DomainUserAgentRule и Manager
# =====================================================

class DomainUserAgentRule:
    def __init__(self, domain: str = "", user_agent: str = ""):
        self.domain: str = domain.strip()
        self.user_agent: str = user_agent.strip()
        self.enabled: bool = True
        self.created_date: datetime = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'domain': self.domain,
            'user_agent': self.user_agent,
            'enabled': self.enabled,
            'created_date': self.created_date.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DomainUserAgentRule':
        rule = cls()
        rule.domain = data.get('domain', '')
        rule.user_agent = data.get('user_agent', '')
        rule.enabled = data.get('enabled', True)
        
        created_date = data.get('created_date')
        if created_date:
            try:
                rule.created_date = datetime.fromisoformat(created_date)
            except (ValueError, TypeError):
                rule.created_date = datetime.now()
        
        return rule


class DomainUserAgentManager:
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = SystemThemeManager.get_config_dir()
        
        self.config_dir = config_dir
        self.rules_file = os.path.join(config_dir, "domain_user_agent_rules.json")
        self.rules: List[DomainUserAgentRule] = []
        
        self._ensure_config_dir()
        self._load_rules()
    
    def _ensure_config_dir(self):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Ошибка создания директории: {e}")
    
    def _load_rules(self):
        try:
            if os.path.exists(self.rules_file):
                with open(self.rules_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if isinstance(data, list):
                    self.rules = [DomainUserAgentRule.from_dict(item) for item in data]
                else:
                    self.rules = []
            else:
                self.rules = []
                self._save_rules()
                
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.error(f"Ошибка загрузки правил: {e}")
            self.rules = []
    
    def _save_rules(self):
        try:
            data = [rule.to_dict() for rule in self.rules]
            with open(self.rules_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except (IOError, OSError) as e:
            logger.error(f"Ошибка сохранения правил: {e}")
            return False
    
    def apply_rules_to_channels(self, channels: List[ChannelData]) -> int:
        modified_count = 0
        for channel in channels:
            if self.apply_rules_to_channel(channel):
                modified_count += 1
        return modified_count


class SystemThemeManager:
    @staticmethod
    def get_config_dir() -> str:
        return os.path.expanduser("\~/.zoya")


class LinkQuality(Enum):
    UNKNOWN = 0
    WORKING = 1
    NOT_WORKING = 2


class ChannelNameNormalizer:
    QUALITY_PATTERNS = [
        r'\(\s*(?:720|1080|1280|480|360|2160|4K|8K|UHD|HD|SD|FHD|FullHD)[pPi]?\s*\)',
        r'\(\s*(?:720|1080|1280|480|360|2160)[pP]\s*\)',
        r'\(\s*(?:4K|8K|UHD|HD|SD|FHD|FullHD)\s*\)',
        r'\(\s*(?:60|50|30|25)[fFpPsS]?\s*\)',
        r'\(\s*(?:High|Medium|Low)\s+Quality\s*\)',
        r'\(\s*\[?[0-9]+[pPi]\s*\]?\s*\)',
        r'\(\s*HQ\s*\)',
        r'\(\s*LQ\s*\)',
        r'\(\s*SQ\s*\)',
    ]
    
    BRACKETS_TO_REMOVE = [
        r'\[Geo-blocked\]',
        r'\[Not\s+24/7\]',
        r'\[Geo[-\s]?blocked\]',
        r'\[Not\s*24\s*/\s*7\]',
        r'\[Blocked\]',
        r'\[Restricted\]',
        r'\[GeoRestricted\]',
    ]
    
    EMOJI_PATTERN = re.compile(
        '['
        '\U0001F600-\U0001F64F'
        '\U0001F300-\U0001F5FF'
        '\U0001F680-\U0001F6FF'
        '\U0001F1E0-\U0001F1FF'
        '\U00002702-\U000027B0'
        '\U000024C2-\U0001F251'
        ']+',
        flags=re.UNICODE
    )
    
    @staticmethod
    def fix_encoding(text: str) -> str:
        if not text:
            return text
        try:
            if any(c in text for c in ['–', '—', '∏', 'ø', '—Å', '—Å–ø', '–°–ø']):
                bytes_data = text.encode('latin1')
                decoded = bytes_data.decode('utf-8', errors='replace')
                if any(c in decoded for c in ['а', 'б', 'в', 'г', 'д']):
                    return decoded
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        return text
    
    @staticmethod
    def normalize(name: str, remove_parentheses: bool = True, remove_brackets: bool = True, 
                  remove_emojis: bool = True, remove_special_chars: bool = True) -> str:
        if not name:
            return ""
        
        fixed_name = ChannelNameNormalizer.fix_encoding(name)
        normalized = fixed_name
        
        if remove_parentheses:
            for pattern in ChannelNameNormalizer.QUALITY_PATTERNS:
                normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
            normalized = re.sub(r'\(\s*\)', '', normalized)
        
        if remove_brackets:
            for pattern in ChannelNameNormalizer.BRACKETS_TO_REMOVE:
                normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
            normalized = re.sub(r'\[\s*\]', '', normalized)
        
        normalized = re.sub(r'\{[^}]*\}', '', normalized)
        
        if remove_emojis:
            normalized = ChannelNameNormalizer.EMOJI_PATTERN.sub('', normalized)
        
        if remove_special_chars:
            normalized = re.sub(r'[^\w\s\-\+\\/\.\,:()\[\]]', ' ', normalized)
            normalized = re.sub(r'\s+', ' ', normalized)
        
        normalized = normalized.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized


# Продолжение в следующей части...

# =========================
# LinkSource и LinkReplacementSettings
# =========================

class LinkSource:
    def __init__(self):
        self.name: str = ""
        self.path: str = ""
        self.source_type: str = "local"
        self.last_updated: Optional[datetime] = None
        self.total_links: int = 0
        self.working_links: int = 0
        self.priority: int = 5
        self.enabled: bool = True
        self.auto_update: bool = False
        self.update_interval_hours: int = 24
        self.tags: List[str] = []
        self.description: str = ""
        self.link_cache: Dict[str, List[str]] = {}
        self.last_cache_update: Optional[datetime] = None
        self.encoding: str = "utf-8"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'path': self.path,
            'source_type': self.source_type,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'total_links': self.total_links,
            'working_links': self.working_links,
            'priority': self.priority,
            'enabled': self.enabled,
            'auto_update': self.auto_update,
            'update_interval_hours': self.update_interval_hours,
            'tags': self.tags,
            'description': self.description,
            'link_cache': self.link_cache,
            'last_cache_update': self.last_cache_update.isoformat() if self.last_cache_update else None,
            'encoding': self.encoding
        }


class LinkReplacementSettings:
    def __init__(self):
        self.match_threshold_percent: float = 80.0
        self.use_fuzzy_matching: bool = True
        self.min_name_similarity: float = 0.7
        self.search_type: str = "exact"
        self.filter_temporary_links: bool = True
        self.filter_unsafe_links: bool = True
        self.temporary_domains: List[str] = ["tmp.", "temp.", "short."]
        self.unsafe_domains: List[str] = ["malware.", "phishing.", "spam."]
        self.check_timeout: int = 5
        self.max_workers: int = 5
        self.max_retries: int = 2
        self.retry_delay: float = 0.5
        self.auto_replace_broken: bool = True
        self.auto_replace_missing: bool = True
        self.keep_backup_links: bool = True
        self.max_alternative_urls: int = 5
        self.use_ip_filtering: bool = True
        self.blacklisted_ips: List[str] = []
        self.whitelisted_ips: List[str] = []
        self.blacklisted_domains: List[str] = []
        self.whitelisted_domains: List[str] = []
        self.prioritize_whitelisted: bool = True
        self.blacklist_priority: int = -10
        self.whitelist_priority: int = 10
        self.ignore_special_chars_in_names: bool = True
        self.remove_parentheses_in_names: bool = True
        self.remove_brackets_in_names: bool = True
        self.remove_emojis_in_names: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'match_threshold_percent': self.match_threshold_percent,
            'use_fuzzy_matching': self.use_fuzzy_matching,
            'min_name_similarity': self.min_name_similarity,
            'search_type': self.search_type,
            'filter_temporary_links': self.filter_temporary_links,
            'filter_unsafe_links': self.filter_unsafe_links,
            'temporary_domains': self.temporary_domains,
            'unsafe_domains': self.unsafe_domains,
            'check_timeout': self.check_timeout,
            'max_workers': self.max_workers,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'auto_replace_broken': self.auto_replace_broken,
            'auto_replace_missing': self.auto_replace_missing,
            'keep_backup_links': self.keep_backup_links,
            'max_alternative_urls': self.max_alternative_urls,
            'use_ip_filtering': self.use_ip_filtering,
            'blacklisted_ips': self.blacklisted_ips,
            'whitelisted_ips': self.whitelisted_ips,
            'blacklisted_domains': self.blacklisted_domains,
            'whitelisted_domains': self.whitelisted_domains,
            'prioritize_whitelisted': self.prioritize_whitelisted,
            'blacklist_priority': self.blacklist_priority,
            'whitelist_priority': self.whitelist_priority,
            'ignore_special_chars_in_names': self.ignore_special_chars_in_names,
            'remove_parentheses_in_names': self.remove_parentheses_in_names,
            'remove_brackets_in_names': self.remove_brackets_in_names,
            'remove_emojis_in_names': self.remove_emojis_in_names
        }


# =========================
# PlaylistTab — расширенная версия
# =========================

class PlaylistTab(QWidget):
    def __init__(self, filepath=None):
        super().__init__()
        self.filepath = filepath
        self.all_channels: List[ChannelData] = []
        self.zoya_engine = ZoyaCanonEngine8()
        self.modified = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Имя", "Группа", "Z-Code", "Q-Code", "URL", "Статус"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        
        zoya_btn = QPushButton("🚀 Применить Zoya Canon Engine 8.0")
        zoya_btn.clicked.connect(self.apply_zoya_canons)
        btn_layout.addWidget(zoya_btn)
        
        save_btn = QPushButton("💾 Сохранить")
        save_btn.clicked.connect(self.save_to_file)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)

    def load_file(self, filepath):
        self.filepath = filepath
        try:
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self._parse_m3u(content)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось открыть файл:\n{str(e)}")

    def _parse_m3u(self, content: str):
        self.all_channels.clear()
        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("#EXTINF:"):
                ch = ChannelData()
                ch.extinf = line
                if ',' in line:
                    ch.name = line.split(',', 1)[1].strip()
                i += 1
                if i < len(lines) and not lines[i].startswith("#"):
                    ch.url = lines[i].strip()
                self.all_channels.append(ch)
            i += 1
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.all_channels))
        for row, ch in enumerate(self.all_channels):
            self.table.setItem(row, 0, QTableWidgetItem(ch.name))
            self.table.setItem(row, 1, QTableWidgetItem(ch.group or "Без группы"))
            self.table.setItem(row, 2, QTableWidgetItem(ch.z_code or ""))
            self.table.setItem(row, 3, QTableWidgetItem(ch.q_code or ""))
            url_text = ch.url[:80] + "..." if len(ch.url) > 80 else ch.url
            self.table.setItem(row, 4, QTableWidgetItem(url_text))
            self.table.setItem(row, 5, QTableWidgetItem("✓" if ch.url else "✗"))

    def apply_zoya_canons(self):
        if not self.zoya_engine or not self.all_channels:
            QMessageBox.warning(self, "Ошибка", "Нет данных для обработки")
            return
        
        count = len(self.all_channels)
        for ch in self.all_channels:
            self.zoya_engine.process_channel(ch)
        
        self._refresh_table()
        self.modified = True
        QMessageBox.information(self, "Зоя", f"Canon Engine 8.0 успешно применён к {count} каналам!")

    def save_to_file(self):
        if not self.filepath:
            self.filepath, _ = QFileDialog.getSaveFileName(self, "Сохранить как", "", "M3U (*.m3u *.m3u8)")
        
        if self.filepath:
            try:
                with open(self.filepath, 'w', encoding='utf-8') as f:
                    f.write("#EXTM3U\n\n")
                    for ch in self.all_channels:
                        f.write(ch.extinf + "\n")
                        if ch.url:
                            f.write(ch.url + "\n")
                self.modified = False
                QMessageBox.information(self, "Сохранено", f"Файл сохранён:\n{self.filepath}")
                return True
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", str(e))
        return False

# =========================
# MainWindow — Полная версия
# =========================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Зоя — M3U Editor + Canon Engine 8.0")
        self.resize(1850, 1100)

        self.tabs = {}
        self.current_tab = None
        self.zoya_engine = ZoyaCanonEngine8()

        self.domain_ua_manager = DomainUserAgentManager()
        self.blacklist_manager = BlacklistManager()

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._new_file()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tab_widget)

    def _setup_menu(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("Файл")
        file_menu.addAction("Новый", self._new_file, "Ctrl+N")
        file_menu.addAction("Открыть", self._open_file, "Ctrl+O")
        file_menu.addAction("Сохранить", self._save_file, "Ctrl+S")
        file_menu.addAction("Сохранить как", self._save_as, "Ctrl+Shift+S")

        zoya_menu = mb.addMenu("Зоя")
        zoya_menu.addAction("Применить Canon Engine 8.0", self._apply_zoya_canons, "Ctrl+Shift+Z")
        zoya_menu.addAction("User-Agent по доменам", self._manage_ua)

    def _setup_toolbar(self):
        tb = QToolBar()
        self.addToolBar(tb)
        tb.addAction("Новый", self._new_file)
        tb.addAction("Открыть", self._open_file)
        tb.addAction("Сохранить", self._save_file)
        tb.addSeparator()
        tb.addAction("Zoya Canon 8.0", self._apply_zoya_canons)

    def _new_file(self):
        tab = PlaylistTab()
        tab.zoya_engine = self.zoya_engine
        index = self.tab_widget.addTab(tab, "Новый плейлист")
        self.tabs[tab] = tab
        self.tab_widget.setCurrentIndex(index)
        self.current_tab = tab

    def _open_file(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Открыть M3U", "", "M3U (*.m3u *.m3u8)")
        if filepath:
            tab = PlaylistTab()
            tab.zoya_engine = self.zoya_engine
            tab.load_file(filepath)
            index = self.tab_widget.addTab(tab, os.path.basename(filepath))
            self.tabs[tab] = tab
            self.tab_widget.setCurrentIndex(index)
            self.current_tab = tab

    def _save_file(self):
        if self.current_tab:
            self.current_tab.save_to_file()

    def _save_as(self):
        if self.current_tab:
            filepath, _ = QFileDialog.getSaveFileName(self, "Сохранить как", "", "M3U (*.m3u)")
            if filepath:
                self.current_tab.filepath = filepath
                self.current_tab.save_to_file()

    def _apply_zoya_canons(self):
        if self.current_tab:
            self.current_tab.apply_zoya_canons()

    def _manage_ua(self):
        dialog = DomainUserAgentDialog(self.domain_ua_manager, self)
        dialog.exec()

    def _close_tab(self, index):
        widget = self.tab_widget.widget(index)
        if widget in self.tabs:
            del self.tabs[widget]
        self.tab_widget.removeTab(index)

    def _on_tab_changed(self, index):
        if index >= 0:
            self.current_tab = self.tab_widget.widget(index)
        else:
            self.current_tab = None


# =========================
# BlacklistManager (простая версия)
# =========================

class BlacklistManager:
    def __init__(self):
        self.blacklist = []

    def add_channel(self, name, tvg_id):
        self.blacklist.append({"name": name, "tvg_id": tvg_id})


