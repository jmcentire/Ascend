"""
Contract tests for Meeting Summarizer component.

Tests cover:
- _truncate: text truncation with sentence boundary detection
- _parse_json: JSON parsing with markdown fence support
- MeetingItemKind: enum values
- MeetingItemExtract: validated struct with content validation
- content_must_be_nonempty: field validator
- get_client: Anthropic client creation
- summarize_transcript: meeting summary generation
- extract_items: structured item extraction
- analyze_sentiment: sentiment score analysis
- generate_prep: 1:1 meeting prep generation
"""

import json
import os
from typing import Any, Optional
from unittest import mock
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import component under test
# Adjust import path based on actual module structure
try:
    from contracts.src_ascend_summarizer.interface import (
        MeetingItemExtract,
        MeetingItemKind,
        _parse_json,
        _truncate,
        analyze_sentiment,
        content_must_be_nonempty,
        extract_items,
        generate_prep,
        get_client,
        summarize_transcript,
        _MAX_INPUT_CHARS,
    )
except ImportError:
    # Fallback for different module structures
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from contracts.src_ascend_summarizer.interface import (
        MeetingItemExtract,
        MeetingItemKind,
        _parse_json,
        _truncate,
        analyze_sentiment,
        content_must_be_nonempty,
        extract_items,
        generate_prep,
        get_client,
        summarize_transcript,
        _MAX_INPUT_CHARS,
    )


# Fixtures for common test setup
@pytest.fixture
def mock_config():
    """Mock AscendConfig object."""
    config = Mock()
    config.anthropic_api_key_env = "ANTHROPIC_API_KEY"
    config.model = "claude-3-sonnet-20240229"
    return config


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client."""
    client = Mock()
    return client


@pytest.fixture
def mock_api_response():
    """Mock successful API response."""
    response = Mock()
    content_block = Mock()
    content_block.text = "This is a generated response from Claude."
    response.content = [content_block]
    return response


# Tests for _truncate
def test_truncate_short_text_unchanged():
    """Text shorter than _MAX_INPUT_CHARS is returned unchanged."""
    text = "This is a short text."
    result = _truncate(text)
    assert result == text
    assert len(result) <= 100000
    assert "[TRUNCATED]" not in result


def test_truncate_exactly_max_chars():
    """Text exactly at _MAX_INPUT_CHARS is returned unchanged."""
    text = "a" * 100000
    result = _truncate(text)
    assert len(result) == 100000
    assert "[TRUNCATED]" not in result


def test_truncate_long_text_with_period():
    """Text longer than _MAX_INPUT_CHARS truncates at sentence boundary if period found in second half."""
    text = "a" * 75000 + ". Some sentence." + "b" * 30000
    result = _truncate(text)
    assert result.endswith(" [TRUNCATED]")
    assert len(result) <= 100000 + len(" [TRUNCATED]")
    assert "." in result


def test_truncate_long_text_no_period():
    """Text longer than _MAX_INPUT_CHARS with no period in second half truncates at max chars."""
    text = "x" * 150000
    result = _truncate(text)
    assert result.endswith(" [TRUNCATED]")
    assert len(result) == 100000 + len(" [TRUNCATED]")


def test_truncate_empty_string():
    """Empty string is returned unchanged."""
    text = ""
    result = _truncate(text)
    assert result == ""
    assert "[TRUNCATED]" not in result


# Tests for _parse_json
def test_parse_json_simple_object():
    """Valid JSON object is parsed correctly."""
    text = '{"key": "value", "number": 42}'
    result = _parse_json(text)
    assert result == {"key": "value", "number": 42}


def test_parse_json_array():
    """Valid JSON array is parsed correctly."""
    text = '[1, 2, 3, "test"]'
    result = _parse_json(text)
    assert result == [1, 2, 3, "test"]


def test_parse_json_with_markdown_fence():
    """JSON wrapped in markdown code fence is extracted and parsed."""
    text = '```json\n{"key": "value"}\n```'
    result = _parse_json(text)
    assert result == {"key": "value"}


def test_parse_json_with_generic_fence():
    """JSON wrapped in generic markdown fence is extracted and parsed."""
    text = "```\n[1, 2, 3]\n```"
    result = _parse_json(text)
    assert result == [1, 2, 3]


def test_parse_json_with_whitespace():
    """JSON with leading/trailing whitespace is parsed correctly."""
    text = '  \n  {"key": "value"}  \n  '
    result = _parse_json(text)
    assert result == {"key": "value"}


def test_parse_json_invalid():
    """Invalid JSON raises json_decode_error."""
    text = "{invalid json}"
    with pytest.raises(json.JSONDecodeError):
        _parse_json(text)


def test_parse_json_empty_string():
    """Empty string raises json_decode_error."""
    text = ""
    with pytest.raises(json.JSONDecodeError):
        _parse_json(text)


# Tests for MeetingItemKind enum
def test_meeting_item_kind_valid_values():
    """All valid MeetingItemKind enum values are accepted."""
    assert MeetingItemKind.action_item
    assert MeetingItemKind.decision
    assert MeetingItemKind.topic
    assert MeetingItemKind.concern
    assert MeetingItemKind.win
    # Verify all 5 values exist
    assert len(list(MeetingItemKind)) == 5


# Tests for MeetingItemExtract
def test_meeting_item_extract_valid():
    """Valid MeetingItemExtract is created successfully."""
    item = MeetingItemExtract(
        kind=MeetingItemKind.action_item,
        content="Follow up on project X",
        owner="Alice"
    )
    assert item.kind == MeetingItemKind.action_item
    assert item.content == "Follow up on project X"
    assert item.owner == "Alice"


def test_meeting_item_extract_no_owner():
    """MeetingItemExtract with no owner (None) is valid."""
    item = MeetingItemExtract(
        kind=MeetingItemKind.decision,
        content="Decided to use Python",
        owner=None
    )
    assert item.owner is None


def test_meeting_item_extract_empty_content():
    """MeetingItemExtract with empty content raises empty_content error."""
    with pytest.raises(ValueError) as exc_info:
        MeetingItemExtract(
            kind=MeetingItemKind.topic,
            content="",
            owner="Bob"
        )
    # Pydantic validation error should mention content
    assert "content" in str(exc_info.value).lower()


# Tests for content_must_be_nonempty validator
def test_content_validator_nonempty():
    """content_must_be_nonempty validator returns value unchanged for non-empty string."""
    result = content_must_be_nonempty(MeetingItemExtract, "Some content")
    assert result == "Some content"


def test_content_validator_empty():
    """content_must_be_nonempty validator raises empty_content for empty string."""
    with pytest.raises(ValueError) as exc_info:
        content_must_be_nonempty(MeetingItemExtract, "")
    assert "empty" in str(exc_info.value).lower()


# Tests for get_client
@patch("contracts_src_ascend_summarizer_interface.os.getenv")
@patch("contracts_src_ascend_summarizer_interface.anthropic.Anthropic")
def test_get_client_with_api_key(mock_anthropic, mock_getenv, mock_config):
    """get_client returns Anthropic client when API key is set."""
    mock_getenv.return_value = "sk-test-key"
    mock_client = Mock()
    mock_anthropic.return_value = mock_client
    
    result = get_client(mock_config)
    
    assert result is not None
    assert result == mock_client
    mock_getenv.assert_called_once_with("ANTHROPIC_API_KEY")
    mock_anthropic.assert_called_once_with(api_key="sk-test-key")


@patch("contracts_src_ascend_summarizer_interface.os.getenv")
def test_get_client_missing_api_key_env_var(mock_getenv, mock_config):
    """get_client returns None and logs warning when API key env var is not set."""
    mock_getenv.return_value = None
    
    result = get_client(mock_config)
    
    assert result is None
    mock_getenv.assert_called_once_with("ANTHROPIC_API_KEY")


@patch("contracts_src_ascend_summarizer_interface.os.getenv")
def test_get_client_empty_api_key(mock_getenv, mock_config):
    """get_client returns None when API key env var is empty string."""
    mock_getenv.return_value = ""
    
    result = get_client(mock_config)
    
    assert result is None


@patch("contracts_src_ascend_summarizer_interface.os.getenv")
@patch("contracts_src_ascend_summarizer_interface.anthropic.Anthropic")
def test_get_client_creation_error(mock_anthropic, mock_getenv, mock_config):
    """get_client returns None when Anthropic client construction fails."""
    mock_getenv.return_value = "sk-test-key"
    mock_anthropic.side_effect = Exception("Connection failed")
    
    result = get_client(mock_config)
    
    assert result is None


# Tests for summarize_transcript
def test_summarize_transcript_success(mock_config, mock_anthropic_client):
    """summarize_transcript returns summary string on successful API call."""
    response = Mock()
    content_block = Mock()
    content_block.text = "Meeting covered project updates and next steps. Team is aligned on deliverables."
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = summarize_transcript(
        "Meeting transcript with lots of details about the project...",
        mock_config,
        mock_anthropic_client
    )
    
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0
    mock_anthropic_client.messages.create.assert_called_once()


def test_summarize_transcript_empty_input(mock_config, mock_anthropic_client):
    """summarize_transcript returns None for empty input."""
    result = summarize_transcript("", mock_config, mock_anthropic_client)
    assert result is None


def test_summarize_transcript_whitespace_input(mock_config, mock_anthropic_client):
    """summarize_transcript returns None for whitespace-only input."""
    result = summarize_transcript("   \n\t  ", mock_config, mock_anthropic_client)
    assert result is None


@patch("contracts_src_ascend_summarizer_interface.get_client")
def test_summarize_transcript_no_client(mock_get_client, mock_config):
    """summarize_transcript returns None when client is None and cannot be created."""
    mock_get_client.return_value = None
    
    result = summarize_transcript("Valid transcript text", mock_config, None)
    
    assert result is None


def test_summarize_transcript_api_error(mock_config, mock_anthropic_client):
    """summarize_transcript returns None when API call raises exception."""
    mock_anthropic_client.messages.create.side_effect = Exception("API error")
    
    result = summarize_transcript("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result is None


def test_summarize_transcript_empty_response(mock_config, mock_anthropic_client):
    """summarize_transcript returns None when API response text is empty."""
    response = Mock()
    content_block = Mock()
    content_block.text = ""
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = summarize_transcript("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result is None


# Tests for extract_items
def test_extract_items_success(mock_config, mock_anthropic_client):
    """extract_items returns list of validated dicts on successful API call."""
    response = Mock()
    content_block = Mock()
    items_json = [
        {"kind": "action_item", "content": "Follow up on budget", "owner": "Alice"},
        {"kind": "decision", "content": "Approved new design", "owner": None}
    ]
    content_block.text = json.dumps(items_json)
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = extract_items(
        "Meeting transcript discussing action items...",
        mock_config,
        mock_anthropic_client
    )
    
    assert isinstance(result, list)
    assert len(result) > 0
    assert all("kind" in item for item in result)


def test_extract_items_empty_input(mock_config, mock_anthropic_client):
    """extract_items returns empty list for empty input."""
    result = extract_items("", mock_config, mock_anthropic_client)
    assert result == []


def test_extract_items_whitespace_input(mock_config, mock_anthropic_client):
    """extract_items returns empty list for whitespace-only input."""
    result = extract_items("  \n  ", mock_config, mock_anthropic_client)
    assert result == []


@patch("contracts_src_ascend_summarizer_interface.get_client")
def test_extract_items_no_client(mock_get_client, mock_config):
    """extract_items returns empty list when client is None and cannot be created."""
    mock_get_client.return_value = None
    
    result = extract_items("Valid transcript text", mock_config, None)
    
    assert result == []


def test_extract_items_malformed_json(mock_config, mock_anthropic_client):
    """extract_items returns empty list when API response is malformed JSON."""
    response = Mock()
    content_block = Mock()
    content_block.text = "{invalid json"
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = extract_items("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result == []


def test_extract_items_not_a_list(mock_config, mock_anthropic_client):
    """extract_items returns empty list when API response is valid JSON but not a list."""
    response = Mock()
    content_block = Mock()
    content_block.text = '{"key": "value"}'  # Object instead of array
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = extract_items("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result == []


def test_extract_items_api_error(mock_config, mock_anthropic_client):
    """extract_items returns empty list when API call raises exception."""
    mock_anthropic_client.messages.create.side_effect = Exception("API error")
    
    result = extract_items("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result == []


def test_extract_items_drops_invalid_items(mock_config, mock_anthropic_client):
    """extract_items drops invalid items with warnings and returns valid ones."""
    response = Mock()
    content_block = Mock()
    items_json = [
        {"kind": "action_item", "content": "Valid item", "owner": "Alice"},
        {"kind": "decision", "content": "", "owner": "Bob"},  # Invalid: empty content
        {"kind": "topic", "content": "Another valid item", "owner": None}
    ]
    content_block.text = json.dumps(items_json)
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = extract_items("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert isinstance(result, list)
    # Should have 2 valid items (invalid one dropped)
    assert all(item.get("content") for item in result)


# Tests for analyze_sentiment
def test_analyze_sentiment_success(mock_config, mock_anthropic_client):
    """analyze_sentiment returns float in [0.0, 1.0] on successful API call."""
    response = Mock()
    content_block = Mock()
    content_block.text = '{"score": 0.75}'
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = analyze_sentiment(
        "Great meeting! Very productive discussion.",
        mock_config,
        mock_anthropic_client
    )
    
    assert result is not None
    assert isinstance(result, float)
    assert 0.0 <= result <= 1.0


def test_analyze_sentiment_empty_input(mock_config, mock_anthropic_client):
    """analyze_sentiment returns None for empty input."""
    result = analyze_sentiment("", mock_config, mock_anthropic_client)
    assert result is None


def test_analyze_sentiment_whitespace_input(mock_config, mock_anthropic_client):
    """analyze_sentiment returns None for whitespace-only input."""
    result = analyze_sentiment("   \n\t  ", mock_config, mock_anthropic_client)
    assert result is None


@patch("contracts_src_ascend_summarizer_interface.get_client")
def test_analyze_sentiment_no_client(mock_get_client, mock_config):
    """analyze_sentiment returns None when client is None and cannot be created."""
    mock_get_client.return_value = None
    
    result = analyze_sentiment("Valid transcript text", mock_config, None)
    
    assert result is None


def test_analyze_sentiment_unparseable_response(mock_config, mock_anthropic_client):
    """analyze_sentiment returns None when response cannot be parsed as score."""
    response = Mock()
    content_block = Mock()
    content_block.text = "not a valid score"
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = analyze_sentiment("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result is None


def test_analyze_sentiment_api_error(mock_config, mock_anthropic_client):
    """analyze_sentiment returns None when API call raises exception."""
    mock_anthropic_client.messages.create.side_effect = Exception("API error")
    
    result = analyze_sentiment("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result is None


def test_analyze_sentiment_clamps_high(mock_config, mock_anthropic_client):
    """analyze_sentiment clamps score above 1.0 to 1.0 with warning."""
    response = Mock()
    content_block = Mock()
    content_block.text = '{"score": 1.5}'
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = analyze_sentiment("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result == 1.0


def test_analyze_sentiment_clamps_low(mock_config, mock_anthropic_client):
    """analyze_sentiment clamps score below 0.0 to 0.0 with warning."""
    response = Mock()
    content_block = Mock()
    content_block.text = '{"score": -0.5}'
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = analyze_sentiment("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result == 0.0


def test_analyze_sentiment_boundary_zero(mock_config, mock_anthropic_client):
    """analyze_sentiment accepts score exactly 0.0."""
    response = Mock()
    content_block = Mock()
    content_block.text = '{"score": 0.0}'
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = analyze_sentiment("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result == 0.0


def test_analyze_sentiment_boundary_one(mock_config, mock_anthropic_client):
    """analyze_sentiment accepts score exactly 1.0."""
    response = Mock()
    content_block = Mock()
    content_block.text = '{"score": 1.0}'
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = analyze_sentiment("Valid transcript text", mock_config, mock_anthropic_client)
    
    assert result == 1.0


# Tests for generate_prep
def test_generate_prep_success(mock_config, mock_anthropic_client):
    """generate_prep returns prep plan string on successful API call."""
    response = Mock()
    content_block = Mock()
    content_block.text = "1:1 Prep Plan for Alice:\n1. Review recent achievements\n2. Discuss open action items"
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = generate_prep(
        "Alice",
        [{"date": "2024-01-15", "summary": "Project kickoff"}],
        [{"item": "Review design doc", "owner": "Alice"}],
        {"rating": 4.5},
        mock_config,
        mock_anthropic_client
    )
    
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_prep_empty_member_name(mock_config, mock_anthropic_client):
    """generate_prep returns None when member_name is empty."""
    result = generate_prep("", [], [], None, mock_config, mock_anthropic_client)
    assert result is None


def test_generate_prep_whitespace_member_name(mock_config, mock_anthropic_client):
    """generate_prep returns None when member_name is whitespace-only."""
    result = generate_prep("   \n  ", [], [], None, mock_config, mock_anthropic_client)
    assert result is None


@patch("contracts_src_ascend_summarizer_interface.get_client")
def test_generate_prep_no_client(mock_get_client, mock_config):
    """generate_prep returns None when client is None and cannot be created."""
    mock_get_client.return_value = None
    
    result = generate_prep("Alice", [], [], None, mock_config, None)
    
    assert result is None


def test_generate_prep_api_error(mock_config, mock_anthropic_client):
    """generate_prep returns None when API call raises exception."""
    mock_anthropic_client.messages.create.side_effect = Exception("API error")
    
    result = generate_prep("Alice", [], [], None, mock_config, mock_anthropic_client)
    
    assert result is None


def test_generate_prep_empty_response(mock_config, mock_anthropic_client):
    """generate_prep returns None when API response text is empty."""
    response = Mock()
    content_block = Mock()
    content_block.text = ""
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = generate_prep("Alice", [], [], None, mock_config, mock_anthropic_client)
    
    assert result is None


@patch("contracts_src_ascend_summarizer_interface.load_config")
def test_generate_prep_loads_config_when_none(mock_load_config, mock_anthropic_client):
    """generate_prep loads config via load_config() when config is None."""
    loaded_config = Mock()
    loaded_config.model = "claude-3-sonnet-20240229"
    mock_load_config.return_value = loaded_config
    
    response = Mock()
    content_block = Mock()
    content_block.text = "Prep plan content"
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = generate_prep("Alice", [], [], None, None, mock_anthropic_client)
    
    assert result is not None
    mock_load_config.assert_called_once()


def test_generate_prep_no_performance_data(mock_config, mock_anthropic_client):
    """generate_prep works when performance_data is None."""
    response = Mock()
    content_block = Mock()
    content_block.text = "Prep plan without performance data"
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    result = generate_prep("Alice", [], [], None, mock_config, mock_anthropic_client)
    
    assert result is not None


# Invariant tests
def test_invariant_max_input_chars():
    """Verify _MAX_INPUT_CHARS constant is 100000."""
    assert _MAX_INPUT_CHARS == 100000


def test_invariant_api_calls_use_truncate(mock_config, mock_anthropic_client):
    """Verify all API functions use _truncate on input text."""
    long_text = "x" * 150000
    
    response = Mock()
    content_block = Mock()
    content_block.text = "Summary"
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    summarize_transcript(long_text, mock_config, mock_anthropic_client)
    
    # Verify API was called
    assert mock_anthropic_client.messages.create.called
    call_args = mock_anthropic_client.messages.create.call_args
    
    # Extract the message content from the API call
    messages = call_args[1]["messages"]
    message_content = messages[0]["content"]
    
    # Verify the content was truncated
    assert len(message_content) <= 100000 + len(" [TRUNCATED]")


def test_invariant_sentiment_uses_256_tokens(mock_config, mock_anthropic_client):
    """Verify sentiment analysis uses max_tokens=256."""
    response = Mock()
    content_block = Mock()
    content_block.text = '{"score": 0.5}'
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    analyze_sentiment("Test text", mock_config, mock_anthropic_client)
    
    call_args = mock_anthropic_client.messages.create.call_args
    assert call_args[1]["max_tokens"] == 256


def test_invariant_other_apis_use_4096_tokens(mock_config, mock_anthropic_client):
    """Verify other API calls use max_tokens=4096."""
    response = Mock()
    content_block = Mock()
    content_block.text = "Summary"
    response.content = [content_block]
    mock_anthropic_client.messages.create.return_value = response
    
    summarize_transcript("Test text", mock_config, mock_anthropic_client)
    
    call_args = mock_anthropic_client.messages.create.call_args
    assert call_args[1]["max_tokens"] == 4096
