"""
Dayflow Windows - 主题管理
IDE 风格的亮色/暗色主题
"""
from dataclasses import dataclass
from typing import Optional
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Signal, QObject


@dataclass
class Theme:
    """主题颜色定义"""
    name: str
    
    # 背景色
    bg_primary: str      # 主背景
    bg_secondary: str    # 次背景（卡片、面板）
    bg_tertiary: str     # 第三背景（输入框）
    bg_hover: str        # 悬停背景
    bg_sidebar: str      # 侧边栏
    
    # 边框
    border: str
    border_hover: str
    
    # 文字
    text_primary: str    # 主文字
    text_secondary: str  # 次文字
    text_muted: str      # 弱化文字
    
    # 强调色
    accent: str          # 主强调色
    accent_hover: str
    accent_light: str    # 浅强调色（背景用）
    
    # 功能色
    success: str
    warning: str
    error: str
    
    # 滚动条
    scrollbar: str
    scrollbar_hover: str
    
    # 卡片阴影
    shadow: str

    # ── Apple 规范补充字段（带默认值，向后兼容旧调用）──
    accent_focus: str = ""   # 2px 焦点环，Apple 强制项
    pressed: str = ""        # 按下态底色
    divider: str = ""        # 发丝分隔线（比 border 更轻）
    pill_bg: str = ""        # 药丸/次要按钮底色


# ─────────────────────────────────────────────────────────────
# 设计系统：Apple（来源 getdesign.md/apple/DESIGN.md）
#
# 核心约束（Apple 规范原文）：
#   · 单一强调色 Action Blue #0066CC，所有可点击元素只用它
#   · 亮色画布只有 白 / 羊皮纸 #F5F5F7 两种，靠明度切换制造节奏
#   · 暗色使用近黑 tile 三级台阶 #272729 / #2A2A2C / #252527
#   · 发丝线 1px，不给卡片加阴影（阴影只留给产品图）
#   · 药丸 radius 9999px 是"可点击"的第一信号
#   · 焦点环 2px Action Blue，全局不可省
#
# 语义色（绿/橙/红）Apple 规范未定义 —— 因为 Apple 页面没有数据图表。
# Dayflow 是生产力工具，需要状态色。这里取 Apple 系统色相并已按 WCAG
# 校验：全部 ≥ 4.5:1（浅色底）/ ≥ 5.5:1（深色底），满足小字号文本。
# ─────────────────────────────────────────────────────────────

# 暗色主题 — 近黑 tile 体系（Apple 官网夜间基调）
DARK_THEME = Theme(
    name="dark",
    bg_primary="#1C1C1E",       # Apple tile-1 稍暗，主画布
    bg_secondary="#2A2A2C",     # Apple surface-tile-2 卡片
    bg_tertiary="#272729",      # Apple surface-tile-1 输入框
    bg_hover="#3A3A3C",         # 微抬一级，替代 Slate 700
    bg_sidebar="#000000",       # Apple surface-black 侧边栏
    border="#3A3A3C",           # 暗色发丝线
    border_hover="#48484A",
    text_primary="#FFFFFF",
    text_secondary="#CCCCCC",   # Apple body-muted
    text_muted="#AEAEAE",       # 弱化文字，仍达 6.46:1
    accent="#2997FF",           # Apple primary-on-dark（暗底专用）
    accent_hover="#4DA6FF",
    accent_light="rgba(41, 151, 255, 0.16)",
    accent_focus="#2997FF",     # 2px 焦点环
    success="#3DD68C",
    warning="#EFB93B",
    error="#F97B70",
    scrollbar="#3A3A3C",
    scrollbar_hover="#545457",
    shadow="rgba(0, 0, 0, 0.55)",
    pressed="#1F1F21",
    divider="#353537",
    pill_bg="#2A2A2C",
)


# 亮色主题 — 白 / 羊皮纸双画布（Apple 官网日间基调）
LIGHT_THEME = Theme(
    name="light",
    bg_primary="#F5F5F7",       # Apple canvas-parchment 主画布
    bg_secondary="#FFFFFF",     # Apple canvas 卡片
    bg_tertiary="#FFFFFF",      # 输入框同白，靠发丝线区分
    bg_hover="#F0F0F2",         # Apple divider-soft 附近
    bg_sidebar="#F5F5F7",       # 羊皮纸侧边栏
    border="#D2D2D7",           # Apple surface-chip-translucent 发丝线
    border_hover="#AEAEAE",
    text_primary="#1D1D1F",     # Apple ink
    text_secondary="#333333",   # Apple ink-muted-80
    text_muted="#6E6E73",       # Apple systemGray，4.66:1
    accent="#0066CC",           # Apple Action Blue 唯一强调色
    accent_hover="#0071E3",     # Apple primary-focus
    accent_light="rgba(0, 102, 204, 0.10)",
    # 焦点环用 Action Blue 本体：Apple 的 #0071E3 在羊皮纸底上只有 4.31:1，
    # 低于 WCAG 对非文本 UI 的 4.5:1 要求（#0066CC 为 5.11:1）
    accent_focus="#0066CC",
    success="#157347",
    warning="#8A5A00",
    error="#C42B1C",
    scrollbar="#D2D2D7",
    scrollbar_hover="#AEAEAE",
    shadow="rgba(0, 0, 0, 0.06)",
    pressed="#E8E8ED",
    divider="#F0F0F0",
    pill_bg="#FFFFFF",
)


# ── Apple 排版阶梯 ──────────────────────────────────────────
# Apple 规范：字号 17px 起，标题 600 字重 + 负字距（"Apple tight" 节奏），
# 正文 400/1.47。Dayflow 是桌面工具，比官网小一号，按同一比例缩放。
TYPE_SCALE = {
    "display":  (28, 600, -0.20),   # 页面主标题
    "title":    (20, 600, -0.15),   # 卡片标题 / 区块标题
    "headline": (17, 600, -0.20),   # 强调小标题
    "body":     (15, 400,  0.00),   # 正文
    "caption":  (13, 400,  0.00),   # 辅助说明
    "fine":     (11, 400,  0.00),   # 时间戳 / 微标签
    "nav":      (13, 400,  0.00),   # 导航
}

# ── Apple 圆角阶梯 ──────────────────────────────────────────
# 规范原文：sm 8px（紧凑工具）、md 11px（珠光按钮）、lg 18px（工具卡片）、
# pill 9999px（主 CTA / 药丸 / 搜索框）。不允许在中间随手取值。
RADIUS = {
    "sm": 8,
    "md": 11,
    "lg": 18,
    "pill": 9999,
}

# ── Apple 间距阶梯（基准 8px）────────────────────────────────
SPACE = {
    "xxs": 4, "xs": 8, "sm": 12, "md": 17,
    "lg": 24, "xl": 32, "xxl": 48,
}


# ── 活动类别色（Apple 系统色族）───────────────────────────────
# Apple 官网没有数据图表，因此规范未定义类别色。Dayflow 需要它们
# 来区分活动类型 —— 这里取 Apple 系统色的两个明度档：
#   浅色主题用深一档（AA 小字号 ≥ 4.5:1）
#   深色主题用亮一档（AA 小字号 ≥ 4.5:1）
# 全部 16 个值已按 WCAG 实测通过，详见 docs。
# 类别名始终以文字出现，颜色只做辅助，因此不额外要求色相分离度。
CATEGORY_COLORS_LIGHT = {
    "工作": "#0A6ED1",
    "Work": "#0A6ED1",
    "学习": "#5B21B6",
    "Study": "#5B21B6",
    "编程": "#0F7A4A",
    "Coding": "#0F7A4A",
    "会议": "#96590A",
    "Meeting": "#96590A",
    "娱乐": "#B3215E",
    "Entertainment": "#B3215E",
    "社交": "#0E7490",
    "Social": "#0E7490",
    "休息": "#6E6E73",
    "Break": "#6E6E73",
    "其他": "#6B6B70",
    "Other": "#6B6B70",
}

CATEGORY_COLORS_DARK = {
    "工作": "#4CA3FF",
    "Work": "#4CA3FF",
    "学习": "#A78BFA",
    "Study": "#A78BFA",
    "编程": "#3DD68C",
    "Coding": "#3DD68C",
    "会议": "#EFB93B",
    "Meeting": "#EFB93B",
    "娱乐": "#FF6E9C",
    "Entertainment": "#FF6E9C",
    "社交": "#4FD0E3",
    "Social": "#4FD0E3",
    "休息": "#AEAEAE",
    "Break": "#AEAEAE",
    "其他": "#B3B3B8",
    "Other": "#B3B3B8",
}

# 指标色（统计页环形图/柱状图）—— 同样取 Apple 系统色族
METRIC_COLORS_LIGHT = {
    "time": "#0A6ED1",
    "efficiency": "#0F7A4A",
    "deep_work": "#5B21B6",
    "activities": "#96590A",
}

METRIC_COLORS_DARK = {
    "time": "#4CA3FF",
    "efficiency": "#3DD68C",
    "deep_work": "#A78BFA",
    "activities": "#EFB93B",
}

# 图例/展示顺序（仅中文，不含英文别名）
CATEGORY_ORDER = ["工作", "编程", "学习", "会议", "娱乐", "社交", "休息", "其他"]



class ThemeManager(QObject):
    """主题管理器"""
    
    theme_changed = Signal(object)  # 传递 Theme 对象
    
    _instance: Optional['ThemeManager'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._current_theme = DARK_THEME
        self._initialized = True
    
    @property
    def current_theme(self) -> Theme:
        return self._current_theme
    
    @property
    def is_dark(self) -> bool:
        return self._current_theme.name == "dark"
    
    def set_theme(self, theme: Theme):
        """设置主题"""
        if self._current_theme == theme:
            return  # 避免重复切换
        self._current_theme = theme
        self._apply_global_theme()
        self.theme_changed.emit(theme)
    
    def toggle_theme(self):
        """切换主题"""
        if self.is_dark:
            self.set_theme(LIGHT_THEME)
        else:
            self.set_theme(DARK_THEME)
    
    def _apply_global_theme(self):
        """应用全局样式"""
        app = QApplication.instance()
        if app:
            app.setStyleSheet(self.get_global_stylesheet())
    
    def get_global_stylesheet(self) -> str:
        """生成全局样式表"""
        t = self._current_theme
        r_sm = RADIUS["sm"]
        r_md = RADIUS["md"]
        r_pill = RADIUS["pill"]
        focus = t.accent_focus
        return f"""
            /* ===== 全局基础 ===== */
            QMainWindow {{
                background-color: {t.bg_primary};
            }}
            
            QWidget {{
                color: {t.text_primary};
                font-family: "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", -apple-system, sans-serif;
                font-size: 15px;
            }}
            
            /* ===== 滚动条 ===== */
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            
            QScrollBar:vertical {{
                width: 8px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {t.scrollbar};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t.scrollbar_hover};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            
            /* ===== 输入框（药丸形，Apple 搜索框语法）===== */
            QLineEdit, QTextEdit, QPlainTextEdit {{
                background-color: {t.bg_tertiary};
                border: 1px solid {t.border};
                border-radius: {r_pill}px;
                padding: 10px 16px;
                color: {t.text_primary};
                font-size: 15px;
                selection-background-color: {t.accent};
                selection-color: #FFFFFF;
            }}
            QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover {{
                border-color: {t.border_hover};
            }}
            /* Apple 规范：焦点环 2px Action Blue，全局不可省 */
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border: 2px solid {focus};
                padding: 9px 15px;
            }}
            QLineEdit::placeholder {{
                color: {t.text_muted};
            }}
            
            /* ===== 按钮（紧凑工具 sm 圆角）===== */
            QPushButton {{
                background-color: {t.bg_tertiary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: {r_sm}px;
                padding: 8px 16px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {t.bg_hover};
                border-color: {t.border_hover};
            }}
            QPushButton:pressed {{
                background-color: {t.pressed};
            }}
            QPushButton:focus {{
                border: 2px solid {focus};
                background-color: {t.bg_hover};
            }}
            QPushButton:focus:hover {{
                border: 2px solid {focus};
            }}
            QPushButton:focus:pressed {{
                border: 2px solid {focus};
                background-color: {t.pressed};
            }}
            QPushButton:disabled {{
                background-color: {t.bg_primary};
                color: {t.text_muted};
                border: 1px solid {t.border};
            }}
            /* 选中态（如已勾选的筛选药丸）也走 Apple 蓝 */
            QPushButton:checked {{
                background-color: {t.accent};
                color: #FFFFFF;
                border: 1px solid {t.accent};
            }}
            QPushButton:checked:hover {{
                background-color: {t.accent_hover};
                border: 1px solid {t.accent_hover};
            }}
            QPushButton:checked:focus {{
                border: 2px solid {focus};
            }}
            
            /* ===== 下拉框 / 数字框 ===== */
            QComboBox, QSpinBox, QDateEdit {{
                background-color: {t.bg_tertiary};
                border: 1px solid {t.border};
                border-radius: {r_sm}px;
                padding: 8px 12px;
                color: {t.text_primary};
                font-size: 14px;
                min-height: 20px;
            }}
            QComboBox:hover, QSpinBox:hover, QDateEdit:hover {{
                border-color: {t.border_hover};
            }}
            QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{
                border: 2px solid {focus};
                padding: 7px 11px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: {r_sm}px;
                padding: 4px;
                selection-background-color: {t.accent};
                selection-color: #FFFFFF;
                outline: none;
            }}
            QComboBox QAbstractItemView::item {{
                padding: 6px 10px;
                border-radius: 6px;
                min-height: 24px;
            }}
            
            /* ===== 复选框 ===== */
            QCheckBox, QRadioButton {{
                color: {t.text_primary};
                font-size: 14px;
                spacing: 8px;
                min-height: 24px;
            }}
            QCheckBox:focus, QRadioButton:focus {{
                color: {t.accent};
            }}
            
            /* ===== 进度条 ===== */
            QProgressBar {{
                background-color: {t.bg_primary};
                border: none;
                border-radius: 6px;
                text-align: center;
                color: {t.text_secondary};
                font-size: 12px;
            }}
            QProgressBar::chunk {{
                background-color: {t.accent};
                border-radius: 6px;
            }}
            
            /* ===== 分组框 ===== */
            QGroupBox {{
                border: 1px solid {t.border};
                border-radius: {r_md}px;
                margin-top: 14px;
                padding-top: 10px;
                font-size: 14px;
                font-weight: 600;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0 6px;
                color: {t.text_secondary};
            }}
            
            /* ===== 工具提示 ===== */
            QToolTip {{
                background-color: {t.bg_secondary};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: {r_sm}px;
                padding: 6px 10px;
                font-size: 13px;
            }}
            
            /* ===== 消息框 ===== */
            QMessageBox {{
                background-color: {t.bg_secondary};
            }}
            QMessageBox QLabel {{
                color: {t.text_primary};
            }}
            QMessageBox QPushButton {{
                min-width: 88px;
                padding: 8px 20px;
            }}
            
            /* ===== 菜单 ===== */
            QMenu {{
                background-color: {t.bg_secondary};
                border: 1px solid {t.border};
                border-radius: {r_sm}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 6px;
                color: {t.text_primary};
            }}
            QMenu::item:selected {{
                background-color: {t.accent};
                color: #FFFFFF;
            }}
            QMenu::item:disabled {{
                color: {t.text_muted};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {t.divider};
                margin: 4px 8px;
            }}
        """


# 全局函数
def get_theme_manager() -> ThemeManager:
    """获取主题管理器实例"""
    return ThemeManager()


def get_efficiency_color(score: float, theme: 'Theme' = None) -> str:
    """根据效率分数获取对应颜色
    
    Args:
        score: 效率分数 (0-100)
        theme: 主题对象，默认使用当前主题
    
    Returns:
        颜色值字符串
    """
    if theme is None:
        theme = get_theme()
    
    if score >= 70:
        return theme.success  # 绿色 - 高效
    elif score >= 40:
        return theme.warning  # 橙色 - 中等
    else:
        return theme.text_muted  # 灰色 - 低效


def get_theme() -> Theme:
    """获取当前主题"""
    return get_theme_manager().current_theme


def is_dark_theme() -> bool:
    """是否为暗色主题"""
    return get_theme_manager().is_dark


def font_spec(role: str) -> str:
    """
    返回 Apple 排版阶梯中某一级的 QSS font 片段。

    Apple 规范的核心是「Apple tight」——17px 以上字号带负字距。
    Qt 的 QSS 支持 letter-spacing，这里直接落地。

    Args:
        role: TYPE_SCALE 的键，如 "title" / "body" / "caption"
    """
    size, weight, tracking = TYPE_SCALE[role]
    return f"font-size: {size}px; font-weight: {weight}; letter-spacing: {tracking}px;"


def apply_type_role(widget, role: str):
    """
    给 QWidget / QLabel 套用 Apple 排版阶梯（用 QFont 以获得真实字距渲染）。

    QSS 的 letter-spacing 在部分控件上不生效，因此正文类控件走 QFont。
    """
    from PySide6.QtGui import QFont

    size, weight, tracking = TYPE_SCALE[role]
    font = widget.font()
    font.setPointSize(size)
    font.setWeight(QFont.Weight(weight))
    if tracking:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking)
    widget.setFont(font)


def get_category_colors(theme: 'Theme' = None) -> dict:
    """返回当前主题下的活动类别色表（含英文别名）"""
    t = theme or get_theme()
    return CATEGORY_COLORS_DARK if t.name == "dark" else CATEGORY_COLORS_LIGHT


def get_display_categories(theme: 'Theme' = None) -> dict:
    """
    返回仅含中文类别的色表（有序），供图例等需要展示的场景使用。

    get_category_colors() 带英文别名，是给按类别名取色的查找表用的；
    直接拿去画图例会多出一倍条目。
    """
    t = theme or get_theme()
    full = CATEGORY_COLORS_DARK if t.name == "dark" else CATEGORY_COLORS_LIGHT
    return {name: full[name] for name in CATEGORY_ORDER if name in full}


def get_category_color(category: str, theme: 'Theme' = None) -> str:
    """获取类别对应的颜色（跟随当前主题明度档）"""
    t = theme or get_theme()
    table = CATEGORY_COLORS_DARK if t.name == "dark" else CATEGORY_COLORS_LIGHT
    return table.get(category, table.get("其他", "#6E6E73"))


def get_metric_colors(theme: 'Theme' = None) -> dict:
    """返回当前主题下的指标色表（统计图表用）"""
    t = theme or get_theme()
    return METRIC_COLORS_DARK if t.name == "dark" else METRIC_COLORS_LIGHT


def with_alpha(hex_color: str, alpha: float) -> str:
    """
    把 #RRGGBB 转成 rgba(r, g, b, a)。

    注意：Qt 的 8 位十六进制是 #AARRGGBB（alpha 在前），不是 CSS 的 #RRGGBBAA。
    直接在颜色后面拼 "18" 想加透明度，会被当成 #AARRGGBB 解析 ——
    结果是色相整个错掉。因此所有半透明底色都必须走这个函数。
    """
    h = hex_color.lstrip("#")
    if len(h) == 8:  # 已经是 #AARRGGBB
        h = h[2:]
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def get_markdown_stylesheet(theme: Optional[Theme] = None) -> str:
    """
    生成适用于 QTextBrowser / QTextDocument 的 Markdown CSS。
    按 Apple 规范：正文 400 字重 / 1.47 行高，标题 600 + 负字距。
    """
    t = theme or get_theme()
    is_dark = (t.name == "dark")
    
    quote_bg = t.accent_light
    quote_border = t.accent
    code_bg = t.bg_tertiary if is_dark else t.bg_primary
    table_header_bg = t.bg_tertiary if is_dark else t.bg_primary
    table_row_alt = t.bg_hover if is_dark else t.bg_primary
    r_sm = RADIUS["sm"]
    r_md = RADIUS["md"]
    
    return f"""
        body {{
            color: {t.text_primary};
            font-family: "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", -apple-system, sans-serif;
            font-size: 15px;
            font-weight: 400;
            line-height: 1.47;
            padding: 8px;
        }}
        h1 {{
            color: {t.text_primary};
            font-size: 24px;
            font-weight: 600;
            letter-spacing: -0.20px;
            line-height: 1.14;
            margin-top: 20px;
            margin-bottom: 12px;
        }}
        h2 {{
            color: {t.text_primary};
            font-size: 20px;
            font-weight: 600;
            letter-spacing: -0.15px;
            line-height: 1.19;
            margin-top: 20px;
            margin-bottom: 10px;
        }}
        h3 {{
            color: {t.text_primary};
            font-size: 17px;
            font-weight: 600;
            letter-spacing: -0.20px;
            line-height: 1.24;
            margin-top: 14px;
            margin-bottom: 6px;
        }}
        h4 {{
            color: {t.text_secondary};
            font-size: 15px;
            font-weight: 600;
            line-height: 1.29;
            margin-top: 10px;
            margin-bottom: 4px;
        }}
        p {{
            margin-top: 6px;
            margin-bottom: 8px;
            line-height: 1.47;
        }}
        blockquote {{
            margin: 12px 0;
            padding: 12px 16px;
            background-color: {quote_bg};
            border-left: 3px solid {quote_border};
            border-radius: {r_sm}px;
            color: {t.text_primary};
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 14px 0;
            font-size: 14px;
        }}
        th {{
            background-color: {table_header_bg};
            color: {t.text_primary};
            font-weight: 600;
            border-bottom: 1px solid {t.border};
            padding: 10px 12px;
            text-align: left;
        }}
        td {{
            border-bottom: 1px solid {t.divider};
            padding: 10px 12px;
            color: {t.text_secondary};
        }}
        code {{
            font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
            font-size: 13px;
            background-color: {code_bg};
            color: {t.accent};
            padding: 2px 6px;
            border-radius: 5px;
        }}
        pre {{
            font-family: "Cascadia Code", "Consolas", monospace;
            font-size: 13px;
            background-color: {code_bg};
            border: 1px solid {t.border};
            border-radius: {r_sm}px;
            padding: 12px;
            margin: 12px 0;
        }}
        hr {{
            border: none;
            border-top: 1px solid {t.divider};
            margin: 20px 0;
        }}
        ul, ol {{
            margin: 6px 0;
            padding-left: 24px;
        }}
        li {{
            margin-bottom: 4px;
            line-height: 1.47;
        }}
        strong {{
            color: {t.text_primary};
            font-weight: 600;
        }}
    """
