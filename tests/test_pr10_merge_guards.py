import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_settings


def test_post_run_settings_coexist_with_unified_and_entry():
    settings = load_settings()

    assert isinstance(settings.UNIFIED_SCORING_ENABLED, bool)
    assert isinstance(settings.ENTRY_SELECTOR_ENABLED, bool)
    assert isinstance(settings.POST_RUN_ANALYZER_ENABLED, bool)

    assert settings.POST_RUN_MIN_TRADES_FOR_CORRELATION > 0
    assert settings.POST_RUN_MIN_TRADES_FOR_REGIME_COMPARISON > 0
    assert settings.POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION > 0
    assert 0 <= settings.POST_RUN_OUTLIER_CLIP_PCT <= 1
    assert 0 <= settings.POST_RUN_RECOMMENDATION_CONFIDENCE_MIN <= 1
    assert isinstance(settings.CONFIG_SUGGESTIONS_ENABLED, bool)
    assert settings.CONFIG_SUGGESTIONS_MIN_SAMPLE > 0
    assert isinstance(settings.CONFIG_SUGGESTIONS_TRAINING_WHEELS_MODE, bool)


def test_env_example_contains_post_run_block_once():
    env_example = Path('.env.example').read_text(encoding='utf-8')

    assert env_example.count('POST_RUN_ANALYZER_ENABLED=') == 1
    assert env_example.count('POST_RUN_ANALYZER_FAILCLOSED=') == 1
    assert 'POST_RUN_MIN_TRADES_FOR_CORRELATION=' in env_example
    assert 'POST_RUN_MIN_TRADES_FOR_REGIME_COMPARISON=' in env_example
    assert 'POST_RUN_MIN_SAMPLE_FOR_RECOMMENDATION=' in env_example
    assert 'POST_RUN_OUTLIER_CLIP_PCT=' in env_example
    assert 'POST_RUN_CONTRACT_VERSION=' in env_example
    assert env_example.count('CONFIG_SUGGESTIONS_ENABLED=') == 1
    assert 'CONFIG_SUGGESTIONS_MIN_SAMPLE=' in env_example
    assert 'CONFIG_SUGGESTIONS_TRAINING_WHEELS_MODE=' in env_example
    assert 'CONFIG_SUGGESTIONS_CONTRACT_VERSION=' in env_example


def test_readme_mentions_pr10_without_removing_pr7_section():
    readme = Path('README.md').read_text(encoding='utf-8')

    assert '## PR-7 entry selector' in readme
    assert '## PR-10 post-run analyzer' in readme
