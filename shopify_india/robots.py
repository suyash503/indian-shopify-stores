"""robots.txt matching, the way RFC 9309 (and Google) describe it.

I don't use urllib.robotparser because it applies the *first* rule that matches.
Every Shopify robots.txt starts with "Allow: /", so the stdlib parser would say
/admin and /checkout are fine to crawl. Here the longest matching rule wins,
Allow wins a tie, and the * and $ wildcards work.
"""
import re


class RobotsRules:
    def __init__(self, rules=None):
        # list of (allowed, compiled_pattern, pattern_length)
        self.rules = rules or []

    @classmethod
    def allow_all(cls):
        return cls()

    @classmethod
    def disallow_all(cls):
        return cls([(False, _compile("/"), 1)])

    @classmethod
    def parse(cls, text, agent):
        agent = agent.lower()
        groups = []  # [(agents, rules)]
        agents, rules = [], []
        seen_rule = False

        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            field, value = (part.strip() for part in line.split(":", 1))
            field = field.lower()

            if field == "user-agent":
                # a user-agent line after some rules starts a new group
                if seen_rule:
                    groups.append((agents, rules))
                    agents, rules, seen_rule = [], [], False
                agents.append(value.lower())
            elif field in ("allow", "disallow"):
                seen_rule = True
                if not value:
                    continue  # "Disallow:" with nothing means allow everything
                rules.append((field == "allow", _compile(value), len(value)))
        if agents:
            groups.append((agents, rules))

        mine = [r for names, rs in groups if any(n != "*" and n in agent for n in names) for r in rs]
        if not mine:
            mine = [r for names, rs in groups if "*" in names for r in rs]
        return cls(mine)

    def allows(self, path):
        best_len, allowed = -1, True
        for is_allow, pattern, length in self.rules:
            if pattern.match(path) and (length > best_len or (length == best_len and is_allow)):
                best_len, allowed = length, is_allow
        return allowed


def _compile(pattern):
    anchored = pattern.endswith("$")
    body = re.escape(pattern.rstrip("$")).replace(r"\*", ".*")
    return re.compile(body + ("$" if anchored else ""))
