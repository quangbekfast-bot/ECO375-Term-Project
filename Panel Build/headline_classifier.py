"""Headline classifier for price-reporting headlines (ECO375). Regex rules, checked by hand on samples."""
import re, numpy as np
MOVE = (r"(?:up|down|higher|lower|jump(?:s|ed|ing)?|soar\w*|surg\w*|spik\w*|rall(?:y|ies|ied|ying)|climb\w*|plung\w*|plummet\w*|"
        r"tumbl\w*|sink(?:s|ing)?|sank|slid(?:e|es|ing)|drop(?:s|ped|ping)?|fall(?:s|ing)?|fell|dip(?:s|ped)?|slump\w*|skyrocket\w*|"
        r"tank(?:s|ed|ing)?|ris(?:e|es|ing)|rose|gain(?:s|ed|ing)?|pop(?:s|ped)?|gap(?:s|ped)?|sell-?off|rebound\w*|retreat\w*|"
        r"crash\w*|rocket\w*|crater\w*|slip(?:s|ped)?|declin\w*|advanc\w*|edg(?:e|es|ed)|trad(?:e|es|ing) (?:higher|lower|up|down))")
ROUNDUP = (r"52[- ]week|new (?:\d+[- ]week |all[- ]time )?(?:highs?|lows?)\b|all[- ]time highs?|stocks moving|biggest movers|\bmovers\b|"
           r"gainers|losers|most active|sector update|mid-morning|mid-?day (?!report)|morning price|price (?:action|check)|"
           r"sector (?:leaders|laggards)|pre-?market (?:session|movers|most)|after[- ]hours (?:movers|most|gainers|session)|"
           r"market (?:update|wrap)|what'?s moving|shares of several|stocks? (?:are |is )?trading (?:higher|lower)|"
           r"crosses (?:above|below)|moving average|oversold|overbought|\brsi\b|relative strength|golden cross|death cross|"
           r"key technical|breaks (?:above|below)|since (?:last )?earnings report|\d+[- ]week highs?")
MOVE_HEAD = (r"(?:stock|shares|share price|\bshare)\W+(?:\S+\W+){0,4}?" + MOVE + r"\b"
             r"|\([A-Z.]{1,6}\)\W+(?:stock\W+)?" + MOVE + r"\b"          # 'Celgene (CELG) Up ...'
             r"|(?:^|\s)[+-]\d+(?:\.\d+)?%"                               # 'Jacobs +7% after ...'
             r"|\b(?:up|down|higher|lower)\s+(?:more than\s+|over\s+|~)?\$?\d+(?:\.\d+)?%"
             r"|\b(?:soar(?:s|ed|ing)?|plung\w*|plummet\w*|tumbl\w*|skyrocket\w*|jump(?:s|ed)|crater\w*|tank(?:s|ed))\b")
CAUSE = (r"\b(?:after|following|on|amid|post|due to|despite|as\s+\S+\s+(?:beats?|miss\w*|report\w*|announc\w*|rais\w*|cut\w*|"
         r"guid\w*|win\w*|wins|los\w*|agree\w*|acquir\w*|launch\w*|receiv\w*|get\w*|sign\w*|issu\w*|file\w*|names?|warn\w*))\b"
         r"|\b(?:beats?|miss(?:es)?|reports?|announc\w*|guidance|forecast\w*|acquisition|deal|merger|fda|approval|earnings|results|"
         r"q[1-4]\b|quarter|contract|lawsuit|upgrade|downgrade|recall|ceo)\b")
R_ROUND, R_MOVE, R_CAUSE = (re.compile(p, re.I) for p in (ROUNDUP, MOVE_HEAD, CAUSE))

def classify(titles):
    """price_report = pure price/technical report with no stated cause;
       event_plus_price = names a move AND a cause (keep: the event is real news);
       no_price = everything else."""
    out = np.full(len(titles), "no_price", dtype=object)
    for i, s in enumerate(titles):
        if R_ROUND.search(s):
            out[i] = "price_report"
        elif R_MOVE.search(s):
            out[i] = "event_plus_price" if R_CAUSE.search(s) else "price_report"
    return out
