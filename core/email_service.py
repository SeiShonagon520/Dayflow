"""
Dayflow - 邮件推送服务
支持 QQ 邮箱定时发送效率报告，含 AI 点评功能
"""
import smtplib
import logging
import asyncio
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from dataclasses import dataclass

import config

logger = logging.getLogger(__name__)

# 工作日活跃时长（小时）
DAILY_ACTIVE_HOURS = 16


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
            with smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, timeout=30) as server:
                logger.info("SMTP 连接成功，正在登录...")
                server.login(self.config.sender_email, self.config.auth_code)
                logger.info("登录成功，正在发送邮件...")
                server.sendmail(
                    self.config.sender_email,
                    self.config.receiver_email,
                    msg.as_string()
                )
            
            logger.info(f"邮件发送成功: {subject}")
            return True, ""
            
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


class AICommentGenerator:
    """AI 点评生成器"""
    
    # 点评 Prompt 模板
    COMMENT_PROMPT = """你是一个温和友好的效率教练。请根据用户今日的时间记录数据，生成一段简短的点评（80-120字）。

用户今日数据：
- 日期：{date}
- 已记录时长：{recorded_time}
- 未记录时长：{untracked_time}（工作日按16小时计算）
- 效率评分：{score}/100
- 时间分布：{categories}

要求：
1. 用朋友聊天的语气，轻松自然
2. 先简单肯定做得好的地方
3. 如果有改进空间，温和地给出建议
4. 如果未记录时间较多（>8小时），委婉询问是否出门或休息了
5. 结尾用一句话鼓励，可以加一个 emoji
6. 不要使用"您"，用"你"
7. 直接输出点评内容，不要加标题或前缀"""

    def __init__(self):
        self.api_base_url = config.API_BASE_URL.rstrip("/")
        self.api_key = config.API_KEY
        self.model = config.API_MODEL
    
    def generate_comment(self, stats: dict) -> str:
        """
        生成 AI 点评
        
        Args:
            stats: {
                'date': '2025年12月02日',
                'recorded_minutes': 438,
                'score': 84,
                'categories': [('编程', 229), ('学习', 162), ...]
            }
        
        Returns:
            str: AI 生成的点评文本
        """
        # 如果没有 API Key，使用模板
        if not self.api_key:
            return self._fallback_comment(stats)
        
        try:
            # 格式化数据
            recorded_h = stats['recorded_minutes'] // 60
            recorded_m = stats['recorded_minutes'] % 60
            recorded_time = f"{recorded_h}小时{recorded_m}分钟"
            
            untracked_minutes = DAILY_ACTIVE_HOURS * 60 - stats['recorded_minutes']
            untracked_h = max(0, untracked_minutes) // 60
            untracked_m = max(0, untracked_minutes) % 60
            untracked_time = f"{untracked_h}小时{untracked_m}分钟"
            
            # 格式化类别
            categories_str = "、".join([
                f"{cat} {m//60}h{m%60}m" 
                for cat, m in stats['categories'][:5]
            ]) if stats['categories'] else "无记录"
            
            # 构建 prompt
            prompt = self.COMMENT_PROMPT.format(
                date=stats['date'],
                recorded_time=recorded_time,
                untracked_time=untracked_time,
                score=stats['score'],
                categories=categories_str
            )
            
            # 调用 API（同步方式）
            comment = self._call_api_sync(prompt)
            return comment if comment else self._fallback_comment(stats)
            
        except Exception as e:
            logger.error(f"AI 点评生成失败: {e}")
            return self._fallback_comment(stats)
    
    def _call_api_sync(self, prompt: str) -> Optional[str]:
        """同步调用 API"""
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(
                    f"{self.api_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.7,
                        "max_tokens": 300
                    }
                )
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"API 调用失败: {e}")
            return None
    
    def _fallback_comment(self, stats: dict) -> str:
        """降级方案：使用模板生成点评"""
        score = stats['score']
        recorded = stats['recorded_minutes']
        untracked = DAILY_ACTIVE_HOURS * 60 - recorded
        
        # 根据效率评分选择评价
        if score >= 80:
            efficiency = "今天效率很高，继续保持！"
        elif score >= 60:
            efficiency = "今天表现不错，还有进步空间~"
        elif score >= 40:
            efficiency = "今天效率一般，明天加油哦！"
        else:
            efficiency = "今天似乎有点分心，没关系，明天重新开始！"
        
        # 根据未记录时间选择提示
        if untracked > 10 * 60:  # 超过10小时未记录
            time_hint = "大部分时间没有记录，是休息日还是出门啦？"
        elif untracked > 6 * 60:  # 超过6小时未记录
            time_hint = "有不少时间没记录到，记得开启录制哦~"
        else:
            time_hint = ""
        
        # 组合点评
        parts = [efficiency]
        if time_hint:
            parts.append(time_hint)
        parts.append("💪")
        
        return " ".join(parts)


class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, storage):
        self.storage = storage
        self.ai_generator = AICommentGenerator()
    
    def generate_daily_report(self, date: datetime = None) -> str:
        """生成每日报告 HTML"""
        if date is None:
            date = datetime.now()
        
        # 获取当天数据
        cards = self.storage.get_cards_for_date(date)
        
        # 统计各类别时间
        category_stats = {}
        total_minutes = 0
        
        for card in cards:
            category = card.category or "其他"
            minutes = card.duration_minutes
            category_stats[category] = category_stats.get(category, 0) + minutes
            total_minutes += minutes
        
        # 排序
        sorted_stats = sorted(category_stats.items(), key=lambda x: x[1], reverse=True)
        
        # 计算效率评分
        total_score = 0
        score_count = 0
        for card in cards:
            if card.productivity_score > 0:
                total_score += card.productivity_score
                score_count += 1
        avg_score = int(total_score / score_count) if score_count > 0 else 0
        
        # 生成 AI 点评
        ai_stats = {
            'date': date.strftime("%Y年%m月%d日"),
            'recorded_minutes': int(total_minutes),
            'score': avg_score,
            'categories': [(cat, int(mins)) for cat, mins in sorted_stats]
        }
        ai_comment = self.ai_generator.generate_comment(ai_stats)
        
        # 生成 HTML
        return self._build_html(date, sorted_stats, total_minutes, avg_score, ai_comment)
    
    def _build_html(self, date: datetime, stats: list, 
                    total_minutes: int, score: int, ai_comment: str) -> str:
        """构建 HTML 邮件内容"""
        date_str = date.strftime("%Y年%m月%d日")
        hours = int(total_minutes // 60)
        mins = int(total_minutes % 60)
        
        # 类别颜色
        category_colors = {
            "工作": "#4F46E5",
            "Work": "#4F46E5",
            "学习": "#059669",
            "Study": "#059669",
            "编程": "#6366F1",
            "Programming": "#6366F1",
            "娱乐": "#DC2626",
            "Entertainment": "#DC2626",
            "休息": "#F59E0B",
            "Rest": "#F59E0B",
            "社交": "#EC4899",
            "Social": "#EC4899",
            "其他": "#78716C",
            "Other": "#78716C",
        }
        
        # 构建时间分布条
        stats_html = ""
        for category, minutes in stats:
            color = category_colors.get(category, "#78716C")
            percent = (minutes / total_minutes * 100) if total_minutes > 0 else 0
            h = int(minutes // 60)
            m = int(minutes % 60)
            
            # 进度条宽度
            bar_width = min(percent, 100)
            
            stats_html += f"""
            <div style="margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <span style="font-weight: 500; color: #374151;">{category}</span>
                    <span style="color: #6B7280;">{h}h {m}m ({percent:.0f}%)</span>
                </div>
                <div style="background-color: #E5E7EB; border-radius: 4px; height: 8px; overflow: hidden;">
                    <div style="background-color: {color}; width: {bar_width}%; height: 100%; border-radius: 4px;"></div>
                </div>
            </div>
            """
        
        # 效率评价
        if score >= 80:
            score_emoji = "🌟"
            score_text = "非常高效！"
            score_color = "#059669"
        elif score >= 60:
            score_emoji = "👍"
            score_text = "表现不错"
            score_color = "#4F46E5"
        elif score >= 40:
            score_emoji = "💪"
            score_text = "继续加油"
            score_color = "#F59E0B"
        else:
            score_emoji = "🎯"
            score_text = "明天更好"
            score_color = "#6B7280"
        
        # 完整 HTML
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #F3F4F6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <!-- 头部 -->
        <div style="background: linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%); border-radius: 16px 16px 0 0; padding: 24px; text-align: center;">
            <h1 style="margin: 0; color: white; font-size: 24px; font-weight: 600;">📊 Dayflow 效率报告</h1>
            <p style="margin: 8px 0 0 0; color: rgba(255,255,255,0.9); font-size: 14px;">{date_str}</p>
        </div>
        
        <!-- 主体 -->
        <div style="background-color: white; padding: 24px; border-radius: 0 0 16px 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            
            <!-- 总览卡片 -->
            <div style="display: flex; gap: 16px; margin-bottom: 24px;">
                <div style="flex: 1; background-color: #F9FAFB; border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 28px; font-weight: 700; color: #4F46E5;">{hours}h {mins}m</div>
                    <div style="color: #6B7280; font-size: 13px; margin-top: 4px;">总记录时长</div>
                </div>
                <div style="flex: 1; background-color: #F9FAFB; border-radius: 12px; padding: 16px; text-align: center;">
                    <div style="font-size: 28px; font-weight: 700; color: {score_color};">{score_emoji} {score}</div>
                    <div style="color: #6B7280; font-size: 13px; margin-top: 4px;">{score_text}</div>
                </div>
            </div>
            
            <!-- 时间分布 -->
            <div style="margin-bottom: 24px;">
                <h2 style="font-size: 16px; font-weight: 600; color: #111827; margin: 0 0 16px 0; display: flex; align-items: center;">
                    <span style="margin-right: 8px;">📈</span> 时间分布
                </h2>
                {stats_html if stats_html else '<div style="color: #9CA3AF; text-align: center;">暂无数据</div>'}
            </div>
            
            <!-- 分隔线 -->
            <div style="border-top: 1px solid #E5E7EB; margin: 24px 0;"></div>
            
            <!-- AI 点评 -->
            <div style="background: linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%); border-radius: 12px; padding: 16px;">
                <h2 style="font-size: 16px; font-weight: 600; color: #92400E; margin: 0 0 12px 0; display: flex; align-items: center;">
                    <span style="margin-right: 8px;">💬</span> 今日点评
                </h2>
                <p style="margin: 0; color: #78350F; font-size: 14px; line-height: 1.7;">
                    {ai_comment}
                </p>
            </div>
        </div>
        
        <!-- 页脚 -->
        <div style="text-align: center; padding: 16px; color: #9CA3AF; font-size: 12px;">
            由 Dayflow 自动生成 · {datetime.now().strftime("%H:%M")}
        </div>
    </div>
</body>
</html>
        """
        
        return html


class EmailScheduler:
    """邮件定时调度器"""
    
    def __init__(self, email_service: EmailService, report_generator: ReportGenerator):
        self.email_service = email_service
        self.report_generator = report_generator
        self._last_noon_send: Optional[datetime] = None
        self._last_night_send: Optional[datetime] = None
    
    def check_and_send(self):
        """检查是否需要发送报告（每分钟调用一次）"""
        now = datetime.now()
        today = now.date()
        
        # 中午 12:00
        if now.hour == 12 and now.minute == 0:
            if self._last_noon_send is None or self._last_noon_send.date() != today:
                self._send_report("noon")
                self._last_noon_send = now
        
        # 晚上 22:00
        if now.hour == 22 and now.minute == 0:
            if self._last_night_send is None or self._last_night_send.date() != today:
                self._send_report("night")
                self._last_night_send = now
    
    def _send_report(self, period: str):
        """发送报告"""
        try:
            now = datetime.now()
            date_str = now.strftime("%m月%d日")
            
            if period == "noon":
                subject = f"📊 Dayflow 午间报告 - {date_str}"
            else:
                subject = f"📊 Dayflow 晚间报告 - {date_str}"
            
            html = self.report_generator.generate_daily_report(now)
            success, error_msg = self.email_service.send_report(subject, html)
            
            if success:
                logger.info(f"定时报告发送成功: {period}")
            else:
                logger.error(f"定时报告发送失败: {error_msg}")
            
        except Exception as e:
            logger.error(f"发送定时报告失败: {e}")
    
    def send_test_email(self) -> tuple:
        """发送测试邮件，返回 (成功, 错误信息)"""
        try:
            now = datetime.now()
            subject = f"🧪 Dayflow 测试邮件 - {now.strftime('%H:%M')}"
            html = self.report_generator.generate_daily_report(now)
            return self.email_service.send_report(subject, html)
        except Exception as e:
            logger.error(f"发送测试邮件失败: {e}")
            return False, str(e)
