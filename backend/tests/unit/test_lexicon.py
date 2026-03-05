from src.routing.lexicon import check_lexicon, check_short_utterance


class TestCheckLexicon:
    def test_match_exact(self) -> None:
        assert check_lexicon("idiota", {"idiota", "imbécil"}) is True

    def test_match_case_insensitive(self) -> None:
        assert check_lexicon("IDIOTA", {"idiota"}) is True

    def test_match_substring(self) -> None:
        assert check_lexicon("eres un idiota total", {"idiota"}) is True

    def test_no_match(self) -> None:
        assert check_lexicon("hola buenos días", {"idiota", "imbécil"}) is False

    def test_empty_lexicon(self) -> None:
        assert check_lexicon("idiota", set()) is False


class TestCheckShortUtterance:
    def test_match_greeting(self) -> None:
        short_utts = {"greetings": ["hola", "buenas"], "acknowledgements": ["ok", "vale"]}
        assert check_short_utterance("hola", short_utts, max_chars=10) == "greetings"

    def test_match_case_insensitive(self) -> None:
        short_utts = {"greetings": ["hola"]}
        assert check_short_utterance("Hola", short_utts, max_chars=10) == "greetings"

    def test_too_long_skipped(self) -> None:
        short_utts = {"greetings": ["buenos días"]}
        assert check_short_utterance("buenos días", short_utts, max_chars=5) is None

    def test_no_match(self) -> None:
        short_utts = {"greetings": ["hola"]}
        assert check_short_utterance("cobro", short_utts, max_chars=10) is None

    def test_empty_utterances(self) -> None:
        assert check_short_utterance("hola", {}, max_chars=10) is None

    def test_acknowledgement(self) -> None:
        short_utts = {"greetings": ["hola"], "acknowledgements": ["ok", "vale"]}
        assert check_short_utterance("vale", short_utts, max_chars=10) == "acknowledgements"
