"""Send a daily report once per configured local time."""

from datetime import datetime, timedelta

from bridge.settings import MASK, email_times, read_settings
from core.email_service import EmailConfig, EmailService, ReportGenerator


def mail_service(values, *, enabled):
    return EmailService(EmailConfig(
        sender_email=values["email_sender"], receiver_email=values["email_receiver"],
        auth_code=values["email_auth_code"], enabled=enabled,
    ))


def send_test_email(storage, draft=None):
    values = read_settings(storage)
    if draft:
        values.update({key: value.strip() for key, value in draft.items()
                       if key in {"email_sender", "email_receiver", "email_auth_code"} and value != MASK})
    service = mail_service(values, enabled=True)
    return service.send_report(
        "Dayflow 测试邮件", "<p>此邮件用于确认 Dayflow 的邮箱配置。</p>"
    )


def check_email_schedule(storage, now=None):
    now = now or datetime.now()
    values = read_settings(storage)
    if values["email_enabled"] != "1":
        return
    service = mail_service(values, enabled=True)
    if not all((service.config.sender_email, service.config.receiver_email, service.config.auth_code)):
        return

    for hour, minute in email_times(values["email_send_times"]):
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if not timedelta(0) <= now - scheduled <= timedelta(hours=2):
            continue
        period = f"{hour:02}:{minute:02}"
        legacy = {(12, 0): "noon", (22, 0): "night"}.get((hour, minute), period)
        with storage._get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(success) AS success, MAX(send_time) AS send_time, COUNT(*) AS attempts "
                "FROM email_send_log WHERE period IN (?, ?) AND substr(send_time,1,10)=?",
                (period, legacy, now.date().isoformat()),
            ).fetchone()
        if row["attempts"]:
            if row["success"] or row["attempts"] >= 3:
                continue
            if now - datetime.fromisoformat(row["send_time"]) < timedelta(minutes=5):
                continue
        try:
            html = ReportGenerator(storage).generate_daily_report(scheduled)
            ok, _ = service.send_report(f"Dayflow 日报 {scheduled.date().isoformat()}", html)
        except Exception:
            ok = False
        with storage._get_connection() as conn, conn:
            conn.execute(
                "INSERT INTO email_send_log(period,send_time,success,error_message) VALUES(?,?,?,?)",
                (period, now.isoformat(), int(ok), "" if ok else "发送失败，请检查邮箱和网络"),
            )
