"""Bounded diagnostics: never persist provider exceptions, URLs or credentials."""

ERROR_MESSAGES = {
    "unknown": "Falha na tradução. Verifique o provedor e tente novamente.",
    "authentication": "Credencial inválida ou acesso negado. Confira a configuração da API.",
    "rate_limit": "Limite ou cota do provedor atingido. Confira a cota antes de tentar novamente.",
    "daily_quota": "Cota diária do provedor esgotada. Continue amanhã ou escolha outro modelo.",
    "unavailable": "Provedor temporariamente indisponível. Tente novamente mais tarde.",
    "network": "Falha de conexão ou tempo limite. Confira a conexão e tente novamente.",
    "empty_response": "O provedor retornou uma tradução vazia para esta entrada.",
    "missing_result": "A resposta do lote não incluiu uma tradução válida para esta entrada.",
    "batch_failed": "O lote falhou sem fornecer um diagnóstico detalhado.",
}


def normalize_error(code: object) -> str:
    return code if isinstance(code, str) and code in ERROR_MESSAGES else "unknown"


def classify_error(exc: Exception) -> str:
    # Inspect only for classification; never return or store this raw text.
    text = str(exc).lower()
    if "empty translation response" in text:
        return "empty_response"
    if any(word in text for word in ("401", "403", "unauthorized", "forbidden", "api key not valid")):
        return "authentication"
    if any(word in text for word in ("429", "quota", "rate limit", "resource_exhausted")):
        return "rate_limit"
    if any(word in text for word in ("503", "502", "504", "high demand", "unavailable", "overloaded")):
        return "unavailable"
    if isinstance(exc, (TimeoutError, ConnectionError)) or any(
        word in text for word in ("timeout", "timed out", "connection", "dns")
    ):
        return "network"
    return "unknown"
