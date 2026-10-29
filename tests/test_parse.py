import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generate_scales import format_check, parse_items  # noqa: E402


class ParseItems(unittest.TestCase):
    def test_plain_numbered_list(self):
        text = "\n".join(f"{i}. This team item {i}." for i in range(1, 8))
        self.assertEqual(len(parse_items(text)), 7)

    def test_parenthesis_numbers(self):
        text = "\n".join(f"{i}) Item {i}" for i in range(1, 8))
        self.assertEqual(len(parse_items(text)), 7)

    def test_bold_numbers_and_preamble(self):
        text = "Here are the items:\n" + "\n".join(f"**{i}.** Item {i}" for i in range(1, 8))
        items = parse_items(text)
        self.assertEqual(len(items), 7)
        self.assertEqual(items[0], "Item 1")

    def test_ignores_non_list_lines(self):
        text = "Intro line\n1. First\nSome comment\n2. Second"
        self.assertEqual(parse_items(text), ["First", "Second"])

    def test_empty(self):
        self.assertEqual(parse_items(""), [])


# Real replies from claude-opus-5-5 (smoke test, level L0, run 1), copied
# verbatim from raw_response so the formatting is exactly what the API sent.
REAL_STAGE1 = '1. In this team, I feel comfortable admitting when I have made a mistake.\n2. Members of this team can raise concerns or problems without fear of being embarrassed or punished.\n3. In this team, it is safe to take a reasonable risk, even if it might not work out.\n4. I can ask other members of this team for help without worrying that they will think less of me.\n5. In this team, people are sometimes criticized or excluded for being different or holding unpopular views.\n6. Members of this team value my unique skills and contributions.\n7. I feel hesitant to question the way things are done in this team.'

REAL_STAGE2 = '**Review**\n\n- **Item 1** (mistakes): Single-barreled and clear. I rewrote it as a reverse-coded item so the set has two negatively worded items, which helps detect acquiescent responding.\n- **Item 2** (voice): Double-barreled twice: "concerns or problems" and "embarrassed or punished." It also overlaps with Item 7, since both ask about speaking up.\n- **Item 3** (risk-taking): "Reasonable risk" is vague, because respondents may define "reasonable" differently. I replaced it with a concrete behavior.\n- **Item 4** (help-seeking): Single-barreled and clear. No change.\n- **Item 5** (acceptance of differences): Double-barreled twice: "criticized or excluded" and "being different or holding unpopular views." The "unpopular views" part also overlaps with the voice items.\n- **Item 6** (being valued): Double-barreled: "skills and contributions."\n- **Item 7** (challenging the status quo): Overlaps with Item 2, since both measure willingness to speak up.\n- **Coverage**: The set covered mistakes, voice, risk-taking, help-seeking, acceptance of differences, and being valued. It covered voice twice and omitted interpersonal trust, meaning the belief that teammates will not deliberately undermine one\'s efforts. I replaced Item 7 with a trust item.\n\n**Revised items**\n\n1. If I make a mistake in this team, it is often held against me.\n2. Members of this team can bring up problems without fear of negative consequences.\n3. It is safe to try new approaches in this team, even if they might fail.\n4. I can ask other members of this team for help without worrying that they will think less of me.\n5. Members of this team sometimes reject others for being different.\n6. Members of this team value my unique skills.\n7. No one in this team would deliberately act in a way that undermines my efforts.\n\nItems 1 and 5 are reverse-coded.'


class ParseRealReplies(unittest.TestCase):
    def test_stage1_plain_list(self):
        items = parse_items(REAL_STAGE1)
        self.assertEqual(len(items), 7)
        self.assertEqual(items[0], "In this team, I feel comfortable admitting when I have made a mistake.")
        self.assertEqual(items[6], "I feel hesitant to question the way things are done in this team.")

    def test_stage2_review_bullets_then_list_then_note(self):
        # Bold heading, bullet-point review, numbered list, closing sentence.
        items = parse_items(REAL_STAGE2)
        self.assertEqual(len(items), 7)
        self.assertEqual(items[0], "If I make a mistake in this team, it is often held against me.")
        self.assertEqual(items[6], "No one in this team would deliberately act in a way that undermines my efforts.")


# Real stage 2 reply (claude-opus-5-5, L0, run 1, second smoke test) whose
# review notes are numbered 1 to 7 before the revised list, copied verbatim.
REAL_STAGE2_NUMBERED_REVIEW = '**Review**\n\n1. *Admitting mistakes.* This item is clear, but it overlaps with item 6, since both concern whether failures are held against the respondent. It also measures the respondent\'s comfort rather than the team climate.\n2. *Raise concerns or disagree.* This item asks about two things at once: raising concerns and disagreeing. "Negative consequences" is also vague.\n3. *Asking for help.* This item is acceptable as a reverse-scored item. Its wording can be simplified.\n4. *Welcome new ideas, even when they challenge the way things are usually done.* This item is a compound statement. It overlaps with item 2 because both concern speaking up, and it measures receptiveness to ideas rather than interpersonal risk.\n5. *Embarrassed or put down for asking questions.* This item asks about two things at once, and "sometimes" is ambiguous. It also partly overlaps with item 3, since asking questions and asking for help are similar behaviours.\n6. *Take a risk.* "A risk" is ambiguous, because it could mean a business risk or an interpersonal risk. The item also overlaps with item 1.\n7. *Value and respect … unique skills and contributions.* This item asks about two things twice over: valuing and respecting, and skills and contributions.\n\n**Coverage gaps:** The items did not address deliberate undermining by teammates. They also did not clearly separate voicing problems, voicing dissent, and experimenting with new approaches. The revised set covers seven distinct facets, one per item:\n- mistakes\n- raising problems\n- dissent\n- help-seeking\n- experimentation\n- undermining\n- being valued\n\nItems 1, 4, and 6 are reverse-scored.\n\n**Revised items**\n\n1. If I make a mistake in this team, it is held against me.\n2. In this team, I can raise difficult issues openly.\n3. In this team, I can express a view that differs from the majority\'s.\n4. Asking for help in this team would make me look incompetent.\n5. In this team, it is safe to try a new approach that might not work.\n6. Some members of this team would deliberately undermine my efforts.\n7. Members of this team value my contributions.'


class ParseLastList(unittest.TestCase):
    def test_numbered_review_then_list_returns_the_list(self):
        items = parse_items(REAL_STAGE2_NUMBERED_REVIEW)
        self.assertEqual(len(items), 7)
        self.assertEqual(items[0], "If I make a mistake in this team, it is held against me.")
        self.assertEqual(items[6], "Members of this team value my contributions.")


class FormatCheck(unittest.TestCase):
    def test_plain_list_is_exact(self):
        text = "\n".join(f"{i}. Item {i}" for i in range(1, 8))
        self.assertEqual(format_check(text, 7), "exact")

    def test_bold_numbers_and_blank_lines_are_exact(self):
        text = "\n\n".join(f"**{i}.** Item {i}" for i in range(1, 8))
        self.assertEqual(format_check(text, 7), "exact")

    def test_extra_text_is_flagged(self):
        result = format_check(REAL_STAGE2, 7)
        self.assertTrue(result.startswith("deviation"))
        self.assertIn("outside the list", result)

    def test_two_lists_are_flagged(self):
        result = format_check(REAL_STAGE2_NUMBERED_REVIEW, 7)
        self.assertIn("numbered lines are", result)

    def test_wrong_count_is_flagged(self):
        text = "\n".join(f"{i}. Item {i}" for i in range(1, 7))
        self.assertTrue(format_check(text, 7).startswith("deviation"))


if __name__ == "__main__":
    unittest.main()
