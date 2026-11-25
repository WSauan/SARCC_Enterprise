"""Utilitários de texto compartilhados entre Core e GUI."""

def fix_mojibake(text: str) -> str:
    """Repara textos UTF-8 lidos incorretamente como CP1252/Latin-1 (ex: CÃ¢mera -> Câmera)."""
    if not text or not isinstance(text, str):
        return text or ""
    if "Ã" in text or "Â" in text:
        try:
            return text.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            try:
                return text.encode("latin1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return text
    return text