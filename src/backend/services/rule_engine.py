import re
from typing import Optional
from models import Rule, Item


def evaluate_rule(rule: Rule, item: Item) -> bool:
    expression = rule.match_expression.strip()
    scope = rule.scope or "title"
    whole_word = rule.match_whole_word

    text = _get_scope_text(item, scope)
    if not text:
        return False

    text = text.lower()
    return _evaluate_expression(expression.lower(), text, whole_word)


def _get_scope_text(item: Item, scope: str) -> Optional[str]:
    if scope == "title":
        return item.title
    elif scope == "content":
        return item.content
    elif scope == "author":
        return item.author
    elif scope == "all":
        parts = [item.title or "", item.content or "", item.author or ""]
        return " ".join(parts)
    return item.title


def _evaluate_expression(expression: str, text: str, whole_word: bool) -> bool:
    # Support AND / OR operators, e.g. "rust AND python" or "rust OR python"
    if " and " in expression:
        terms = [t.strip() for t in expression.split(" and ")]
        return all(_match_term(t, text, whole_word) for t in terms)
    elif " or " in expression:
        terms = [t.strip() for t in expression.split(" or ")]
        return any(_match_term(t, text, whole_word) for t in terms)
    else:
        return _match_term(expression, text, whole_word)


def _match_term(term: str, text: str, whole_word: bool) -> bool:
    if term.startswith("/") and term.endswith("/"):
        # Regex pattern
        pattern = term[1:-1]
        try:
            return bool(re.search(pattern, text))
        except re.error:
            return False

    if whole_word:
        pattern = r"\b" + re.escape(term) + r"\b"
        return bool(re.search(pattern, text))

    return term in text


def get_rule_actions(rule: Rule) -> list[str]:
    return rule.actions or []
