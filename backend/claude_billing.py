"""
[Claude 크레딧] 예상 잔액 = 기준 잔액(콘솔에서 본 값) − 그 시각 이후 감사 로그에 기록된 Claude 예상 비용

- 개인 조직(Individual Org)은 Anthropic 사용액 조회 API(Admin API)를 쓸 수 없어 로그 기준으로 계산
- 로그 비용은 원화·부가세 포함 → 환경 설정의 환율·부가세율로 USD(부가세 제외, 콘솔 차감액 기준)로 환산
  (기록할 때와 같은 환율로 되돌리므로 차감 달러는 환율과 관계없이 정확. 환율이 바뀌면 지난 기간의 달러 환산만 조금 달라짐)
- 콘솔 잔액을 볼 때마다 '콘솔 잔액으로 맞추기'로 다시 입력하면 오차가 쌓이지 않음
"""
import datetime as dt

import app_config


def _usd_factor() -> float:
    """원화(부가세 포함) → USD(부가세 제외) 로 나눌 값 (지금 환율 기준)"""
    return app_config.get("KRW_PER_USD") * (1 + app_config.get("VAT_RATE"))


def _log_cost(cur, since: str):
    """(원화 합계, 달러 합계)"""
    cur.execute("""
        SELECT ISNULL(SUM(estimated_cost), 0) FROM Sys_AIAuditLog
        WHERE created_at >= ? AND (model_name LIKE 'claude%' OR router_model_name LIKE 'claude%')""", (since,))
    krw = float(cur.fetchone()[0] or 0)
    return krw, krw / _usd_factor()


def sync_balance(balance_usd) -> dict:
    """콘솔에서 본 잔액으로 기준을 다시 맞춤 (지금 시각부터 다시 계산)"""
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    app_config.set_value("CREDIT_BASE_USD", str(balance_usd))
    app_config.set_value("CREDIT_BASE_AT", now)
    return get_summary()


def _save_raw(key, value, desc):
    """크레딧 기록용 설정 행 저장 (환경 설정 목록에 나오지 않는 값)"""
    conn = app_config._owner_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE Sys_SystemSetting SET setting_value = ?, updated_at = GETDATE() WHERE setting_key = ?", (value, key))
        if cur.rowcount == 0:
            cur.execute("INSERT INTO Sys_SystemSetting (setting_key, setting_value, description) VALUES (?, ?, ?)", (key, value, desc))
        conn.commit()
    finally:
        conn.close()
    app_config._cache[key] = (value, __import__("time").time())


def record_charge(paid_usd: float, paid_krw: float) -> dict:
    """[충전 기록] 결제 금액(USD, 부가세 포함)과 카드 청구 원화로
    1) 환율 = 원화 ÷ 결제 달러 (카드 수수료 포함 실제 환율) 저장
    2) 예상 잔액에 충전 크레딧(결제액 ÷ (1 + 부가세율))을 더해 지금 시각으로 다시 맞춤"""
    import json
    # 충전 전 잔액은 지금까지의 로그가 기록된 '옛 환율'로 계산해야 하므로 환율을 바꾸기 전에 구함
    before = get_summary()
    base = before["remaining_usd"] if before["remaining_usd"] is not None else 0.0
    rate = round(paid_krw / paid_usd, 2)
    app_config.set_value("KRW_PER_USD", str(rate))
    credit = round(paid_usd / (1 + app_config.get("VAT_RATE")), 4)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    app_config.set_value("CREDIT_BASE_USD", str(round(base + credit, 4)))
    app_config.set_value("CREDIT_BASE_AT", now)
    _save_raw("CREDIT_LAST_CHARGE", json.dumps({"at": now, "paid_usd": paid_usd, "paid_krw": paid_krw, "rate": rate, "credit_usd": credit},
                                               ensure_ascii=False), "[Claude 크레딧] 마지막 충전 기록")
    out = get_summary()
    out["charged"] = {"credit_usd": credit, "rate": rate, "before_usd": base}
    return out


def get_summary() -> dict:
    base_usd = float(app_config.get("CREDIT_BASE_USD") or 0)
    base_at = app_config.get("CREDIT_BASE_AT") or ""
    now = dt.datetime.now()
    today = now.strftime("%Y-%m-%d 00:00:00")
    month = now.strftime("%Y-%m-01 00:00:00")
    out = {
        "checked_at": now.strftime("%Y-%m-%d %H:%M"),
        "base_usd": base_usd, "base_at": base_at,
        "krw_per_usd": app_config.get("KRW_PER_USD"), "vat_rate": app_config.get("VAT_RATE"),
        "since_base_krw": None, "since_base_usd": None, "remaining_usd": None,
        "note": "감사 로그에 기록된 Claude 예상 비용 기준 (실제 청구와 조금 다를 수 있음). "
                "로그에 남지 않는 호출(AI 인사이트 분석 등)은 빠집니다.",
    }
    import json
    try:
        out["last_charge"] = json.loads(app_config.get_raw("CREDIT_LAST_CHARGE") or "null")
    except ValueError:
        out["last_charge"] = None
    conn = app_config._owner_conn()
    try:
        cur = conn.cursor()
        out["today_krw"], today_usd = _log_cost(cur, today)
        out["month_krw"], month_usd = _log_cost(cur, month)
        if base_usd > 0 and base_at:
            krw, usd = _log_cost(cur, base_at)
            out["since_base_krw"] = round(krw, 1)
            out["since_base_usd"] = round(usd, 4)
            out["remaining_usd"] = round(base_usd - out["since_base_usd"], 4)
    finally:
        conn.close()
    out["today_usd"] = round(today_usd, 4)
    out["month_usd"] = round(month_usd, 4)
    return out
