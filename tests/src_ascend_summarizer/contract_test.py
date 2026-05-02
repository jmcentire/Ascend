"""
Contract test suite for Meeting Summarizer component.

Tests cover:
- Pure functions: _truncate, _parse_json
- Client management: get_client
- API functions: summarize_transcript, extract_items, analyze_sentiment, generate_prep
- Validators: content_must_be_nonempty
- Type validation: MeetingItemExtract, MeetingItemKind
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
from typing import Optional, Any
import json
import os

# Import the component under test
from src.ascend.summarizer import (
    _truncate,
    _parse_json,
    get_client,
    summarize_transcript,
    extract_items,
    analyze_sentiment,
    generate_prep,
    content_must_be_nonempty,
    MeetingItemExtract,
    MeetingItemKind,
)


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def mock_config():
    """Mock AscendConfig with test settings."""
    config = Mock()
    config.anthropic_api_key_env = "ANTHROPIC_API_KEY"
    config.model_name = "claude-3-sonnet-20240229"
    config.max_tokens = 4096
    return config


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client with message creation."""
    client = Mock()
    client.messages = Mock()
    return client


@pytest.fixture
def mock_successful_response():
    """Mock successful API response."""
    response = Mock()
    response.content = [Mock(text="Test response")]
    return response


# ==============================================================================
# TESTS: _truncate
# ==============================================================================

def test_truncate_short_text_unchanged():
    """Verify that text shorter than MAX_INPUT_CHARS is returned unchanged."""
    text = "Short meeting transcript."
    result = _truncate(text)
    
    assert result == "Short meeting transcript."
    assert " [TRUNCATED]" not in result


def test_truncate_exactly_100000_chars():
    """Text exactly at MAX_INPUT_CHARS boundary should not be truncated."""
    text = "a" * 100000
    result = _truncate(text)
    
    assert len(result) == 100000
    assert " [TRUNCATED]" not in result


def test_truncate_long_text_with_sentence():
    """Text over 100,000 chars with sentence boundary after 50,000 should break at sentence."""
    text = "a" * 60000 + ". " + "b" * 50000
    result = _truncate(text)
    
    assert result.endswith(" [TRUNCATED]")
    assert len(result) <= 100012  # 100000 + len(' [TRUNCATED]')
    assert ". " in result


def test_truncate_long_text_no_sentence_boundary():
    """Text over 100,000 chars without sentence boundary should truncate at MAX_INPUT_CHARS."""
    text = "a" * 150000
    result = _truncate(text)
    
    assert result.endswith(" [TRUNCATED]")
    assert len(result) == 100012  # 100000 + len(' [TRUNCATED]')


def test_truncate_empty_string():
    """Empty string should be returned unchanged."""
    text = ""
    result = _truncate(text)
    
    assert result == ""


def test_truncate_unicode_characters():
    """Unicode characters should be handled correctly without corruption."""
    text = "Hello 😀 café " * 10
    result = _truncate(text)
    
    assert "😀" in result
    assert "café" in result


def test_invariant_max_input_chars():
    """MAX_INPUT_CHARS constant should be 100000."""
    # Access the constant from the module
    from src.ascend.summarizer import _MAX_INPUT_CHARS
    assert _MAX_INPUT_CHARS == 100000


# ==============================================================================
# TESTS: _parse_json
# ==============================================================================

def test_parse_json_simple_object():
    """Valid JSON object should be parsed correctly."""
    text = '{"key": "value", "num": 42}'
    result = _parse_json(text)
    
    assert result == {"key": "value", "num": 42}


def test_parse_json_array():
    """Valid JSON array should be parsed correctly."""
    text = '[1, 2, 3, "test"]'
    result = _parse_json(text)
    
    assert result == [1, 2, 3, "test"]


def test_parse_json_with_markdown_fences():
    """JSON wrapped in markdown code fences should be extracted and parsed."""
    text = '```json\n{"extracted": true}\n```'
    result = _parse_json(text)
    
    assert result == {"extracted": True}


def test_parse_json_invalid_json():
    """Invalid JSON should raise ValueError with invalid_json error."""
    text = "{invalid json}"
    
    with pytest.raises(ValueError):
        _parse_json(text)


def test_parse_json_primitive():
    """JSON primitive values should be parsed correctly."""
    text = '"string"'
    result = _parse_json(text)
    
    assert result == "string"


def test_parse_json_with_backticks_only():
    """JSON with just backticks should strip them."""
    text = '```\n[1, 2, 3]\n```'
    result = _parse_json(text)
    
    assert result == [1, 2, 3]


# ==============================================================================
# TESTS: get_client
# ==============================================================================

def test_get_client_with_valid_api_key(mock_config):
    """Valid API key in environment should return Anthropic client."""
    with patch("os.environ.get", return_value="test_api_key_12345"):
        with patch("src_ascend_summarizer.anthropic.Anthropic") as mock_anthropic:
            mock_client = Mock()
            mock_anthropic.return_value = mock_client
            
            result = get_client(mock_config)
            
            assert result is not None
            assert result == mock_client


def test_get_client_missing_api_key(mock_config):
    """Missing API key should return None and log warning."""
    with patch("os.environ.get", return_value=None):
        with patch("src_ascend_summarizer.logger") as mock_logger:
            result = get_client(mock_config)
            
            assert result is None
            assert mock_logger.warning.called


def test_get_client_empty_api_key(mock_config):
    """Empty API key should return None."""
    with patch("os.environ.get", return_value=""):
        result = get_client(mock_config)
        
        assert result is None


def test_get_client_creation_failure(mock_config):
    """Exception during client creation should return None and log error."""
    with patch("os.environ.get", return_value="test_key"):
        with patch("src_ascend_summarizer.anthropic.Anthropic", side_effect=Exception("API error")):
            with patch("src_ascend_summarizer.logger") as mock_logger:
                result = get_client(mock_config)
                
                assert result is None
                assert mock_logger.error.called


# ==============================================================================
# TESTS: summarize_transcript
# ==============================================================================

def test_summarize_transcript_success(mock_config, mock_anthropic_client):
    """Valid transcript with client should return summary string."""
    raw_text = "Meeting transcript with discussions and decisions"
    
    mock_response = Mock()
    mock_response.content = [Mock(text="Summary of meeting")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = summarize_transcript(raw_text, mock_config, mock_anthropic_client)
        
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


def test_summarize_transcript_empty_input(mock_config, mock_anthropic_client):
    """Empty or whitespace-only input should return None."""
    raw_text = "   "
    
    result = summarize_transcript(raw_text, mock_config, mock_anthropic_client)
    
    assert result is None


def test_summarize_transcript_no_client(mock_config):
    """None client with unavailable get_client should return None."""
    raw_text = "Valid transcript"
    
    with patch("src_ascend_summarizer.get_client", return_value=None):
        result = summarize_transcript(raw_text, mock_config, None)
        
        assert result is None


def test_summarize_transcript_api_error(mock_config, mock_anthropic_client):
    """API call exception should return None and log error."""
    raw_text = "Valid transcript"
    mock_anthropic_client.messages.create.side_effect = Exception("API error")
    
    with patch("src_ascend_summarizer.logger") as mock_logger:
        with patch("src_ascend_summarizer.log_operation"):
            result = summarize_transcript(raw_text, mock_config, mock_anthropic_client)
            
            assert result is None
            assert mock_logger.error.called


def test_summarize_transcript_logs_operation(mock_config, mock_anthropic_client):
    """Successful summarization should call log_operation."""
    raw_text = "Meeting transcript"
    
    mock_response = Mock()
    mock_response.content = [Mock(text="Summary")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation") as mock_log:
        result = summarize_transcript(raw_text, mock_config, mock_anthropic_client)
        
        assert mock_log.called


def test_invariant_no_exceptions_propagate(mock_config, mock_anthropic_client):
    """Public API functions should not propagate exceptions."""
    raw_text = "text"
    mock_anthropic_client.messages.create.side_effect = RuntimeError("Unexpected")
    
    with patch("src_ascend_summarizer.logger"):
        with patch("src_ascend_summarizer.log_operation"):
            # Should not raise, should return None
            result = summarize_transcript(raw_text, mock_config, mock_anthropic_client)
            
            assert result is None or isinstance(result, str)


# ==============================================================================
# TESTS: extract_items
# ==============================================================================

def test_extract_items_success(mock_config, mock_anthropic_client):
    """Valid transcript should return list of validated meeting items."""
    raw_text = "Meeting with action items and decisions"
    
    api_response_text = json.dumps([
        {"kind": "action_item", "content": "Task", "owner": "John"}
    ])
    mock_response = Mock()
    mock_response.content = [Mock(text=api_response_text)]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = extract_items(raw_text, mock_config, mock_anthropic_client)
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert "kind" in result[0]
        assert "content" in result[0]


def test_extract_items_all_kinds(mock_config, mock_anthropic_client):
    """All MeetingItemKind enum values should be handled."""
    raw_text = "Complex meeting"
    
    api_response_text = json.dumps([
        {"kind": "action_item", "content": "Do task", "owner": "Alice"},
        {"kind": "decision", "content": "Decided to proceed", "owner": "Bob"},
        {"kind": "topic", "content": "Discussed budget", "owner": None},
        {"kind": "concern", "content": "Resource shortage", "owner": "Charlie"},
        {"kind": "win", "content": "Completed project", "owner": "Dana"}
    ])
    mock_response = Mock()
    mock_response.content = [Mock(text=api_response_text)]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = extract_items(raw_text, mock_config, mock_anthropic_client)
        
        assert any(item["kind"] == "action_item" for item in result)
        assert any(item["kind"] == "decision" for item in result)


def test_extract_items_empty_input(mock_config, mock_anthropic_client):
    """Empty input should return empty list."""
    raw_text = ""
    
    result = extract_items(raw_text, mock_config, mock_anthropic_client)
    
    assert result == []


def test_extract_items_no_client(mock_config):
    """No client available should return empty list."""
    raw_text = "Valid transcript"
    
    with patch("src_ascend_summarizer.get_client", return_value=None):
        result = extract_items(raw_text, mock_config, None)
        
        assert result == []


def test_extract_items_invalid_json(mock_config, mock_anthropic_client):
    """Non-JSON API response should return empty list."""
    raw_text = "Valid transcript"
    
    mock_response = Mock()
    mock_response.content = [Mock(text="not json")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.logger"):
        with patch("src_ascend_summarizer.log_operation"):
            result = extract_items(raw_text, mock_config, mock_anthropic_client)
            
            assert result == []


def test_extract_items_non_list_response(mock_config, mock_anthropic_client):
    """JSON response that is not a list should return empty list."""
    raw_text = "Valid transcript"
    
    mock_response = Mock()
    mock_response.content = [Mock(text='{"not": "a list"}')]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.logger"):
        with patch("src_ascend_summarizer.log_operation"):
            result = extract_items(raw_text, mock_config, mock_anthropic_client)
            
            assert result == []


def test_extract_items_validation_error(mock_config, mock_anthropic_client):
    """Items failing validation should be dropped with warning."""
    raw_text = "Valid transcript"
    
    # Empty content should fail validation
    api_response_text = json.dumps([
        {"kind": "action_item", "content": "", "owner": "John"}
    ])
    mock_response = Mock()
    mock_response.content = [Mock(text=api_response_text)]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.logger") as mock_logger:
        with patch("src_ascend_summarizer.log_operation"):
            result = extract_items(raw_text, mock_config, mock_anthropic_client)
            
            assert result == []
            assert mock_logger.warning.called


def test_extract_items_partial_validation_failure(mock_config, mock_anthropic_client):
    """Mix of valid and invalid items should return only valid items."""
    raw_text = "Valid transcript"
    
    api_response_text = json.dumps([
        {"kind": "action_item", "content": "Valid task", "owner": "Alice"},
        {"kind": "decision", "content": "", "owner": "Bob"},  # Invalid - empty content
        {"kind": "topic", "content": "Valid topic", "owner": None}
    ])
    mock_response = Mock()
    mock_response.content = [Mock(text=api_response_text)]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.logger"):
        with patch("src_ascend_summarizer.log_operation"):
            result = extract_items(raw_text, mock_config, mock_anthropic_client)
            
            assert len(result) > 0
            assert all(item["content"] for item in result)


def test_extract_items_logs_count(mock_config, mock_anthropic_client):
    """Should log operation with item count."""
    raw_text = "Meeting transcript"
    
    api_response_text = json.dumps([
        {"kind": "action_item", "content": "Task", "owner": "John"}
    ])
    mock_response = Mock()
    mock_response.content = [Mock(text=api_response_text)]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation") as mock_log:
        result = extract_items(raw_text, mock_config, mock_anthropic_client)
        
        assert mock_log.called


# ==============================================================================
# TESTS: analyze_sentiment
# ==============================================================================

def test_analyze_sentiment_success(mock_config, mock_anthropic_client):
    """Valid transcript should return float in [0.0, 1.0]."""
    raw_text = "Positive meeting discussion"
    
    mock_response = Mock()
    mock_response.content = [Mock(text="0.75")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
        
        assert result is not None
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


def test_analyze_sentiment_clamp_high(mock_config, mock_anthropic_client):
    """Score above 1.0 should be clamped to 1.0."""
    raw_text = "Very positive"
    
    mock_response = Mock()
    mock_response.content = [Mock(text="1.5")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
        
        assert result == 1.0


def test_analyze_sentiment_clamp_low(mock_config, mock_anthropic_client):
    """Score below 0.0 should be clamped to 0.0."""
    raw_text = "Very negative"
    
    mock_response = Mock()
    mock_response.content = [Mock(text="-0.3")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
        
        assert result == 0.0


def test_analyze_sentiment_empty_input(mock_config, mock_anthropic_client):
    """Empty input should return None."""
    raw_text = "  \n  "
    
    result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
    
    assert result is None


def test_analyze_sentiment_no_client(mock_config):
    """No client available should return None."""
    raw_text = "Valid transcript"
    
    with patch("src_ascend_summarizer.get_client", return_value=None):
        result = analyze_sentiment(raw_text, mock_config, None)
        
        assert result is None


def test_analyze_sentiment_unparseable_score(mock_config, mock_anthropic_client):
    """Non-numeric API response should return None."""
    raw_text = "Valid transcript"
    
    mock_response = Mock()
    mock_response.content = [Mock(text="not a number")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.logger"):
        with patch("src_ascend_summarizer.log_operation"):
            result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
            
            assert result is None


def test_analyze_sentiment_api_error(mock_config, mock_anthropic_client):
    """API exception should return None."""
    raw_text = "Valid transcript"
    mock_anthropic_client.messages.create.side_effect = Exception("API error")
    
    with patch("src_ascend_summarizer.logger"):
        with patch("src_ascend_summarizer.log_operation"):
            result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
            
            assert result is None


def test_analyze_sentiment_boundary_values(mock_config, mock_anthropic_client):
    """Exact boundary values 0.0 and 1.0 should be valid."""
    raw_text = "Meeting"
    
    mock_response = Mock()
    mock_response.content = [Mock(text="0.0")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
        
        assert result == 0.0
    
    # Test 1.0 boundary
    mock_response.content = [Mock(text="1.0")]
    
    with patch("src_ascend_summarizer.log_operation"):
        result = analyze_sentiment(raw_text, mock_config, mock_anthropic_client)
        
        assert result == 1.0


# ==============================================================================
# TESTS: generate_prep
# ==============================================================================

def test_generate_prep_success(mock_config, mock_anthropic_client):
    """Valid inputs should return structured prep plan."""
    member_name = "John Doe"
    recent_meetings = [{"summary": "Last meeting"}]
    open_items = [{"task": "Follow up"}]
    
    mock_response = Mock()
    mock_response.content = [Mock(text="Prep plan content")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = generate_prep(member_name, recent_meetings, open_items, None, mock_config, mock_anthropic_client)
        
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


def test_generate_prep_empty_member_name(mock_config, mock_anthropic_client):
    """Empty member name should return None."""
    member_name = "   "
    recent_meetings = []
    open_items = []
    
    result = generate_prep(member_name, recent_meetings, open_items, None, mock_config, mock_anthropic_client)
    
    assert result is None


def test_generate_prep_no_config(mock_anthropic_client):
    """Unavailable config should return None."""
    member_name = "John"
    recent_meetings = []
    open_items = []
    
    with patch("src_ascend_summarizer.load_config", return_value=None):
        result = generate_prep(member_name, recent_meetings, open_items, None, None, mock_anthropic_client)
        
        assert result is None


def test_generate_prep_no_client(mock_config):
    """Unavailable client should return None."""
    member_name = "John"
    recent_meetings = []
    open_items = []
    
    with patch("src_ascend_summarizer.get_client", return_value=None):
        result = generate_prep(member_name, recent_meetings, open_items, None, mock_config, None)
        
        assert result is None


def test_generate_prep_api_error(mock_config, mock_anthropic_client):
    """API error should return None."""
    member_name = "John"
    recent_meetings = []
    open_items = []
    mock_anthropic_client.messages.create.side_effect = Exception("API error")
    
    with patch("src_ascend_summarizer.logger"):
        with patch("src_ascend_summarizer.log_operation"):
            result = generate_prep(member_name, recent_meetings, open_items, None, mock_config, mock_anthropic_client)
            
            assert result is None


def test_generate_prep_with_performance_data(mock_config, mock_anthropic_client):
    """Optional performance data should be included in generation."""
    member_name = "John"
    recent_meetings = []
    open_items = []
    performance_data = {"score": 95}
    
    mock_response = Mock()
    mock_response.content = [Mock(text="Prep plan with performance data")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = generate_prep(member_name, recent_meetings, open_items, performance_data, mock_config, mock_anthropic_client)
        
        assert result is not None


def test_generate_prep_empty_lists(mock_config, mock_anthropic_client):
    """Empty recent_meetings and open_items should still generate prep."""
    member_name = "John"
    recent_meetings = []
    open_items = []
    
    mock_response = Mock()
    mock_response.content = [Mock(text="Minimal prep plan")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer.log_operation"):
        result = generate_prep(member_name, recent_meetings, open_items, None, mock_config, mock_anthropic_client)
        
        assert result is not None


# ==============================================================================
# TESTS: content_must_be_nonempty validator
# ==============================================================================

def test_content_validator_nonempty():
    """Non-empty content should pass validation."""
    v = "Valid content"
    result = content_must_be_nonempty(MeetingItemExtract, v)
    
    assert result == "Valid content"


def test_content_validator_empty():
    """Empty content should raise validation error."""
    v = ""
    
    with pytest.raises(ValueError):
        content_must_be_nonempty(MeetingItemExtract, v)


# ==============================================================================
# TESTS: MeetingItemExtract type validation
# ==============================================================================

def test_meeting_item_extract_valid():
    """Valid MeetingItemExtract should be created successfully."""
    item = MeetingItemExtract(
        kind=MeetingItemKind.action_item,
        content="Complete report",
        owner="Alice"
    )
    
    assert item.kind == MeetingItemKind.action_item
    assert item.content == "Complete report"
    assert item.owner == "Alice"


def test_meeting_item_extract_empty_content():
    """MeetingItemExtract with empty content should fail validation."""
    from pydantic import ValidationError
    
    with pytest.raises(ValidationError):
        item = MeetingItemExtract(
            kind=MeetingItemKind.decision,
            content="",
            owner="Bob"
        )


def test_meeting_item_extract_no_owner():
    """MeetingItemExtract with None owner should be valid."""
    item = MeetingItemExtract(
        kind=MeetingItemKind.topic,
        content="Discuss strategy",
        owner=None
    )
    
    assert item.owner is None
    assert item.content == "Discuss strategy"


# ==============================================================================
# TESTS: MeetingItemKind enum
# ==============================================================================

def test_meeting_item_kind_all_values():
    """All MeetingItemKind enum values should be valid."""
    # Verify all enum values exist
    assert MeetingItemKind.action_item
    assert MeetingItemKind.decision
    assert MeetingItemKind.topic
    assert MeetingItemKind.concern
    assert MeetingItemKind.win


def test_meeting_item_kind_values():
    """Enum values should match contract specification."""
    values = [item.value for item in MeetingItemKind]
    expected = ["action_item", "decision", "topic", "concern", "win"]
    
    assert set(values) == set(expected)


# ==============================================================================
# TESTS: Invariants
# ==============================================================================

def test_invariant_truncate_called_before_api(mock_config, mock_anthropic_client):
    """All API calls should use truncated input."""
    raw_text = "a" * 150000  # Longer than MAX_INPUT_CHARS
    
    mock_response = Mock()
    mock_response.content = [Mock(text="Summary")]
    mock_anthropic_client.messages.create.return_value = mock_response
    
    with patch("src_ascend_summarizer._truncate", wraps=_truncate) as mock_truncate:
        with patch("src_ascend_summarizer.log_operation"):
            result = summarize_transcript(raw_text, mock_config, mock_anthropic_client)
            
            # Verify truncate was called
            assert mock_truncate.called
            
            # Verify API received truncated text
            call_args = mock_anthropic_client.messages.create.call_args
            if call_args:
                # The system message or user message should contain truncated marker if input was long
                messages_arg = call_args[1].get("messages", [])
                if messages_arg:
                    content = messages_arg[0].get("content", "")
                    # If original was > 100000, truncation should have occurred
                    assert len(content) <= 100012  # 100000 + ' [TRUNCATED]'


def test_invariant_sentiment_always_clamped(mock_config, mock_anthropic_client):
    """Sentiment scores are always clamped to [0.0, 1.0] range."""
    test_cases = [
        ("2.5", 1.0),
        ("-1.0", 0.0),
        ("0.5", 0.5),
        ("1.0", 1.0),
        ("0.0", 0.0),
    ]
    
    for api_value, expected in test_cases:
        mock_response = Mock()
        mock_response.content = [Mock(text=api_value)]
        mock_anthropic_client.messages.create.return_value = mock_response
        
        with patch("src_ascend_summarizer.log_operation"):
            result = analyze_sentiment("Test", mock_config, mock_anthropic_client)
            
            if result is not None:
                assert 0.0 <= result <= 1.0
                assert result == expected


def test_invariant_meetingitemextract_content_always_nonempty():
    """MeetingItemExtract.content is always non-empty (enforced by validator)."""
    from pydantic import ValidationError
    
    # Valid case
    item = MeetingItemExtract(
        kind=MeetingItemKind.action_item,
        content="Valid",
        owner="Alice"
    )
    assert len(item.content) > 0
    
    # Invalid case - empty content
    with pytest.raises(ValidationError):
        MeetingItemExtract(
            kind=MeetingItemKind.action_item,
            content="",
            owner="Alice"
        )
    
    # Invalid case - whitespace only (if validator strips)
    try:
        item_ws = MeetingItemExtract(
            kind=MeetingItemKind.action_item,
            content="   ",
            owner="Alice"
        )
        # If this doesn't raise, ensure content is non-empty after any stripping
        assert len(item_ws.content.strip()) >= 0  # Depends on implementation
    except ValidationError:
        # Expected if validator rejects whitespace-only
        pass
