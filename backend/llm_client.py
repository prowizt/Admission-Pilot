# ==========================================
# LLM 공급자 공통 호출 계층 (Gemini ↔ Claude 전환)
# ==========================================
# 모델 이름이 "claude-"로 시작하면 Anthropic(Claude) SDK로, 그 외에는 기존 Gemini SDK로 호출합니다.
# main.py / excel_autofill.py 는 이 모듈의 generate() / stream() 만 사용하므로,
# 크롬 확장에서 모델 드롭다운만 바꿔도 같은 질문을 두 공급자로 비교할 수 있습니다.
#
# [키 처리] 요청 헤더(x-gemini-key)로 받은 키를 공급자 공통 키로 사용합니다.
#           Claude 모델인데 헤더 키가 없으면 서버 .env 의 ANTHROPIC_API_KEY 를 사용합니다.
# [주의] Claude Haiku 5.5 는 temperature / top_p / top_k / budget_tokens 를 보내면 400 오류가 나므로 절대 보내지 않습니다.

import os
from dataclasses import dataclass

import anthropic
import google.generativeai as genai
from google.api_core import retry as gapi_retry

import app_config

# [환경설정] 아래 값은 대시보드 '환경 설정'에서 바꾸면 재시작 없이 바로 반영되도록 읽을 때마다 app_config 에서 가져옵니다.
#  - KRW_PER_USD: 비용 추정용 환율 (원/달러). 실제 청구액은 Anthropic 콘솔 Usage 에서 확인
#  - VAT_RATE: 부가세율. 로그의 원화 비용은 부가세 포함 금액 (콘솔 크레딧 차감액은 부가세 제외)
#  - MAX_PROMPT_TOKENS: Claude 호출 1건의 입력 토큰 상한 (넘으면 호출하지 않고 취소)
#  - ROUTER_THINKING_OFF: 라우터(JSON 판단) 호출의 추론 끄기 여부 (ROUTER_THINKING=on 이면 켬)
#  - STAFF_EFFORT: 교직원 최종 답변 추론 강도 기본값
# 다른 모듈의 llm_client.VAT_RATE 같은 기존 사용처는 아래 __getattr__ 로 그대로 동작합니다.
def __getattr__(name):
    if name in ("KRW_PER_USD", "VAT_RATE", "MAX_PROMPT_TOKENS", "STAFF_EFFORT"):
        return app_config.get(name)
    if name == "ROUTER_THINKING_OFF":
        return app_config.get("ROUTER_THINKING") != "on"
    raise AttributeError(name)

# Claude 모델별 단가 (USD / 1M tokens): (입력, 출력)
CLAUDE_PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
# Haiku 5.5 는 프롬프트(입력 합계)가 10만 토큰을 넘으면 요청 전체가 5배 단가($0.50 / $2.50)로 과금됩니다.
HAIKU_LONG_PROMPT_THRESHOLD = 100_000



class TokenLimitExceeded(Exception):
    """입력 토큰이 MAX_PROMPT_TOKENS 를 넘어 API 호출 없이 취소된 경우 (과금 없음)"""

    def __init__(self, model, tokens, limit):
        self.model = model
        self.tokens = tokens
        self.limit = limit
        # 메시지에 숫자를 넣지 않습니다. (main.py 재시도 루프가 오류 문자열의 "429"/"503" 으로 재시도를 판단하기 때문)
        super().__init__("입력 토큰 한도 초과로 AI 호출을 취소했습니다.")


class ApiKeyError(Exception):
    """Claude API 키가 만료·비활성·잘못되어 인증이 거부된 경우 (401/403). 메시지는 관리자용 안내 (학생에게는 보여 주지 않음)"""


API_KEY_ERROR_MESSAGE = ("Claude API 키가 만료되었거나 비활성화된 키입니다(또는 권한 없음). "
                         "backend/.env 의 ANTHROPIC_API_KEY 를 확인해 주세요. "
                         "운영 서버는 C:\\actions-runner\\.env 도 함께 바꾸고 다시 배포해야 합니다. "
                         "(크롬 확장 모델 설정에 키를 직접 넣었다면 그 키도 확인)")


def _raise_key_error(e):
    print(f"[LLM] 🔑 Claude API 키 인증 실패 ({type(e).__name__}): {getattr(e, 'message', e)}")
    raise ApiKeyError(API_KEY_ERROR_MESSAGE) from e


REFUSAL_MESSAGE ="⚠️ Claude가 안전 정책에 따라 이 요청에 대한 답변을 거절했습니다. 질문을 바꾸거나 Gemini 모델로 다시 시도해 주세요."


def token_limit_message(err: "TokenLimitExceeded", doc_chars=None, prompt_chars=0, extra_hint="") -> str:
    """취소 안내 문구. doc_chars={파일명: 글자수} 가 있으면 전체 토큰을 글자 비율로 나눠 문서별 예상 토큰을 표시합니다."""
    lines = [
        "⛔ **AI 호출을 취소했습니다 (과금 없음)**",
        f"- 사용 모델: {err.model}",
        f"- 입력 토큰: {err.tokens:,}개 (한도 {err.limit:,}개 초과)",
    ]
    if doc_chars and prompt_chars:
        lines.append("- 참고 문서별 예상 토큰:")
        for fname, chars in sorted(doc_chars.items(), key=lambda x: -x[1]):
            lines.append(f"  - {fname}: 약 {int(err.tokens * chars / prompt_chars):,} 토큰")
    lines.append("")
    lines.append("큰 문서를 빼거나 질문 범위를 좁혀서 다시 시도해 주세요.")
    if extra_hint:
        lines.append(extra_hint)
    return "\n".join(lines)


@dataclass
class LLMResult:
    text: str
    in_tokens: int = 0          # 프롬프트 전체 토큰 (Claude: 캐시 읽기/쓰기 포함)
    out_tokens: int = 0
    cache_read_tokens: int = 0  # Claude 프롬프트 캐시 적중 토큰
    cache_write_tokens: int = 0 # Claude 프롬프트 캐시 생성 토큰


def is_claude(model_name: str) -> bool:
    return bool(model_name) and model_name.lower().startswith("claude-")


def resolve_api_key(model_name: str, header_key: str) -> str:
    """헤더 키를 우선 사용하고, Claude 모델이면서 헤더 키가 없으면 서버 환경변수 키로 대체합니다."""
    if header_key:
        return header_key
    if is_claude(model_name):
        return os.getenv("ANTHROPIC_API_KEY", "")
    return ""


def estimate_cost_krw(model_name: str, result: LLMResult) -> float:
    """Claude 호출 1건의 예상 비용(원, 부가세 포함). 캐시 읽기 0.1배, 캐시 쓰기(5분) 1.25배 단가를 적용합니다."""
    in_price, out_price = CLAUDE_PRICES.get(model_name.lower(), CLAUDE_PRICES["claude-haiku-5-5"])
    if model_name.lower() == "claude-haiku-5-5" and result.in_tokens > HAIKU_LONG_PROMPT_THRESHOLD:
        in_price, out_price = in_price * 5, out_price * 5
    uncached = max(result.in_tokens - result.cache_read_tokens - result.cache_write_tokens, 0)
    usd = (
        uncached * in_price
        + result.cache_read_tokens * in_price * 0.1
        + result.cache_write_tokens * in_price * 1.25
        + result.out_tokens * out_price
    ) / 1_000_000
    return usd * app_config.get("KRW_PER_USD") * (1 + app_config.get("VAT_RATE"))


# ------------------------------------------
# Claude (Anthropic) 분기
# ------------------------------------------
# 추론(thinking)을 끌 수 있는 모델. Haiku 5.5 는 effort high 이하에서 {"type": "disabled"} 허용
# (Opus 5.5 / Sonnet 5.5 는 disabled 를 보내면 400 오류이므로 대상에서 제외)
THINKING_DISABLE_MODELS = ("claude-haiku-5-5",)
# 교직원 최종 답변 추론 강도: 확장 프로그램에서 모델별로 지정하면 그 값이 우선, 없으면 환경설정 STAFF_EFFORT
VALID_EFFORTS = ("low", "medium", "high")


def resolve_effort(requested=None) -> str:
    """교직원 답변 추론 강도 = 대시보드 환경 설정 STAFF_EFFORT.
    (예전 확장 프로그램이 보내는 모델별 effort 값은 무시: 설정을 한 곳에서만 관리)"""
    return app_config.get("STAFF_EFFORT")


def mode_label(model, effort, thinking_off=False) -> str:
    """감사 로그/화면 표시용 호출 설정 문구 (예: 'effort=medium · 추론 켬')"""
    if not model or model == "NONE":
        return ""
    if not is_claude(model):
        return "해당 없음 (Gemini)"
    off = thinking_off and model.lower() in THINKING_DISABLE_MODELS and effort in ("low", "medium", "high")
    return f"effort={effort} · 추론 {'끔' if off else '켬'}"


def _claude_kwargs(model, prompt, system, effort, json_schema, max_tokens, thinking_off=False):
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "output_config": {"effort": effort},
    }
    if thinking_off and model.lower() in THINKING_DISABLE_MODELS and effort in ("low", "medium", "high"):
        # 라우터처럼 정해진 형식(JSON)만 내는 호출은 추론을 꺼서 출력 토큰·지연을 줄입니다.
        kwargs["thinking"] = {"type": "disabled"}
    if system and system.strip():
        # 프롬프트 캐싱은 사용하지 않습니다. (라우터가 질문마다 다른 문서를 골라 넣어 적중률이 낮고, 미적중 시 쓰기 요금 1.25배만 발생)
        kwargs["system"] = system.strip()
    if json_schema:
        kwargs["output_config"]["format"] = {"type": "json_schema", "schema": json_schema}
    return kwargs


def _claude_check_tokens(client, kwargs):
    """호출 전에 입력 토큰을 세고(무료 API), 한도를 넘으면 TokenLimitExceeded 를 던집니다."""
    count_kwargs = {"model": kwargs["model"], "messages": kwargs["messages"]}
    if "system" in kwargs:
        count_kwargs["system"] = kwargs["system"]
    try:
        tokens = client.messages.count_tokens(**count_kwargs).input_tokens
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        _raise_key_error(e)  # 키 만료·비활성은 보통 여기(첫 호출)에서 걸림
    limit = app_config.get("MAX_PROMPT_TOKENS")
    if tokens > limit:
        print(f"[LLM] 🛑 Claude({kwargs['model']}) 입력 {tokens:,} 토큰 > 한도 {limit:,} → 호출 취소 (과금 없음)")
        raise TokenLimitExceeded(kwargs["model"], tokens, limit)
    return tokens


def _claude_result(message) -> LLMResult:
    text = "".join(b.text for b in message.content if b.type == "text")
    if message.stop_reason == "refusal":
        text = REFUSAL_MESSAGE
    elif message.stop_reason == "max_tokens":
        text += "\n\n> [!NOTE]\n> 답변이 최대 길이에 도달해 중간에 끊겼을 수 있습니다."
    u = message.usage
    cache_read = u.cache_read_input_tokens or 0
    cache_write = u.cache_creation_input_tokens or 0
    return LLMResult(
        text=text,
        in_tokens=u.input_tokens + cache_read + cache_write,
        out_tokens=u.output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
    )


def _claude_generate(model, api_key, prompt, system, json_schema, effort, timeout, max_tokens, thinking_off=False) -> LLMResult:
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
    kwargs = _claude_kwargs(model, prompt, system, effort, json_schema, max_tokens, thinking_off)
    _claude_check_tokens(client, kwargs)
    try:
        # 긴 출력에서도 HTTP 타임아웃이 나지 않도록 내부적으로 스트리밍으로 받은 뒤 최종 메시지를 조립합니다.
        with client.messages.stream(**kwargs) as s:
            message = s.get_final_message()
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
        _raise_key_error(e)
    except anthropic.BadRequestError as e:
        if not json_schema:
            raise
        # 구조화 출력이 거부되면 프롬프트 JSON 지시만으로 재시도 (호출 측 파서가 JSON을 읽음)
        print(f"[LLM] ⚠️ 구조화 출력(json_schema) 거부됨 → 프롬프트 JSON 모드로 재시도: {e.message}")
        kwargs["output_config"].pop("format", None)
        with client.messages.stream(**kwargs) as s:
            message = s.get_final_message()
    result = _claude_result(message)
    mode = f"effort={effort}, 추론={'끔' if 'thinking' in kwargs else '켬'}"
    print(f"[LLM] Claude({model}, {mode}) 입력 {result.in_tokens:,} (캐시 읽기 {result.cache_read_tokens:,} / 쓰기 {result.cache_write_tokens:,}) / 출력 {result.out_tokens:,}")
    return result


# ------------------------------------------
# Gemini 분기 (기존 main.py 호출 방식 유지)
# ------------------------------------------
def _to_gemini_schema(schema):
    """표준 JSON Schema(소문자 type)를 Gemini response_schema 형식(대문자 type, additionalProperties 제거)으로 변환합니다."""
    if isinstance(schema, dict):
        out = {}
        for k, v in schema.items():
            if k == "additionalProperties":
                continue
            out[k] = v.upper() if k == "type" and isinstance(v, str) else _to_gemini_schema(v)
        return out
    if isinstance(schema, list):
        return [_to_gemini_schema(v) for v in schema]
    return schema


def _gemini_usage(response, result: LLMResult):
    meta = getattr(response, "usage_metadata", None)
    if meta:
        result.in_tokens = meta.prompt_token_count or 0
        result.out_tokens = meta.candidates_token_count or 0


def _gemini_generate(model, api_key, prompt, system, json_schema, timeout) -> LLMResult:
    genai.configure(api_key=api_key)
    gmodel = genai.GenerativeModel(model_name=model, system_instruction=system) if system else genai.GenerativeModel(model)
    no_retry = gapi_retry.Retry(initial=0, maximum=0, multiplier=0, deadline=0)
    extra = {}
    if json_schema:
        extra["generation_config"] = genai.types.GenerationConfig(
            response_mime_type="application/json",
            response_schema=_to_gemini_schema(json_schema),
        )
    response = gmodel.generate_content(prompt, request_options={"timeout": timeout, "retry": no_retry}, **extra)
    result = LLMResult(text=response.text)
    _gemini_usage(response, result)
    return result


# ------------------------------------------
# 공개 함수
# ------------------------------------------
def generate(model, api_key, prompt, system=None, json_schema=None, effort="medium", timeout=600, max_tokens=32000, thinking_off=False) -> LLMResult:
    """단건 생성. effort / thinking_off 는 Claude 에만 적용됩니다 (thinking_off 는 Haiku 5.5 만 해당)."""
    if is_claude(model):
        return _claude_generate(model, api_key, prompt, system, json_schema, effort, timeout, max_tokens, thinking_off)
    return _gemini_generate(model, api_key, prompt, system, json_schema, timeout)


def count_tokens(model, api_key, text) -> int:
    """텍스트 1건의 입력 토큰 수 (무료 API). 실패 시 글자 수를 근사값으로 반환합니다."""
    try:
        if is_claude(model):
            client = anthropic.Anthropic(api_key=api_key, max_retries=2)
            return client.messages.count_tokens(model=model, messages=[{"role": "user", "content": text}]).input_tokens
        genai.configure(api_key=api_key)
        return genai.GenerativeModel(model).count_tokens(text).total_tokens
    except Exception as e:
        print(f"[LLM] ⚠️ 토큰 계산 실패 → 글자 수로 근사: {e}")
        return len(text)


class LLMStream:
    """텍스트 조각(str)을 순서대로 내보내는 스트림. 반복이 끝나면 self.result 에 토큰 사용량이 채워집니다."""

    def __init__(self, model, api_key, prompt, system=None, effort="low", timeout=60, max_tokens=16000):
        self.model = model
        self.result = LLMResult(text="")
        if is_claude(model):
            self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
            self._kwargs = _claude_kwargs(model, prompt, system, effort, None, max_tokens)
            # 스트림 생성 시점에 한도를 검사하여, 호출 측에서 응답 시작 전에 취소를 처리할 수 있게 합니다.
            _claude_check_tokens(self._client, self._kwargs)
        else:
            genai.configure(api_key=api_key)
            gmodel = genai.GenerativeModel(model_name=model, system_instruction=system) if system else genai.GenerativeModel(model)
            no_retry = gapi_retry.Retry(initial=0, maximum=0, multiplier=0, deadline=0)
            # Gemini 는 여기서 즉시 요청을 보내므로, 호출 측 재시도 루프(429/503)가 그대로 동작합니다.
            self._gemini_response = gmodel.generate_content(prompt, request_options={"timeout": timeout, "retry": no_retry}, stream=True)

    def __iter__(self):
        if is_claude(self.model):
            try:
                with self._client.messages.stream(**self._kwargs) as s:
                    for text in s.text_stream:
                        yield text
                    final = _claude_result(s.get_final_message())
            except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
                _raise_key_error(e)
            if final.text == REFUSAL_MESSAGE:
                yield "\n\n" + REFUSAL_MESSAGE
            self.result = final
        else:
            full = ""
            for chunk in self._gemini_response:
                try:
                    text = chunk.text
                except ValueError:
                    # 마지막 청크 등 텍스트 파트가 없는 경우(finish_reason=1) 무시
                    continue
                if text:
                    full += text
                    yield text
            self.result.text = full
            _gemini_usage(self._gemini_response, self.result)


def stream(model, api_key, prompt, system=None, effort="low", timeout=60) -> LLMStream:
    return LLMStream(model, api_key, prompt, system=system, effort=effort, timeout=timeout)
