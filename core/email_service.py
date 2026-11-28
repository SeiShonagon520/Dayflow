"""
Dayflow - 邮件推送服务
支持 QQ 邮箱定时发送效率报告，含 AI 点评功能
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import html
import logging
import re
import smtplib
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

import config
from core.activity_time import ledger_days, split_hours, summarize_activities
from core.llm_provider import DayflowBackendProvider

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """邮箱配置"""
    smtp_server: str = "smtp.qq.com"
    smtp_port: int = 465
    sender_email: str = ""
    auth_code: str = ""  # QQ邮箱授权码
    receiver_email: str = ""
    enabled: bool = False


class EmailService:
    """邮件服务"""
    
    def __init__(self, config: EmailConfig):
        self.config = config
    
    def send_report(self, subject: str, html_content: str) -> tuple:
        """发送 HTML 报告邮件，返回 (成功, 错误信息)"""
        if not self.config.enabled:
            return False, "邮件推送未启用"
        
        if not all([self.config.sender_email, self.config.auth_code, self.config.receiver_email]):
            return False, "邮箱配置不完整"
        
        try:
            # 创建邮件
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.config.sender_email
            msg["To"] = self.config.receiver_email
            
            # 添加 HTML 内容
            html_part = MIMEText(html_content, "html", "utf-8")
            msg.attach(html_part)
            
            # 发送邮件
            logger.info(f"正在连接 SMTP 服务器: {self.config.smtp_server}:{self.config.smtp_port}")
            server = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port,
                                     timeout=30, context=ssl.create_default_context())
            try:
                logger.info("SMTP 连接成功，正在登录...")
                server.login(self.config.sender_email, self.config.auth_code)
                logger.info("登录成功，正在发送邮件...")
                server.sendmail(
                    self.config.sender_email,
                    self.config.receiver_email,
                    msg.as_string()
                )
                # sendmail 成功 = 邮件已发送
                logger.info(f"邮件发送成功: {subject}")
                return True, ""
            finally:
                # 忽略 quit() 时的错误（QQ 邮箱可能返回非标准响应）
                try:
                    server.quit()
                except Exception:
                    pass
            
        except smtplib.SMTPAuthenticationError as e:
            error_msg = "授权码错误或SMTP服务未开启"
            logger.error(f"SMTP认证失败: {e}")
            return False, error_msg
        except smtplib.SMTPConnectError as e:
            error_msg = "无法连接SMTP服务器，请检查网络"
            logger.error(f"SMTP连接失败: {e}")
            return False, error_msg
        except TimeoutError:
            error_msg = "连接超时，请检查网络或端口是否被封锁"
            logger.error("SMTP连接超时")
            return False, error_msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"邮件发送失败: {e}")
            return False, error_msg


class DeepAnalyzer:
    """
    深度数据分析器 - 纯数据驱动，不做主观臆断
    
    注意：原始 cards 是每分钟一条记录（系统设计），需要合并成真正的工作段
    """
    
    def __init__(self, cards: list):
        self.cards = cards
        self.sorted_cards = sorted(
            [c for c in cards if c.start_time], 
            key=lambda x: x.start_time
        )
        # 合并连续同类型记录为真正的工作段
        self.merged_sessions = self._merge_consecutive_cards()
    
    def _merge_consecutive_cards(self) -> list:
        """
        将连续的同类型记录合并成真正的工作段
        
        例如：10个连续的"编程"卡片 → 1个10分钟的编程工作段
        
        注意：如果两张卡片之间的时间间隔超过 5 分钟，即使类别相同也视为不同工作段
        """
        if not self.sorted_cards:
            return []
        
        # 时间间隔阈值（分钟）- 超过此值视为不同工作段
        GAP_THRESHOLD_MINUTES = 5
        
        sessions = []
        current_session = {
            'category': self.sorted_cards[0].category,
            'start_time': self.sorted_cards[0].start_time,
            'end_time': self.sorted_cards[0].end_time,
            'duration': self.sorted_cards[0].duration_minutes,
            'scores': [self.sorted_cards[0].productivity_score] if self.sorted_cards[0].productivity_score > 0 else []
        }
        
        for card in self.sorted_cards[1:]:
            # 计算与上一张卡片的时间间隔
            time_gap = 0
            if current_session['end_time'] and card.start_time:
                time_gap = (card.start_time - current_session['end_time']).total_seconds() / 60
            
            # 如果类别相同且时间间隔在阈值内，合并到当前工作段
            if card.category == current_session['category'] and time_gap <= GAP_THRESHOLD_MINUTES:
                current_session['duration'] += card.duration_minutes
                current_session['end_time'] = card.end_time
                if card.productivity_score > 0:
                    current_session['scores'].append(card.productivity_score)
            else:
                # 类别不同或时间间隔过大，保存当前工作段，开始新的
                current_session['avg_score'] = int(sum(current_session['scores']) / len(current_session['scores'])) if current_session['scores'] else 0
                sessions.append(current_session)
                current_session = {
                    'category': card.category,
                    'start_time': card.start_time,
                    'end_time': card.end_time,
                    'duration': card.duration_minutes,
                    'scores': [card.productivity_score] if card.productivity_score > 0 else []
                }
        
        # 保存最后一个工作段
        current_session['avg_score'] = int(sum(current_session['scores']) / len(current_session['scores'])) if current_session['scores'] else 0
        sessions.append(current_session)
        
        return sessions
    
    def analyze(self) -> dict:
        """执行完整的深度分析，返回结构化数据"""
        return {
            'focus': self._analyze_focus(),
            'rhythm': self._analyze_rhythm(),
            'switching': self._analyze_switching(),
            'categories': self._analyze_categories(),
            'day_type': self._classify_day_type(),
        }
    
    def _analyze_focus(self) -> dict:
        """专注力分析 - 基于合并后的真实工作段"""
        if not self.merged_sessions:
            return {'has_data': False}
        
        durations = [s['duration'] for s in self.merged_sessions if s['duration'] > 0]
        if not durations:
            return {'has_data': False}
        
        # 时长分布统计（基于真实工作段）
        fragments = [d for d in durations if d < 15]  # <15分钟
        deep = [d for d in durations if d >= 60]  # >60分钟（深度工作）
        
        # 找最长的那次
        max_duration = max(durations)
        max_session = None
        for s in self.merged_sessions:
            if s['duration'] == max_duration:
                max_session = {
                    'category': s['category'],
                    'duration': int(max_duration),
                    'time': s['start_time'].strftime('%H:%M') if s['start_time'] else ''
                }
                break
        
        return {
            'has_data': True,
            'total_sessions': len(self.merged_sessions),  # 真实工作段数量
            'fragment_count': len(fragments),  # 碎片数量
            'fragment_percent': int(len(fragments) / len(durations) * 100) if durations else 0,
            'deep_count': len(deep),  # 深度工作次数
            'deep_total_mins': int(sum(deep)),  # 深度工作总时长
            'max_session': max_session,
            'avg_duration': int(sum(durations) / len(durations))
        }
    
    def _analyze_rhythm(self) -> dict:
        """工作节奏分析 - 按时段统计"""
        hourly_data = {}
        periods = {}
        names = ["凌晨(0-6)", "上午(6-12)", "下午(12-18)", "晚上(18-24)"]
        for card in self.sorted_cards:
            if not card.start_time or not card.end_time or card.productivity_score <= 0:
                continue
            for hour, minutes in split_hours(card):
                hours = hourly_data.setdefault(hour, [0.0, 0.0])
                period = periods.setdefault(names[hour // 6], [0.0, 0.0, set()])
                hours[0] += card.productivity_score * minutes
                hours[1] += minutes
                period[0] += card.productivity_score * minutes
                period[1] += minutes
                period[2].add(id(card))

        if not hourly_data:
            return {"has_data": False}
        hourly_avg = {hour: round(points / minutes, 1) for hour, (points, minutes) in hourly_data.items()}
        peak_hour = max(hourly_avg, key=hourly_avg.get)
        low_hour = min(hourly_avg, key=hourly_avg.get)
        period_stats = {
            name: {"avg_score": round(points / minutes, 1), "total_mins": round(minutes, 1),
                   "session_count": len(cards)}
            for name, (points, minutes, cards) in periods.items()
        }

        return {
            'has_data': True,
            'hourly_avg': hourly_avg,
            'peak_hour': peak_hour,
            'peak_score': hourly_avg[peak_hour],
            'low_hour': low_hour,
            'low_score': hourly_avg[low_hour],
            'periods': period_stats
        }
    
    def _analyze_switching(self) -> dict:
        """任务切换分析 - 基于合并后的真实工作段"""
        if len(self.merged_sessions) < 2:
            return {'has_data': False, 'total_switches': 0}
        
        # 切换次数 = 工作段数量 - 1
        switches = []
        for i in range(1, len(self.merged_sessions)):
            prev = self.merged_sessions[i-1]
            curr = self.merged_sessions[i]
            switches.append({
                'time': curr['start_time'].strftime('%H:%M') if curr['start_time'] else '',
                'from': prev['category'],
                'to': curr['category']
            })
        
        # 统计切换频率
        from collections import Counter
        switch_pairs = Counter(f"{s['from']}→{s['to']}" for s in switches)
        most_common = switch_pairs.most_common(3)
        
        return {
            'has_data': True,
            'total_switches': len(switches),
            'common_patterns': most_common
        }
    
    def _analyze_categories(self) -> dict:
        """类别效率分析 - 基于合并后的真实工作段"""
        from collections import defaultdict
        
        cat_data = defaultdict(lambda: {'scores': [], 'minutes': 0, 'sessions': 0})
        
        for session in self.merged_sessions:
            cat = session['category'] or '其他'
            if session['avg_score'] > 0:
                cat_data[cat]['scores'].append(session['avg_score'])
            cat_data[cat]['minutes'] += session['duration']
            cat_data[cat]['sessions'] += 1
        
        if not cat_data:
            return {'has_data': False}
        
        # 计算每个类别的统计
        cat_stats = {}
        for cat, data in cat_data.items():
            avg_score = int(sum(data['scores'])/len(data['scores'])) if data['scores'] else 0
            cat_stats[cat] = {
                'avg_score': avg_score,
                'total_mins': int(data['minutes']),
                'session_count': data['sessions'],  # 真实工作段数量
                'score_variance': self._calc_variance(data['scores']) if len(data['scores']) > 1 else 0
            }
        
        # 找最高效和最低效
        scored_cats = {k: v for k, v in cat_stats.items() if v['avg_score'] > 0}
        best_cat = max(scored_cats, key=lambda x: scored_cats[x]['avg_score']) if scored_cats else None
        worst_cat = min(scored_cats, key=lambda x: scored_cats[x]['avg_score']) if scored_cats else None
        
        return {
            'has_data': True,
            'stats': cat_stats,
            'best': best_cat,
            'worst': worst_cat
        }
    
    def _calc_variance(self, scores: list) -> int:
        """计算分数波动（标准差）"""
        if len(scores) < 2:
            return 0
        avg = sum(scores) / len(scores)
        variance = sum((s - avg) ** 2 for s in scores) / len(scores)
        return int(variance ** 0.5)
    
    def _classify_day_type(self) -> dict:
        """基于数据判断今日类型"""
        focus = self._analyze_focus()
        switching = self._analyze_switching()
        
        if not focus.get('has_data'):
            return {'type': '数据不足', 'description': '记录较少，无法分类'}
        
        deep_count = focus.get('deep_count', 0)
        fragment_percent = focus.get('fragment_percent', 0)
        switch_count = switching.get('total_switches', 0)
        
        # 基于数据的客观分类
        if deep_count >= 2 and fragment_percent < 30:
            return {'type': '深度工作日', 'indicators': f'{deep_count}次深度工作，碎片仅{fragment_percent}%'}
        elif switch_count >= 8:
            return {'type': '多任务切换日', 'indicators': f'切换{switch_count}次'}
        elif fragment_percent > 60:
            return {'type': '碎片化日', 'indicators': f'{fragment_percent}%为碎片时间'}
        elif deep_count == 0 and focus.get('avg_duration', 0) < 20:
            return {'type': '轻量日', 'indicators': f'平均每段{focus.get("avg_duration", 0)}分钟'}
        else:
            return {'type': '常规日', 'indicators': '节奏正常'}


class AICommentGenerator:
    """AI 点评生成器 - 基于深度数据"""
    
    # 朋友式点评 Prompt
    COMMENT_PROMPT = """你是用户的一个懂时间管理的朋友。下面是他今天的时间记录数据，请基于【客观数据】写一段点评。

【写作风格】
- 像发微信语音转文字那样自然，可以用口语化表达
- 开头别用"今天"，换个角度切入（比如从某个有趣的数据点开始）
- 别总结数据，而是说出数据背后有意思的发现
- 别给建议，除非数据明显指向某个问题

【禁止使用】
- "继续保持"、"加油"、"相信你"、"明天会更好" 等鸡汤
- "今天你..."、"从数据来看..." 等套路开头
- 过多 emoji（最多1个，放结尾）
- 任何形式的猜测（"可能是因为..."）

【今日数据】
日期：{date}
记录时长：{recorded_time}
综合效率：{score}分
时间分布：{categories}

【专注力数据】
{focus_data}

【工作节奏数据】
{rhythm_data}

【任务切换数据】
{switching_data}

【类别效率数据】
{category_data}

【今日类型】
{day_type}

【输出要求】
- 100-150字
- 直接输出，不要标题
- 说人话，别像 AI"""

    # 专业深度分析 Prompt
    ANALYSIS_PROMPT = """你是一位专业的时间管理与行为分析专家。请基于以下用户今日的活动数据，撰写一份专业的深度分析报告。

【数据说明】
- "工作段"是指连续做同一类事情的时间段（系统自动识别并合并）
- 切换次数是指在不同类别之间切换的次数
- 效率分数基于屏幕活动的专注程度评估

【今日原始数据】
日期：{date}
总记录时长：{recorded_time}
综合效率评分：{score}分
今日类型：{day_type}
时间分布：{categories}

【专注力指标】
{focus_data}

【时段效率数据】
{rhythm_data}

【任务切换数据】
{switching_data}

【类别效率对比】
{category_data}

【分析要求】
请从以下维度进行深度分析，输出专业报告：

1. **行为模式诊断**
   - 今日的工作模式属于什么类型？（深度工作型/碎片化/多任务切换型）
   - 这种模式的利弊是什么？

2. **效率瓶颈识别**
   - 基于数据，找出今日效率的主要瓶颈点
   - 哪些时段或行为拖累了整体效率？

3. **优势与亮点**
   - 今日做得好的方面（用数据支撑）
   - 可以继续保持的良好习惯

4. **改进策略**（具体可执行）
   - 基于今日数据，给出2-3条针对性的改进建议
   - 建议要具体、可量化、可操作

【输出格式】
- 使用专业、客观的语言
- 分析要有数据支撑，避免空泛
- 总字数300-500字
- 使用 Markdown 格式，包含小标题
- 直接输出分析内容，不要有任何前言"""

    def __init__(self, storage=None):
        self.storage = storage

    def _setting(self, key: str, fallback: str) -> str:
        if self.storage and hasattr(self.storage, "get_setting"):
            value = self.storage.get_setting(key, "")
            if value:
                return value
        return fallback

    def _build_provider(self, timeout: float) -> DayflowBackendProvider:
        api_base_url = self._setting("api_url", config.API_BASE_URL)
        api_key = self._setting("api_key", config.API_KEY)
        model = self._setting("api_model", config.API_MODEL)
        return DayflowBackendProvider(
            api_base_url=api_base_url,
            api_key=api_key,
            model=model,
            timeout=timeout,
        )

    @staticmethod
    def _format_prompt_fields(stats: dict, deep_analysis: dict, *, detailed: bool) -> dict:
        total_mins = int(round(stats['recorded_minutes']))
        recorded_h, recorded_m = divmod(total_mins, 60)

        categories_str = "、".join(
            f"{cat}({int(m) // 60}h{int(m) % 60}m)"
            for cat, m in stats['categories'][:5]
        ) if stats['categories'] else "无记录"

        focus = deep_analysis.get('focus', {})
        rhythm = deep_analysis.get('rhythm', {})
        switching = deep_analysis.get('switching', {})
        categories = deep_analysis.get('categories', {})
        day_type = deep_analysis.get('day_type', {})

        if focus.get('has_data'):
            max_session = focus['max_session']
            if detailed:
                focus_data = (
                    f"- 工作段数量: {focus['total_sessions']}段\n"
                    f"- 碎片工作(<15min): {focus['fragment_count']}段，占比{focus['fragment_percent']}%\n"
                    f"- 深度工作(>60min): {focus['deep_count']}段，累计{focus['deep_total_mins']}分钟\n"
                    f"- 最长单次专注: {max_session['duration']}分钟（{max_session['category']}，{max_session['time']}开始）\n"
                    f"- 平均工作段时长: {focus['avg_duration']}分钟"
                )
            else:
                focus_data = (
                    f"- 总共 {focus['total_sessions']} 段工作\n"
                    f"- 碎片(<15分钟): {focus['fragment_count']}段，占{focus['fragment_percent']}%\n"
                    f"- 深度工作(>60分钟): {focus['deep_count']}段，共{focus['deep_total_mins']}分钟\n"
                    f"- 最长一段: {max_session['duration']}分钟（{max_session['category']}，{max_session['time']}）\n"
                    f"- 平均每段: {focus['avg_duration']}分钟"
                )
        else:
            focus_data = "数据不足，无法分析" if detailed else "数据不足"

        if rhythm.get('has_data'):
            if detailed:
                period_lines = [
                    f"- {name}: 效率均分{data['avg_score']}分，工作{data['total_mins']}分钟，{data['session_count']}个工作段"
                    for name, data in rhythm.get('periods', {}).items()
                ]
                rhythm_data = "\n".join(period_lines) if period_lines else "数据不足"
                rhythm_data += f"\n- 效率峰值: {rhythm['peak_hour']}:00（{rhythm['peak_score']}分）"
                rhythm_data += f"\n- 效率低谷: {rhythm['low_hour']}:00（{rhythm['low_score']}分）"
                rhythm_data += f"\n- 峰谷差值: {round(rhythm['peak_score'] - rhythm['low_score'], 1)}分"
            else:
                period_lines = [
                    f"- {name}: 均分{data['avg_score']}，共{data['total_mins']}分钟"
                    for name, data in rhythm.get('periods', {}).items()
                ]
                rhythm_data = "\n".join(period_lines) if period_lines else "数据不足"
                rhythm_data += f"\n- 效率最高时段: {rhythm['peak_hour']}点（{rhythm['peak_score']}分）"
                rhythm_data += f"\n- 效率最低时段: {rhythm['low_hour']}点（{rhythm['low_score']}分）"
        else:
            rhythm_data = "数据不足，无法分析" if detailed else "数据不足"

        if switching.get('has_data'):
            if detailed:
                switching_data = f"- 类别切换总次数: {switching['total_switches']}次"
                if switching.get('common_patterns'):
                    patterns = [f"{p[0]}（{p[1]}次）" for p in switching['common_patterns']]
                    switching_data += f"\n- 高频切换模式: {', '.join(patterns)}"
            else:
                switching_data = f"- 总切换次数: {switching['total_switches']}次"
                if switching.get('common_patterns'):
                    patterns = [f"{p[0]}({p[1]}次)" for p in switching['common_patterns']]
                    switching_data += f"\n- 常见切换: {', '.join(patterns)}"
        else:
            switching_data = "切换极少或无数据" if detailed else "切换较少或无数据"

        if categories.get('has_data'):
            if detailed:
                cat_lines = []
                for cat, data in sorted(
                    categories.get('stats', {}).items(),
                    key=lambda x: x[1]['total_mins'],
                    reverse=True,
                ):
                    variance_text = f"，波动±{data['score_variance']}" if data['score_variance'] > 0 else ""
                    cat_lines.append(
                        f"- {cat}: 效率{data['avg_score']}分{variance_text}，{data['session_count']}段共{data['total_mins']}分钟"
                    )
                category_data = "\n".join(cat_lines[:6])
                if categories.get('best') and categories.get('worst') and categories['best'] != categories['worst']:
                    best_data = categories['stats'].get(categories['best'], {})
                    worst_data = categories['stats'].get(categories['worst'], {})
                    diff = best_data.get('avg_score', 0) - worst_data.get('avg_score', 0)
                    category_data += f"\n- 效率最高: {categories['best']}（{best_data.get('avg_score', 0)}分）"
                    category_data += f"\n- 效率最低: {categories['worst']}（{worst_data.get('avg_score', 0)}分）"
                    category_data += f"\n- 类别效率差: {diff}分"
            else:
                cat_lines = [
                    f"- {cat}: 均分{data['avg_score']}，{data['session_count']}段共{data['total_mins']}分钟"
                    for cat, data in categories.get('stats', {}).items()
                ]
                category_data = "\n".join(cat_lines[:5])
                if categories.get('best') and categories.get('worst') and categories['best'] != categories['worst']:
                    category_data += f"\n- 效率最高: {categories['best']}，最低: {categories['worst']}"
        else:
            category_data = "数据不足，无法分析" if detailed else "数据不足"

        return {
            "date": stats['date'],
            "recorded_time": f"{recorded_h}小时{recorded_m}分钟",
            "score": stats['score'],
            "categories": categories_str,
            "focus_data": focus_data,
            "rhythm_data": rhythm_data,
            "switching_data": switching_data,
            "category_data": category_data,
            "day_type": f"{day_type.get('type', '常规日')}（{day_type.get('indicators', '')}）",
        }

    def generate_comment(self, stats: dict, deep_analysis: dict) -> str:
        """生成 AI 点评"""
        try:
            prompt = self.COMMENT_PROMPT.format(
                **self._format_prompt_fields(stats, deep_analysis, detailed=False)
            )
            comment = self._call_provider(prompt, max_tokens=200)
            return comment if comment else self._fallback_comment(stats, deep_analysis)
        except Exception as e:
            logger.error(f"AI 点评生成失败: {e}")
            return self._fallback_comment(stats, deep_analysis)

    def generate_deep_analysis(self, stats: dict, deep_analysis: dict) -> str:
        """生成专业深度分析报告"""
        try:
            prompt = self.ANALYSIS_PROMPT.format(
                **self._format_prompt_fields(stats, deep_analysis, detailed=True)
            )
            analysis = self._call_provider(prompt, max_tokens=1500)
            return analysis if analysis else self._fallback_analysis(deep_analysis)
        except Exception as e:
            logger.error(f"深度分析生成失败: {e}")
            return self._fallback_analysis(deep_analysis)
    
    def _fallback_analysis(self, deep_analysis: dict) -> str:
        """深度分析降级方案"""
        focus = deep_analysis.get('focus', {})
        rhythm = deep_analysis.get('rhythm', {})
        switching = deep_analysis.get('switching', {})
        day_type = deep_analysis.get('day_type', {})
        
        lines = ["### 行为模式"]
        
        dtype = day_type.get('type', '常规日')
        lines.append(f"今日属于 **{dtype}**。{day_type.get('indicators', '')}")
        
        if focus.get('has_data'):
            lines.append("")
            lines.append("### 专注力表现")
            if focus.get('deep_count', 0) > 0:
                lines.append(f"- 完成了 {focus['deep_count']} 次深度工作（>60分钟），累计 {focus['deep_total_mins']} 分钟")
            lines.append(f"- 最长专注 {focus.get('max_session', {}).get('duration', 0)} 分钟")
            lines.append(f"- 碎片工作占比 {focus.get('fragment_percent', 0)}%")
        
        if rhythm.get('has_data'):
            lines.append("")
            lines.append("### 时段效率")
            lines.append(f"- 效率峰值在 {rhythm.get('peak_hour', '')}:00（{rhythm.get('peak_score', 0)}分）")
            lines.append(f"- 效率低谷在 {rhythm.get('low_hour', '')}:00（{rhythm.get('low_score', 0)}分）")
        
        if switching.get('has_data') and switching.get('total_switches', 0) > 0:
            lines.append("")
            lines.append("### 任务切换")
            lines.append(f"- 今日切换 {switching['total_switches']} 次")
        
        return "\n".join(lines)
    
    def _call_provider(self, prompt: str, max_tokens: int = 300) -> Optional[str]:
        """复用 DayflowBackendProvider 同步调用大模型接口（兼容 Ollama 与 Gemini 代理）。"""
        timeout = 30.0 if max_tokens > 500 else 15.0
        provider = self._build_provider(timeout=timeout)
        if not provider.api_key and not provider.is_ollama:
            return None

        async def _invoke() -> Optional[str]:
            try:
                content = await provider._chat_completion(
                    [{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=max_tokens,
                )
                return content.strip() if content else None
            finally:
                await provider.close()

        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(_invoke())
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _invoke()).result()
        except Exception as e:
            logger.warning(f"API 调用失败: {type(e).__name__}: {e}")
            return None
    
    def _fallback_comment(self, stats: dict, deep_analysis: dict) -> str:
        """降级方案：基于深度分析数据生成点评"""
        score = stats['score']
        recorded_h = int(round(stats['recorded_minutes'])) // 60
        categories = stats.get('categories', [])
        focus = deep_analysis.get('focus', {})
        day_type = deep_analysis.get('day_type', {})
        
        parts = []
        
        # 基于今日类型
        dtype = day_type.get('type', '')
        if dtype == '深度工作日':
            parts.append(f"今天是个深度工作日，{focus.get('deep_count', 0)}段超过60分钟的专注时间")
        elif dtype == '碎片化日':
            parts.append(f"今天时间比较碎片化，{focus.get('fragment_percent', 0)}%是短时间片段")
        elif dtype == '多任务切换日':
            parts.append("今天切换了不少任务类型，上下文切换成本不小")
        else:
            if score >= 70:
                parts.append(f"今天{recorded_h}小时的工作，综合效率{score}分，节奏不错")
            else:
                top_cat = categories[0][0] if categories else "工作"
                parts.append(f"今天主要在「{top_cat}」上花了时间")
        
        # 加一个数据亮点
        if focus.get('has_data') and focus.get('max_session'):
            ms = focus['max_session']
            parts.append(f"最长的一段是{ms['duration']}分钟的{ms['category']}（{ms['time']}开始）")
        
        return "。".join(parts) + " ✨"


class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, storage):
        self.storage = storage
        self.ai_generator = AICommentGenerator(storage)
    
    def generate_daily_report(self, date: datetime = None, *, use_ai: bool = False) -> str:
        """生成每日报告 HTML"""
        if date is None:
            date = datetime.now()
        
        day = date.date()
        cards = ledger_days(self.storage, day, day)[day]
        totals = summarize_activities(cards)
        total_minutes = totals["minutes"]
        avg_score = totals["avgScore"]
        sorted_stats = sorted(totals["categories"].items(), key=lambda item: -item[1])

        # 深度分析
        analyzer = DeepAnalyzer(cards)
        deep_analysis = analyzer.analyze()
        if deep_analysis["focus"].get("has_data"):
            deep_analysis["focus"]["deep_count"] = totals["deepWork"]
            deep_analysis["focus"]["deep_total_mins"] = round(totals["deepWorkMinutes"], 1)
        
        # 构建 AI 使用的统计数据
        ai_stats = {
            'date': f"{date.year:04d}年{date.month:02d}月{date.day:02d}日",
            'recorded_minutes': round(total_minutes, 1),
            'score': avg_score,
            'categories': [(cat, int(mins)) for cat, mins in sorted_stats]
        }
        
        ai_comment = self.ai_generator._fallback_comment(ai_stats, deep_analysis) if cards else "当天暂无活动记录。"
        expert_analysis = self.ai_generator._fallback_analysis(deep_analysis) if cards else ""
        if use_ai and cards:
            try:
                ai_comment = self.ai_generator.generate_comment(ai_stats, deep_analysis)
            except Exception:
                logger.warning("邮件日报的模型点评暂不可用")
            try:
                expert_analysis = self.ai_generator.generate_deep_analysis(ai_stats, deep_analysis)
            except Exception:
                logger.warning("邮件日报的模型分析暂不可用")
        
        # 生成 HTML（包含深度分析）
        return self._build_html(date, sorted_stats, total_minutes, avg_score, deep_analysis, ai_comment, expert_analysis)
    
    @staticmethod
    def _template_dir() -> Path:
        if getattr(sys, "frozen", False):
            base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            packed_dir = base_dir / "templates"
            if (packed_dir / "email_report.html").exists():
                return packed_dir
        dev_dir = Path(__file__).parent.parent / "templates"
        if (dev_dir / "email_report.html").exists():
            return dev_dir
        raise FileNotFoundError("找不到邮件报告模板 templates/email_report.html")

    def _build_html(self, date: datetime, stats: list,
                    total_minutes: int, score: int, deep_analysis: dict,
                    ai_comment: str, expert_analysis: str = "") -> str:
        """构建 HTML 邮件内容（统一使用 templates/email_report.html）"""
        date_str = f"{date.year:04d}年{date.month:02d}月{date.day:02d}日"
        hours = int(total_minutes // 60)
        mins = int(total_minutes % 60)

        category_colors = {
            "工作": "#4F46E5", "Work": "#4F46E5",
            "学习": "#059669", "Study": "#059669",
            "编程": "#6366F1", "Programming": "#6366F1",
            "娱乐": "#DC2626", "Entertainment": "#DC2626",
            "休息": "#F59E0B", "Rest": "#F59E0B",
            "社交": "#EC4899", "Social": "#EC4899",
            "其他": "#78716C", "Other": "#78716C",
        }

        if score >= 80:
            score_emoji, score_text, score_color = "🌟", "非常高效", "#059669"
        elif score >= 60:
            score_emoji, score_text, score_color = "👍", "表现不错", "#4F46E5"
        elif score >= 40:
            score_emoji, score_text, score_color = "💪", "稳步前进", "#F59E0B"
        else:
            score_emoji, score_text, score_color = "🎯", "明天更好", "#6B7280"

        focus = deep_analysis.get('focus', {})
        rhythm = deep_analysis.get('rhythm', {})
        switching = deep_analysis.get('switching', {})
        categories = deep_analysis.get('categories', {})
        day_type = deep_analysis.get('day_type', {})

        deep_html = self._build_deep_analysis_html(focus, rhythm, switching, categories, day_type)

        stats_items = []
        for category, minutes in stats[:6]:
            color = category_colors.get(category, "#78716C")
            percent = (minutes / total_minutes * 100) if total_minutes > 0 else 0
            h, m = int(minutes // 60), int(minutes % 60)
            stats_items.append({
                "category": category,
                "minutes": minutes,
                "hours": h,
                "mins": m,
                "percent": percent,
                "bar_width": min(percent, 100),
                "color": color,
            })

        env = Environment(loader=FileSystemLoader(str(self._template_dir())), autoescape=True)
        template = env.get_template("email_report.html")
        expert_html = self._build_expert_analysis_html(expert_analysis) if expert_analysis else ""
        return template.render(
            date_str=date_str,
            hours=hours,
            mins=mins,
            score=score,
            score_emoji=score_emoji,
            score_text=score_text,
            score_color=score_color,
            focus=focus,
            day_type=day_type,
            stats_items=stats_items,
            deep_html=deep_html,
            ai_comment=ai_comment,
            expert_analysis_html=expert_html,
            generated_at=datetime.now().strftime("%H:%M"),
        )
    
    def _build_deep_analysis_html(self, focus: dict, rhythm: dict, 
                                   switching: dict, categories: dict, day_type: dict) -> str:
        """构建深度分析部分的 HTML（所有动态文本均经过 HTML 转义）"""
        esc = html.escape
        sections = []
        
        # 1. 专注力分析
        if focus.get('has_data'):
            max_s = focus.get('max_session', {})
            max_cat = esc(str(max_s.get('category', '')))
            max_time = esc(str(max_s.get('time', '')))
            max_detail = f" · 最长: {max_cat} ({max_time})" if max_cat else ""
            focus_html = f"""
            <div style="background: #F8FAFC; border-radius: 10px; padding: 14px; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #334155; font-size: 13px; margin-bottom: 10px;">🎯 专注力数据</div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; flex: 1; min-width: 120px;">
                        <div style="font-size: 18px; font-weight: 600; color: #0F172A;">{max_s.get('duration', 0)}分钟</div>
                        <div style="font-size: 11px; color: #64748B;">最长专注</div>
                    </div>
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; flex: 1; min-width: 120px;">
                        <div style="font-size: 18px; font-weight: 600; color: #0F172A;">{focus.get('deep_total_mins', 0)}分钟</div>
                        <div style="font-size: 11px; color: #64748B;">深度工作(>60min)</div>
                    </div>
                    <div style="background: white; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px 12px; flex: 1; min-width: 120px;">
                        <div style="font-size: 18px; font-weight: 600; color: {'#DC2626' if focus.get('fragment_percent', 0) > 50 else '#0F172A'};">{focus.get('fragment_percent', 0)}%</div>
                        <div style="font-size: 11px; color: #64748B;">碎片占比(<15min)</div>
                    </div>
                </div>
                <div style="margin-top: 10px; font-size: 12px; color: #64748B;">
                    共 {focus.get('total_sessions', 0)} 段工作 · 平均每段 {focus.get('avg_duration', 0)} 分钟{max_detail}
                </div>
            </div>"""
            sections.append(focus_html)
        
        # 2. 工作节奏分析
        if rhythm.get('has_data'):
            periods = rhythm.get('periods', {})
            rhythm_bars = ""
            max_score = max([p.get('avg_score', 0) for p in periods.values()]) if periods else 100
            peak_hour = rhythm.get('peak_hour', -1)
            
            for name, data in periods.items():
                score = data.get('avg_score', 0)
                bar_width = (score / max_score * 100) if max_score > 0 else 0
                is_peak = (
                    (0 <= peak_hour < 6 and '凌晨' in name)
                    or (6 <= peak_hour < 12 and '上午' in name)
                    or (12 <= peak_hour < 18 and '下午' in name)
                    or (peak_hour >= 18 and '晚上' in name)
                )
                label = esc(str(name).split('(')[0])
                
                rhythm_bars += f"""
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                        <span style="font-size: 12px; color: #374151;">{label} {'⭐' if is_peak else ''}</span>
                        <span style="font-size: 12px; color: #6B7280;">{score}分 · {data.get('total_mins', 0)}分钟</span>
                    </div>
                    <div style="background: #E5E7EB; border-radius: 3px; height: 8px;">
                        <div style="background: {'#10B981' if score >= 70 else '#F59E0B' if score >= 50 else '#EF4444'}; width: {bar_width}%; height: 100%; border-radius: 3px;"></div>
                    </div>
                </div>"""
            
            rhythm_html = f"""
            <div style="background: #F8FAFC; border-radius: 10px; padding: 14px; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #334155; font-size: 13px; margin-bottom: 10px;">⏰ 时段效率</div>
                {rhythm_bars}
                <div style="margin-top: 8px; font-size: 12px; color: #64748B;">
                    效率峰值: {esc(str(rhythm.get('peak_hour', '')))}:00 ({rhythm.get('peak_score', 0)}分) ·
                    低谷: {esc(str(rhythm.get('low_hour', '')))}:00 ({rhythm.get('low_score', 0)}分)
                </div>
            </div>"""
            sections.append(rhythm_html)
        
        # 3. 任务切换分析
        if switching.get('has_data') and switching.get('total_switches', 0) > 0:
            switch_count = switching.get('total_switches', 0)
            switch_color = '#10B981' if switch_count <= 3 else '#F59E0B' if switch_count <= 6 else '#EF4444'
            switch_text = '非常聚焦' if switch_count <= 3 else '节奏正常' if switch_count <= 6 else '切换频繁'
            
            patterns = switching.get('common_patterns', [])
            pattern_str = " · ".join(esc(str(p[0])) for p in patterns[:2]) if patterns else ""
            
            switch_html = f"""
            <div style="background: #F8FAFC; border-radius: 10px; padding: 14px; margin-bottom: 12px;">
                <div style="font-weight: 600; color: #334155; font-size: 13px; margin-bottom: 10px;">🔄 任务切换</div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="background: {switch_color}; color: white; font-size: 20px; font-weight: 700; padding: 12px 20px; border-radius: 8px;">
                        {switch_count}
                    </div>
                    <div>
                        <div style="font-size: 14px; font-weight: 500; color: #0F172A;">{switch_text}</div>
                        <div style="font-size: 12px; color: #64748B;">今日类别切换次数</div>
                    </div>
                </div>
                {f'<div style="margin-top: 8px; font-size: 12px; color: #64748B;">常见切换: {pattern_str}</div>' if pattern_str else ''}
            </div>"""
            sections.append(switch_html)
        
        # 4. 类别效率对比
        if categories.get('has_data') and len(categories.get('stats', {})) >= 2:
            cat_stats = categories.get('stats', {})
            best = categories.get('best')
            worst = categories.get('worst')
            
            if best and worst and best != worst:
                best_data = cat_stats.get(best, {})
                worst_data = cat_stats.get(worst, {})
                
                cat_html = f"""
                <div style="background: #F8FAFC; border-radius: 10px; padding: 14px;">
                    <div style="font-weight: 600; color: #334155; font-size: 13px; margin-bottom: 10px;">📊 类别效率对比</div>
                    <div style="display: flex; gap: 10px;">
                        <div style="flex: 1; background: #DCFCE7; border-radius: 8px; padding: 10px; text-align: center;">
                            <div style="font-size: 11px; color: #166534;">效率最高</div>
                            <div style="font-size: 15px; font-weight: 600; color: #15803D; margin: 4px 0;">{esc(str(best))}</div>
                            <div style="font-size: 18px; font-weight: 700; color: #166534;">{best_data.get('avg_score', 0)}分</div>
                            <div style="font-size: 11px; color: #166534;">{best_data.get('session_count', 0)}段 · {best_data.get('total_mins', 0)}分钟</div>
                        </div>
                        <div style="flex: 1; background: #FEF3C7; border-radius: 8px; padding: 10px; text-align: center;">
                            <div style="font-size: 11px; color: #92400E;">效率较低</div>
                            <div style="font-size: 15px; font-weight: 600; color: #B45309; margin: 4px 0;">{esc(str(worst))}</div>
                            <div style="font-size: 18px; font-weight: 700; color: #92400E;">{worst_data.get('avg_score', 0)}分</div>
                            <div style="font-size: 11px; color: #92400E;">{worst_data.get('session_count', 0)}段 · {worst_data.get('total_mins', 0)}分钟</div>
                        </div>
                    </div>
                </div>"""
                sections.append(cat_html)
        
        return "\n".join(sections) if sections else '<div style="color: #9CA3AF; text-align: center; padding: 20px;">数据量较少，暂无深度分析</div>'
    
    def _build_expert_analysis_html(self, expert_analysis: str) -> str:
        """构建专业分析报告的 HTML（先转义原文再渲染受控 Markdown 标签）"""
        html_content = html.escape(expert_analysis)
        
        html_content = re.sub(r'^### (.+)$', r'<h4 style="font-size: 14px; font-weight: 600; color: #1E3A5F; margin: 16px 0 8px 0;">\1</h4>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^## (.+)$', r'<h3 style="font-size: 15px; font-weight: 600; color: #1E3A5F; margin: 16px 0 10px 0;">\1</h3>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html_content)
        html_content = re.sub(r'^- (.+)$', r'<div style="margin: 4px 0; padding-left: 12px;">• \1</div>', html_content, flags=re.MULTILINE)
        html_content = html_content.replace('\n\n', '</p><p style="margin: 8px 0; color: #334155; font-size: 13px; line-height: 1.7;">')
        html_content = html_content.replace('\n', '<br>')
        
        return f"""
            <!-- 分隔线 -->
            <div style="border-top: 1px solid #E5E7EB; margin: 24px 0;"></div>
            
            <!-- 专业深度分析报告 -->
            <div style="background: linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%); border-radius: 12px; padding: 20px; margin-top: 16px;">
                <h2 style="font-size: 16px; font-weight: 600; color: #0C4A6E; margin: 0 0 16px 0; display: flex; align-items: center;">
                    📋 专业分析报告
                </h2>
                <div style="background: white; border-radius: 8px; padding: 16px; color: #334155; font-size: 13px; line-height: 1.7;">
                    <p style="margin: 0; color: #334155; font-size: 13px; line-height: 1.7;">
                        {html_content}
                    </p>
                </div>
            </div>"""
