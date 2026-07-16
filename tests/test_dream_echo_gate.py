"""Dream echo keyword and time-window branches."""
from core.dream.echo_gate import should_dream_echo


def test_two_hours_after_exit_without_keyword_is_echo():
    assert should_dream_echo(last_exited_at=1000, user_content="你好", reply="我在", now=1000 + 2 * 3600)


def test_three_days_after_exit_without_keyword_is_not_echo():
    assert not should_dream_echo(last_exited_at=1000, user_content="你好", reply="我在", now=1000 + 3 * 86400)


def test_three_days_after_exit_with_dream_keyword_is_echo():
    assert should_dream_echo(last_exited_at=1000, user_content="我梦到你了", reply="嗯", now=1000 + 3 * 86400)


def test_no_dream_history_without_keyword_is_not_echo():
    assert not should_dream_echo(last_exited_at=None, user_content="你好", reply="我在", now=1000)


def test_aspiration_word_does_not_trigger_dream_echo():
    assert not should_dream_echo(last_exited_at=None, user_content="我的梦想是去远方", reply="很好", now=1000)
