#!/usr/bin/env python3
"""Passphrase generator based on a Diceware word list.

Builds passwords from random words plus digits and one special character,
e.g. "Fuchs47KometTee%Wolke". Randomness comes from `secrets` (OS CSPRNG).

Word list format (German Diceware, one entry per line):

    11111<TAB or spaces>abakus
    11112<TAB or spaces>abbild

Lines that do not match (PGP header, comments, blank lines) are ignored.
If no Diceware-style lines are found, the file is read as a plain list with
one word per line.

Examples:
    python3 pwgen.py diceware_de.txt
    python3 pwgen.py diceware_de.txt -n 5 --max-word-len 5 --count 5
"""
import argparse
import math
import re
import secrets
import string
import sys
from pathlib import Path

SPECIAL = "!%?="
DICE_LINE = re.compile(r"^\s*[1-6]{5}\s+(\S+)\s*$")


def load_wordlist(path, ascii_only=True, max_word_len=None):
    """Read the word list and return a de-duplicated list of usable words."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()

    words = []
    for line in lines:
        m = DICE_LINE.match(line)
        if m:
            words.append(m.group(1))

    if not words:  # fallback: plain list, one word per line
        words = [ln.strip() for ln in lines if ln.strip() and " " not in ln.strip()]

    def usable(w):
        if not w.isalpha():
            return False
        if ascii_only and not w.isascii():
            return False
        if max_word_len and len(w) > max_word_len:
            return False
        return True

    # keep original order, drop duplicates (case-insensitive)
    unique = {}
    for w in words:
        if usable(w):
            unique.setdefault(w.lower(), w.lower())
    return list(unique.values())


def has_all_classes(pw):
    return (
        any(c.islower() for c in pw)
        and any(c.isupper() for c in pw)
        and any(c.isdigit() for c in pw)
        and any(c in SPECIAL for c in pw)
    )


def generate(words, n_words, n_digits, min_len, max_len, rng, max_tries=100_000):
    for _ in range(max_tries):
        parts = [w.capitalize() for w in rng.sample(words, n_words)]
        digits = "".join(secrets.choice(string.digits) for _ in range(n_digits))
        parts.insert(secrets.randbelow(len(parts) + 1), digits)
        parts.insert(secrets.randbelow(len(parts) + 1), secrets.choice(SPECIAL))
        pw = "".join(parts)
        if min_len <= len(pw) <= max_len and has_all_classes(pw):
            return pw
    sys.exit(
        f"No password of {min_len}-{max_len} characters found with {n_words} words. "
        "Use fewer words, shorter words (--max-word-len) or relax the length limits."
    )


def entropy_bits(n_list, n_words, n_digits):
    """Upper estimate in bits; length filtering lowers it slightly."""
    word_bits = (math.lgamma(n_list + 1) - math.lgamma(n_list - n_words + 1)) / math.log(2)
    digit_bits = n_digits * math.log2(10)
    special_bits = math.log2(len(SPECIAL))
    position_bits = math.log2(n_words + 1) + math.log2(n_words + 2)
    return word_bits + digit_bits + special_bits + position_bits


def main():
    p = argparse.ArgumentParser(description="Diceware-based password generator")
    p.add_argument("wordlist", help="path to the word list (txt)")
    p.add_argument("-n", "--words", type=int, default=4, help="number of words (default 4)")
    p.add_argument("-d", "--digits", type=int, default=2, help="number of digits (default 2)")
    p.add_argument("--min", dest="min_len", type=int, default=20, help="minimum length (default 20)")
    p.add_argument("--max", dest="max_len", type=int, default=25, help="maximum length (default 25)")
    p.add_argument("--max-word-len", type=int, default=None, help="only use words up to this length")
    p.add_argument("--umlauts", action="store_true", help="allow words with umlauts/ß (default: ASCII only)")
    p.add_argument("-c", "--count", type=int, default=1, help="how many passwords to print")
    args = p.parse_args()

    words = load_wordlist(args.wordlist, ascii_only=not args.umlauts, max_word_len=args.max_word_len)
    if len(words) < args.words:
        sys.exit(f"Word list too small ({len(words)} usable words).")

    rng = secrets.SystemRandom()
    for _ in range(args.count):
        print(generate(words, args.words, args.digits, args.min_len, args.max_len, rng))

    bits = entropy_bits(len(words), args.words, args.digits)
    print(f"[{len(words)} words in list, approx. {bits:.0f} bits entropy]", file=sys.stderr)


if __name__ == "__main__":
    main()
